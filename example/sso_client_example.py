"""
SSO Client Example (OIDC / OAuth2)
===================================
A sample website that simulates a third-party application integrating with
Odoo SSO via OIDC (OpenID Connect).

Usage:
  1. First create an SSO application in the Odoo backend and obtain the
     client_id and client_secret.
  2. Add the following callback URL in the Odoo SSO app:
     http://localhost:5000/callback
  3. Modify the parameters in the CONFIG block below.
  4. Run: python sso_client_example.py
  5. Open in a browser: http://localhost:5000

OIDC flow:
  /login       -> /sso/oauth2/authorize (with nonce, state, scope=openid profile)
  /callback    -> /sso/oauth2/token (exchange code for access_token + id_token)
               -> verify id_token signature (JWKS) / nonce
               -> /sso/oauth2/userinfo to fetch user information
"""

import json
import secrets
from urllib.parse import urlencode

import jwt
import requests
from flask import Flask
from flask import redirect
from flask import render_template_string
from flask import request
from flask import session

# ============================================================
# Configuration - modify according to your environment
# ============================================================
CONFIG = {
    "ODOO_SSO_BASE": "http://127.0.0.1:8072",  # Odoo service address
    "CLIENT_ID": "sso_xxx",  # obtained from Odoo SSO backend
    "CLIENT_SECRET": "xxx",  # obtained from Odoo SSO backend
    "REDIRECT_URI": "http://127.0.0.1:5000/callback",  # must match the Odoo backend configuration
    "PORT": 5000,  # port for this example service
}

# OIDC route prefix (consistent with the sso module's /sso/oauth2/*)
OIDC_BASE = f"{CONFIG['ODOO_SSO_BASE']}/sso/oauth2"

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)


# ============================================================
# Helper functions
# ============================================================

def get_jwks():
    """Fetch Odoo SSO's JWKS public key set, used to verify the id_token signature."""
    resp = requests.get(f"{OIDC_BASE}/certs", timeout=10)
    resp.raise_for_status()
    return resp.json().get("keys", [])


def verify_id_token(id_token, nonce):
    """
    Verify the id_token's signature and claims using JWKS.
    Returns the decoded payload, raises an exception on verification failure.
    """
    # Read the kid from the header without verifying the signature first
    unverified_header = jwt.get_unverified_header(id_token)
    kid = unverified_header.get("kid")

    keys = get_jwks()
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if not jwk:
        raise ValueError("No matching JWK found (kid mismatch)")

    # Use PyJWT's PyJWK to convert the JWK dict into a public key object
    public_key = jwt.PyJWK(jwk).key

    issuer = OIDC_BASE  # Odoo OIDC issuer = base/sso/oauth2
    payload = jwt.decode(
        id_token,
        key=public_key,
        algorithms=["RS256"],
        audience=CONFIG["CLIENT_ID"],
        issuer=issuer,
        options={"verify_aud": True, "verify_iss": True},
    )

    # Verify the nonce to prevent replay attacks
    if nonce and payload.get("nonce") != nonce:
        raise ValueError("id_token nonce mismatch")

    return payload


