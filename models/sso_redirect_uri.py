from odoo import _
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import ValidationError


class SSORedirectURI(models.Model):
    _name = "sso.redirect.uri"
    _description = "SSO Redirect URI"
    _rec_name = "uri"

    application_id = fields.Many2one(
        "sso.application",
        string="Application",
        required=True,
        ondelete="cascade",
    )
    uri = fields.Char(
        string="Redirect URI",
        required=True,
        help="Allowed redirect URI for OAuth2 callback. Must be a valid URL.",
    )

    _sql_constraints = [
        ("unique_uri_per_app", "UNIQUE(application_id, uri)", "This redirect URI already exists for this application!"),
    ]

    @api.constrains("uri")
    def _check_uri(self):
        for record in self:
            if not record.uri.startswith(("http://", "https://")):
                raise ValidationError(_("Redirect URI must start with http:// or https://"))
