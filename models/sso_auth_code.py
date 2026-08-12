import secrets
from datetime import datetime
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models


class SSOAuthCode(models.Model):
    _name = "sso.auth.code"
    _description = "SSO Authorization Code"
    _order = "create_date DESC"
    _rec_name = "code"

    code = fields.Char(
        string="Authorization Code",
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
    redirect_uri = fields.Char(string="Redirect URI", readonly=True)
    state = fields.Char(string="State", readonly=True)
    nonce = fields.Char(string="Nonce", readonly=True, help="OIDC nonce for id_token binding.")
    expires_at = fields.Datetime(
        string="Expires At",
        required=True,
        readonly=True,
    )
    used = fields.Boolean(string="Used", default=False, readonly=True)

    _sql_constraints = [
        ("unique_code", "UNIQUE(code)", "Authorization code must be unique!"),
    ]

    @api.model
    def _generate_code(self):
        return secrets.token_urlsafe(32)

    @api.model
    def create_auth_code(self, application, user, redirect_uri, state, scope=None, nonce=None):
        """Create a new authorization code with 5-minute expiry."""
        code_value = self._generate_code()
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        return self.create(
            {
                "code": code_value,
                "application_id": application.id,
                "user_id": user.id,
                "scope": scope or application.scope,
                "redirect_uri": redirect_uri,
                "state": state,
                "nonce": nonce,
                "expires_at": expires_at,
            }
        )

    @api.model
    def consume_code(self, code, client_id, redirect_uri):
        """Validate and consume an authorization code. Returns the code record or None."""
        now = datetime.utcnow()
        code_record = self.search(
            [
                ("code", "=", code),
                ("application_id.client_id", "=", client_id),
                ("redirect_uri", "=", redirect_uri),
                ("used", "=", False),
                ("expires_at", ">", now),
            ],
            limit=1,
        )
        if code_record:
            code_record.write({"used": True})
        return code_record

    @api.model
    def _cron_cleanup_expired_codes(self):
        """Remove expired authorization codes."""
        expired = self.search([("expires_at", "<", datetime.utcnow())])
        expired.unlink()
