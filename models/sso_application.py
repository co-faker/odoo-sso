import hashlib
import secrets

from odoo import api
from odoo import fields
from odoo import models


class SSOApplication(models.Model):
    _name = "sso.application"
    _description = "SSO Application"
    _order = "name"
    _rec_name = "name"

    name = fields.Char(string="Application Name", required=True, translate=True)
    client_id = fields.Char(
        string="Client ID",
        required=True,
        readonly=True,
        index=True,
        copy=False,
        default=lambda self: self._generate_client_id(),
    )
    client_secret = fields.Char(
        string="Client Secret",
        readonly=True,
        copy=False,
        help="The client secret is only shown once after creation.",
    )
    client_secret_plain = fields.Char(
        string="Client Secret (Plain)",
        readonly=True,
        help="Temporarily holds the plain text secret for one-time display.",
    )
    redirect_uri_ids = fields.One2many(
        "sso.redirect.uri",
        "application_id",
        string="Redirect URIs",
    )
    scope = fields.Char(
        string="Scope",
        default="openid profile",
        help="Space-separated list of scopes. Default: openid profile",
    )
    access_token_validity = fields.Integer(
        string="Access Token Validity (seconds)",
        default=3600,
        required=True,
        help="Default: 3600 seconds (1 hour)",
    )
    id_token_validity = fields.Integer(
        string="ID Token Validity (seconds)",
        default=3600,
        required=True,
        help="Lifetime of the OIDC id_token. Default: 3600 seconds (1 hour).",
    )
    refresh_token_validity = fields.Integer(
        string="Refresh Token Validity (seconds)",
        default=86400,
        required=True,
        help="Default: 86400 seconds (24 hours)",
    )
    approval_prompt = fields.Selection(
        [
            ("auto", "Auto - Skip confirmation for returning users"),
            ("force", "Force - Always require user confirmation"),
        ],
        string="Approval Prompt",
        default="force",
        required=True,
    )
    consent_expiry = fields.Integer(
        string="Consent Expiry (days)",
        default=0,
        help="0 = never expires. Number of days after which user consent expires.",
    )
    active = fields.Boolean(string="Active", default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    image = fields.Binary(string="Logo", attachment=True)
    description = fields.Text(string="Description", translate=True)

    _sql_constraints = [
        ("unique_client_id", "UNIQUE(client_id)", "Client ID must be unique!"),
    ]

    @api.model
    def _generate_client_id(self):
        return "sso_" + secrets.token_hex(16)

    @api.model
    def _generate_client_secret(self):
        return secrets.token_hex(32)

    def action_generate_secret(self):
        self.ensure_one()
        plain_secret = self._generate_client_secret()
        self.write(
            {
                "client_secret": self._hash_secret(plain_secret),
                "client_secret_plain": plain_secret,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "sso.application",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": {
                "form_view_initial_mode": "edit",
                "show_secret": True,
            },
        }

    @api.model
    def _hash_secret(self, secret):
        return hashlib.sha256(secret.encode()).hexdigest()

    @api.model
    def validate_client_secret(self, client_id, client_secret):
        """Validate client credentials. Returns the application if valid, else None."""
        app = self.search([("client_id", "=", client_id), ("active", "=", True)], limit=1)
        if app and app.client_secret:
            return app if app.client_secret == self._hash_secret(client_secret) else None
        return None

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "client_id" not in vals:
                vals["client_id"] = self._generate_client_id()
        return super().create(vals_list)

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        default["client_id"] = self._generate_client_id()
        default["client_secret"] = False
        default["client_secret_plain"] = False
        return super().copy(default)

    def unlink(self):
        self.env["sso.redirect.uri"].search([("application_id", "in", self.ids)]).unlink()
        self.env["sso.auth.code"].search([("application_id", "in", self.ids)]).unlink()
        self.env["sso.access.token"].search([("application_id", "in", self.ids)]).unlink()
        self.env["sso.user.consent"].search([("application_id", "in", self.ids)]).unlink()
        self.env["sso.log"].search([("application_id", "in", self.ids)]).unlink()
        return super().unlink()
