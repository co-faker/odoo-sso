import base64
import json

import werkzeug.exceptions
import werkzeug.urls
import werkzeug.utils
from odoo import _
from odoo import http
from odoo.http import request


class OAuth2Provider(http.Controller):
    @http.route("/sso/oauth2/authorize", type="http", auth="user", methods=["GET"], sitemap=False)
    def authorize_page(self, **kwargs):
        """Display the OAuth2 authorization page."""
        client_id = kwargs.get("client_id")
        redirect_uri = kwargs.get("redirect_uri")
        response_type = kwargs.get("response_type", "code")
        state = kwargs.get("state")
        scope = kwargs.get("scope")
        nonce = kwargs.get("nonce")

        if not client_id or not redirect_uri or not state:
            return self._error_page("Missing required parameters: client_id, redirect_uri, state")

        if response_type != "code":
            return self._error_page("Unsupported response_type. Only 'code' is supported.")

        app = self._validate_application(client_id, redirect_uri)
        if not app:
            return self._error_page("Invalid client_id or redirect_uri not in whitelist.")

        if app.approval_prompt == "auto":
            consent = request.env["sso.user.consent"].has_valid_consent(request.env.user, app)
            if consent:
                code_record = request.env["sso.auth.code"].create_auth_code(
                    app, request.env.user, redirect_uri, state, scope, nonce
                )
                self._log_action("authorize", app, success=True)
                redirect_url = self._build_redirect_url(redirect_uri, code=code_record.code, state=state)
                return werkzeug.utils.redirect(redirect_url, 302)

        return request.render(
            "sso.oauth_authorize_template",
            {
                "application": app,
                "user": request.env.user,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": scope or app.scope,
                "client_id": client_id,
                "nonce": nonce,
            },
        )

    @http.route("/sso/oauth2/authorize", type="http", auth="user", methods=["POST"], sitemap=False)
    def authorize_confirm(self, **kwargs):
        """Handle user's authorization decision."""
        action = kwargs.get("action")
        client_id = kwargs.get("client_id")
        redirect_uri = kwargs.get("redirect_uri")
        state = kwargs.get("state")
        scope = kwargs.get("scope")
        nonce = kwargs.get("nonce")

        if not client_id or not redirect_uri or not state:
            return self._error_page("Missing required parameters")

        app = self._validate_application(client_id, redirect_uri)
        if not app:
            return self._error_page("Invalid client_id or redirect_uri not in whitelist.")

        if action == "deny":
            self._log_action("authorize", app, success=False, error_message="User denied authorization")
            redirect_url = self._build_redirect_url(redirect_uri, error="access_denied", state=state)
            return werkzeug.utils.redirect(redirect_url, 302)

        if action == "confirm":
            if app.approval_prompt == "auto":
                request.env["sso.user.consent"].grant_consent(request.env.user, app, scope)

            code_record = request.env["sso.auth.code"].create_auth_code(
                app, request.env.user, redirect_uri, state, scope, nonce
            )
            self._log_action("authorize", app, success=True)
            redirect_url = self._build_redirect_url(redirect_uri, code=code_record.code, state=state)
            return werkzeug.utils.redirect(redirect_url, 302)

        return self._error_page("Invalid action")

    @http.route("/sso/oauth2/token", type="http", auth="none", methods=["POST"], sitemap=False, csrf=False)
    def token(self, **kwargs):
        """Exchange authorization code or refresh token for access token."""
        grant_type = kwargs.get("grant_type", "authorization_code")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")

        if not client_id or not client_secret:
            auth_header = request.httprequest.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                    client_id, client_secret = decoded.split(":", 1)
                except (ValueError, base64.binascii.Error):
                    pass

        if not client_id or not client_secret:
            return self._json_error("invalid_client", "Client credentials are required")

        app = request.env["sso.application"].sudo().validate_client_secret(client_id, client_secret)
        if not app:
            return self._json_error("invalid_client", "Invalid client credentials")

        if grant_type == "authorization_code":
            return self._handle_auth_code_grant(app, kwargs)
        elif grant_type == "refresh_token":
            return self._handle_refresh_token_grant(app, kwargs)
        else:
            return self._json_error("unsupported_grant_type", f"Unsupported grant_type: {grant_type}")

    def _handle_auth_code_grant(self, app, kwargs):
        """Handle authorization_code grant type."""
        code = kwargs.get("code")
        redirect_uri = kwargs.get("redirect_uri")

        if not code or not redirect_uri:
            return self._json_error("invalid_request", "Missing code or redirect_uri")

        code_record = request.env["sso.auth.code"].sudo().consume_code(code, app.client_id, redirect_uri)
        if not code_record:
            return self._json_error("invalid_grant", "Invalid or expired authorization code")

        token_record = request.env["sso.access.token"].sudo().create_token(app, code_record.user_id, code_record.scope)

        self._log_action("token_refresh", app, user=code_record.user_id, success=True)

        response_data = {
            "access_token": token_record.token,
            "token_type": "Bearer",
            "expires_in": app.access_token_validity,
            "refresh_token": token_record.refresh_token,
            "scope": token_record.scope,
        }

        # OIDC: include id_token if openid scope requested
        if "openid" in (code_record.scope or "").split():
            from .oidc_provider import OIDCProvider
            oidc = OIDCProvider()
            id_token = oidc._build_id_token(
                app, code_record.user_id, code_record.nonce, app.client_id, code_record.scope
            )
            response_data["id_token"] = id_token

        return self._json_response(response_data)

    def _handle_refresh_token_grant(self, app, kwargs):
        """Handle refresh_token grant type."""
        refresh_token = kwargs.get("refresh_token")
        if not refresh_token:
            return self._json_error("invalid_request", "Missing refresh_token")

        new_token = request.env["sso.access.token"].sudo().refresh_access_token(refresh_token, app.client_id)
        if not new_token:
            return self._json_error("invalid_grant", "Invalid or expired refresh token")

        self._log_action("token_refresh", app, user=new_token.user_id, success=True)

        return self._json_response(
            {
                "access_token": new_token.token,
                "token_type": "Bearer",
                "expires_in": app.access_token_validity,
                "refresh_token": new_token.refresh_token,
                "scope": new_token.scope,
            }
        )

    @http.route("/sso/oauth2/userinfo", type="http", auth="none", methods=["GET"], sitemap=False, csrf=False)
    def userinfo(self, **kwargs):
        """Return user information for a valid access token."""
        auth_header = request.httprequest.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return self._json_error("invalid_token", "Missing or invalid Authorization header")

        token_value = auth_header[7:]
        token_record = request.env["sso.access.token"].sudo().validate_token(token_value)
        if not token_record:
            return self._json_error("invalid_token", "Invalid or expired access token")

        user = token_record.user_id
        partner = user.partner_id

        # Respect the requested scope (OIDC standard): only return claims
        # the client actually asked for.
        scopes = set((token_record.scope or "").split())

        claims = {"sub": str(user.id)}

        if "profile" in scopes:
            # Standard OIDC profile claims
            claims.update(
                {
                    "name": partner.name or user.login,
                    "given_name": user.name or partner.name,
                    "family_name": partner.name or "",
                    "preferred_username": user.login,
                    "locale": user.lang or "",
                }
            )
            # Odoo-specific extension claims (kept for convenience)
            claims.update(
                {
                    "login": user.login,
                    "user_id": user.id,
                    "partner_id": partner.id,
                    "company_id": user.company_id.id,
                    "company_name": user.company_id.name,
                }
            )

        if "email" in scopes:
            claims["email"] = partner.email or user.login or ""

        groups = user.group_ids
        groups_xmlids = groups.get_external_id()
        claims["groups"] = [
            {
                "id": g.id,
                "xmlid": groups_xmlids.get(g.id),
                "name": g.full_name or g.name,
            }
            for g in groups
        ]

        self._log_action("userinfo", token_record.application_id, user=user, success=True)

        return self._json_response(claims)

    @http.route("/sso/oauth2/logout", type="http", auth="user", methods=["GET"], sitemap=False)
    def logout(self, **kwargs):
        """SSO logout - destroy Odoo session and redirect."""
        redirect_uri = kwargs.get("redirect_uri", "/web")
        redirect_uri = redirect_uri.rstrip().rstrip("/")

        if redirect_uri and redirect_uri != "/web":
            app = (
                request.env["sso.application"]
                .sudo()
                .search(
                    [
                        ("redirect_uri_ids.uri", "=", redirect_uri),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
            )
            if not app:
                redirect_uri = "/web"

        self._log_action("logout", success=True)

        request.session.logout()
        request.session.db = None

        return werkzeug.utils.redirect(redirect_uri, 302)

    def _validate_application(self, client_id, redirect_uri):
        """Validate client_id and redirect_uri. Returns application or None."""
        app = (
            request.env["sso.application"]
            .sudo()
            .search(
                [
                    ("client_id", "=", client_id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if not app:
            return None

        valid_uris = app.redirect_uri_ids.mapped("uri")
        if redirect_uri not in valid_uris:
            return None

        return app

    def _build_redirect_url(self, base_uri, **params):
        """Build redirect URL with query parameters."""
        parsed = werkzeug.urls.url_parse(base_uri)
        existing_params = dict(werkzeug.urls.url_decode(parsed.query))
        existing_params.update({k: v for k, v in params.items() if v is not None})
        return parsed.replace(query=werkzeug.urls.url_encode(existing_params)).to_url()

    def _log_action(self, action, application=None, user=None, success=True, error_message=None):
        """Create a log entry."""
        try:
            ip = request.httprequest.remote_addr or ""
            user_agent = request.httprequest.headers.get("User-Agent", "")
            request.env["sso.log"].sudo().log(
                action=action,
                user=user or request.env.user,
                application=application,
                ip=ip,
                user_agent=user_agent,
                success=success,
                error_message=error_message,
            )
        except Exception:
            pass

    def _json_response(self, data, status=200):
        """Return a JSON response."""
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        }
        return request.make_response(json.dumps(data), headers=headers, status=status)

    def _json_error(self, error, description=""):
        """Return a JSON error response."""
        return self._json_response(
            {
                "error": error,
                "error_description": description,
            },
            status=400,
        )

    def _error_page(self, message):
        """Return an HTML error page."""
        return request.render(
            "sso.oauth_error_template",
            {
                "error_message": message,
                "_": _,
            },
        )
