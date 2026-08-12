from datetime import datetime
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models


class SSOUserConsent(models.Model):
    _name = "sso.user.consent"
    _description = "SSO User Consent"
    _order = "granted_date DESC"
    _rec_name = "user_id"
    _sql_constraints = [
        (
            "unique_user_application",
            "UNIQUE(user_id, application_id)",
            "This user already has a consent record for this application!",
        ),
    ]

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    application_id = fields.Many2one(
        "sso.application",
        string="Application",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    scope = fields.Char(string="Scope", readonly=True)
    granted_date = fields.Datetime(
        string="Granted Date",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    expires_at = fields.Datetime(
        string="Expires At",
        readonly=True,
        help="Null means never expires.",
    )

    @api.model
    def grant_consent(self, user, application, scope=None):
        """Create or update consent for a user-application pair."""
        existing = self.search(
            [
                ("user_id", "=", user.id),
                ("application_id", "=", application.id),
            ],
            limit=1,
        )

        vals = {
            "scope": scope or application.scope,
            "granted_date": datetime.utcnow(),
        }
        if application.consent_expiry > 0:
            vals["expires_at"] = datetime.utcnow() + timedelta(days=application.consent_expiry)
        else:
            vals["expires_at"] = False

        if existing:
            existing.write(vals)
            return existing
        else:
            vals.update(
                {
                    "user_id": user.id,
                    "application_id": application.id,
                }
            )
            return self.create(vals)

    @api.model
    def has_valid_consent(self, user, application):
        """Check if user has a valid (non-expired) consent for this application."""
        consent = self.search(
            [
                ("user_id", "=", user.id),
                ("application_id", "=", application.id),
            ],
            limit=1,
        )
        if not consent:
            return False
        if consent.expires_at and consent.expires_at < datetime.utcnow():
            return False
        return True

    def action_revoke(self):
        self.unlink()
