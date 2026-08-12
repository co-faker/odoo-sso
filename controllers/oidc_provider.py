import json
import time

import jwt
from odoo import http
from odoo.http import request
from werkzeug.urls import url_parse, url_decode, url_encode


class OIDCProvider(http.Controller):
    """OpenID Connect endpoints. All routes are prefixed with /sso."""

    @http.route("/sso/oauth2/.well-known/openid-configuration", type="http", auth="none", methods=["GET"], sitemap=False, csrf=False)
    def openid_configuration(self, **kwargs):
        """OIDC Discovery document."""
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        issuer = base_url.rstrip("/") + "/sso/oauth2"
        data = {
            "issuer": issuer,
            "authorization_endpoint": issuer + "/authorize",
            "token_endpoint": issuer + "/token",
            "userinfo_endpoint": issuer + "/userinfo",
            "end_session_endpoint": issuer + "/logout",
            "jwks_uri": issuer + "/certs",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "profile", "email"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
            "claims_supported": [
                "iss",
                "sub",
                "aud",
                "exp",
                "iat",
                "nonce",
                "name",
                "preferred_username",
                "email",
                "email_verified",
                "groups",
            ],
            "code_challenge_methods_supported": ["S256"],
        }
        return self._json_response(data)

    @http.route("/sso/oauth2/certs", type="http", auth="none", methods=["GET"], sitemap=False, csrf=False)
    def jwks(self, **kwargs):
        """JSON Web Key Set document."""
        jwks = request.env["sso.jwk"].sudo().get_jwks()
        return self._json_response(jwks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_id_token(self, app, user, nonce, audience, scope=None):
        """Create and sign an OIDC id_token (RS256 JWT).

        Claims are filtered by the requested scope (OIDC standard):
        only include profile/email claims when the client asked for them.
        """
        key = request.env["sso.jwk"].sudo().get_active_key()
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        issuer = base_url.rstrip("/") + "/sso/oauth2"
        now = int(time.time())

        scopes = set((scope or "").split())

        partner = user.partner_id
        groups = user.group_ids
        groups_xmlids = groups.get_external_id()
        groups_claim = [
            g.full_name or g.name
            for g in groups
            if groups_xmlids.get(g.id)
        ]

        payload = {
            "iss": issuer,
            "sub": str(user.id),
            "aud": audience,
            "exp": now + app.id_token_validity,
            "iat": now,
            "auth_time": now,
        }
        if "profile" in scopes:
            payload["name"] = partner.name or user.login
            payload["given_name"] = user.name or partner.name
            payload["family_name"] = partner.name or ""
            payload["preferred_username"] = user.login
            payload["locale"] = user.lang or ""
            payload["groups"] = groups_claim
        if "email" in scopes:
            email = partner.email or user.login or ""
            if not email or "@" not in email:
                email = f"{user.login}@company.local"
            payload["email"] = email
            payload["email_verified"] = bool(partner.email)
        if nonce:
            payload["nonce"] = nonce

        id_token = jwt.encode(
            payload,
            key.private_key,
            algorithm="RS256",
            headers={"kid": key.name},
        )
        return id_token

    def _json_response(self, data, status=200):
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        }
        return request.make_response(json.dumps(data), headers=headers, status=status)