# ============================================================
# HTML template
# ============================================================
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SSO Client Example (OIDC)</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
        .card { border: 1px solid #ddd; border-radius: 8px; padding: 30px; text-align: center; }
        .btn { display: inline-block; padding: 12px 30px; background: #875A7B; color: #fff;
               text-decoration: none; border-radius: 6px; font-size: 16px; }
        .btn:hover { background: #6d4a63; }
        .info { background: #f5f5f5; border-radius: 6px; padding: 15px; margin: 15px 0; text-align: left; }
        .info dt { font-weight: bold; margin-top: 8px; }
        .info dd { margin-left: 0; color: #555; }
        .error { color: #d32f2f; background: #ffebee; padding: 10px; border-radius: 6px; }
        .success { color: #2e7d32; background: #e8f5e9; padding: 10px; border-radius: 6px; }
        .sub { font-size: 12px; color: #999; word-break: break-all; }
    </style>
</head>
<body>
    <div class="card">
        <h1>SSO Client Example (OIDC)</h1>
        <p>Simulate a third-party application integrating with Odoo SSO via OpenID Connect</p>
        {% if user %}
            <div class="success">Logged in via Odoo SSO</div>
            <div class="info">
                <dl>
                    <dt>User ID (sub)</dt><dd>{{ user.sub }}</dd>
                    <dt>Name</dt><dd>{{ user.name }}</dd>
                    <dt>Login (preferred_username)</dt><dd>{{ user.preferred_username or user.login }}</dd>
                    <dt>Email</dt><dd>{{ user.email }}</dd>
                    <dt>User Groups</dt><dd>
                        <ul style="margin: 0; padding-left: 18px; max-height: 160px; overflow-y: auto;">
                            {% for g in user.groups %}
                                <li>{{ g }}</li>
                            {% endfor %}
                        </ul>
                    </dd>
                    {% if id_token_claims %}
                    <dt>id_token claims</dt>
                    <dd class="sub">{{ id_token_claims }}</dd>
                    {% endif %}
                </dl>
            </div>
            <a href="/logout" class="btn" style="background: #d32f2f;">Log out</a>
        {% else %}
            <p style="color: #888; margin: 20px 0;">Click the button below to log in with your Odoo account</p>
            <a href="/login" class="btn">Log in with Odoo</a>
        {% endif %}
        <p style="margin-top: 30px; font-size: 12px; color: #aaa;">
            Odoo SSO (OIDC): {{ config.ODOO_SSO_BASE }}/sso/oauth2
        </p>
    </div>
</body>
</html>
"""


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    """Home page - display user info or a login button"""
    user_json = session.get("user")
    user = json.loads(user_json) if user_json else None
    id_token_claims = session.get("id_token_claims")
    return render_template_string(INDEX_HTML, user=user, config=CONFIG, id_token_claims=id_token_claims)


@app.route("/login")
def login():
    """Step 1: Redirect to the Odoo SSO authorization page (with state + nonce)"""
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    session["oauth_nonce"] = nonce

    params = {
        "client_id": CONFIG["CLIENT_ID"],
        "redirect_uri": CONFIG["REDIRECT_URI"],
        "response_type": "code",
        "state": state,
        "nonce": nonce,
        "scope": "openid profile email",
    }
    authorize_url = f"{OIDC_BASE}/authorize?{urlencode(params)}"
    return redirect(authorize_url)


@app.route("/callback")
def callback():
    """Step 3: Odoo SSO callback - exchange code for token, verify id_token, then fetch user info"""
    error = request.args.get("error")
    if error:
        return f"Authorization failed: {error}", 400

    code = request.args.get("code")
    state = request.args.get("state")

    # Verify state to prevent CSRF
    saved_state = session.pop("oauth_state", None)
    if not state or state != saved_state:
        return "State mismatch, possible CSRF attack", 400

    if not code:
        return "Missing authorization code", 400

    saved_nonce = session.pop("oauth_nonce", None)

    # Step 4: Exchange the authorization code for a token
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CONFIG["REDIRECT_URI"],
        "client_id": CONFIG["CLIENT_ID"],
        "client_secret": CONFIG["CLIENT_SECRET"],
    }
    token_resp = requests.post(
        f"{OIDC_BASE}/token",
        data=token_data,
        timeout=10,
    )
    if token_resp.status_code != 200:
        return f"Token exchange failed: {token_resp.text}", 400

    token_json = token_resp.json()
    access_token = token_json["access_token"]
    refresh_token = token_json.get("refresh_token")
    id_token = token_json.get("id_token")

    # Step 4.5: Verify the id_token (OIDC)
    id_token_claims = None
    if id_token:
        try:
            claims = verify_id_token(id_token, saved_nonce)
            id_token_claims = json.dumps(claims, ensure_ascii=False, indent=2)
            session["id_token_claims"] = id_token_claims
        except Exception as e:
            return f"id_token verification failed: {e}", 400

    # Save to session
    session["access_token"] = access_token
    session["refresh_token"] = refresh_token

    # Step 5: Fetch user info using the access token
    user_resp = requests.get(
        f"{OIDC_BASE}/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        return f"Failed to fetch user info: {user_resp.text}", 400

    user_info = user_resp.json()
    session["user"] = json.dumps(user_info, ensure_ascii=False)

    return redirect("/")


@app.route("/refresh")
def refresh():
    """Manually refresh the token"""
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return "No refresh token available, please log in again", 400

    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CONFIG["CLIENT_ID"],
        "client_secret": CONFIG["CLIENT_SECRET"],
    }
    token_resp = requests.post(
        f"{OIDC_BASE}/token",
        data=token_data,
        timeout=10,
    )
    if token_resp.status_code != 200:
        return f"Token refresh failed: {token_resp.text}", 400

    token_json = token_resp.json()
    session["access_token"] = token_json["access_token"]
    session["refresh_token"] = token_json.get("refresh_token", refresh_token)
    return redirect("/")


@app.route("/logout")
def logout():
    """Log out - clear the local session first, then log out of the Odoo SSO
    session, and finally return to the example app's home page"""
    session.clear()
    # Odoo's /sso/oauth2/logout requires the redirect_uri to be in the app's
    # callback allowlist, otherwise it falls back to the Odoo login page.
    home_uri = CONFIG["REDIRECT_URI"].rsplit("/callback", 1)[0] + "/"
    logout_url = f"{OIDC_BASE}/logout?redirect_uri={home_uri}"
    return redirect(logout_url)


# ============================================================
# Startup
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("SSO Client Example (OIDC)")
    print("=" * 50)
    print()
    print(f"  Access URL: http://localhost:{CONFIG['PORT']}")
    print(f"  Odoo SSO: {OIDC_BASE}")
    print(f"  Callback URL: {CONFIG['REDIRECT_URI']}")
    print()
    print("  Before using, please ensure:")
    print("    1. Odoo is installed and the SSO module is started")
    print("    2. An SSO application is created in the Odoo backend (scope must include openid)")
    print(f"    3. Callback URL added: {CONFIG['REDIRECT_URI']}")
    print("    4. Fill CLIENT_ID and CLIENT_SECRET into CONFIG")
    print()
    print("=" * 50)
    app.run(host="0.0.0.0", port=CONFIG["PORT"], debug=True)
