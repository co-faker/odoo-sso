import secrets
from datetime import datetime
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models


class SSOAccessToken(models.Model):
    _name = "sso.access.token"
    _description = "SSO Access Token"
    _order = "create_date DESC"
    _rec_name = "token"

    token = fields.Char(
        string="Access Token",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )
    application_id = fields.Many2one(
        "sso.application",
        string="Application",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    scope = fields.Char(string="Scope", readonly=True)
    expires_at = fields.Datetime(
        string="Access Token Expires At",
        required=True,
        readonly=True,
    )
    refresh_token = fields.Char(
        string="Refresh Token",
        readonly=True,
        index=True,
        copy=False,
    )
    refresh_expires_at = fields.Datetime(
        string="Refresh Token Expires At",
        readonly=True,
    )
    revoked = fields.Boolean(string="Revoked", default=False, readonly=True)

    _sql_constraints = [
        ("unique_token", "UNIQUE(token)", "Access token must be unique!"),
        ("unique_refresh_token", "UNIQUE(refresh_token)", "Refresh token must be unique!"),
    ]

    @api.model
    def _generate_token(self):
        return "at_" + secrets.token_urlsafe(32)

    @api.model
    def _generate_refresh_token(self):
        return "rt_" + secrets.token_urlsafe(32)

    @api.model
    def create_token(self, application, user, scope=None):
        """Create a new access token with refresh token."""
        now = datetime.utcnow()
        token_value = self._generate_token()
        refresh_value = self._generate_refresh_token()

        return self.create(
            {
                "token": token_value,
                "application_id": application.id,
                "user_id": user.id,
                "scope": scope or application.scope,
                "expires_at": now + timedelta(seconds=application.access_token_validity),
                "refresh_token": refresh_value,
                "refresh_expires_at": now + timedelta(seconds=application.refresh_token_validity),
            }
        )

    @api.model
    def validate_token(self, token):
        """Validate an access token. Returns the token record or None."""
        now = datetime.utcnow()
        record = self.search(
            [
                ("token", "=", token),
                ("revoked", "=", False),
                ("expires_at", ">", now),
            ],
            limit=1,
        )
        return record

    @api.model
    def refresh_access_token(self, refresh_token, client_id):
        """Refresh an access token using a refresh token. Returns new token record or None."""
        now = datetime.utcnow()
        old_token = self.search(
            [
                ("refresh_token", "=", refresh_token),
                ("application_id.client_id", "=", client_id),
                ("revoked", "=", False),
                ("refresh_expires_at", ">", now),
            ],
            limit=1,
        )
        if not old_token:
            return None

        application = old_token.application_id
        user = old_token.user_id

        old_token.write({"revoked": True})

        return self.create_token(application, user, old_token.scope)

    def action_revoke(self):
        self.write({"revoked": True})

    @api.model
    def _cron_cleanup_expired_tokens(self):
        """Remove expired tokens."""
        expired = self.search([("expires_at", "<", datetime.utcnow())])
        expired.unlink()
