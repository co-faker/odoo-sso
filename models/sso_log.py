from odoo import api
from odoo import fields
from odoo import models


class SSOLog(models.Model):
    _name = "sso.log"
    _description = "SSO Log"
    _order = "create_date DESC"
    _rec_name = "create_date"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        readonly=True,
        ondelete="set null",
    )
    application_id = fields.Many2one(
        "sso.application",
        string="Application",
        readonly=True,
        ondelete="set null",
    )
    action = fields.Selection(
        [
            ("authorize", "Authorize"),
            ("token_refresh", "Token Refresh"),
            ("userinfo", "User Info"),
            ("logout", "Logout"),
        ],
        string="Action",
        required=True,
        readonly=True,
    )
    ip = fields.Char(string="IP Address", readonly=True)
    user_agent = fields.Char(string="User Agent", readonly=True)
    success = fields.Boolean(string="Success", default=True, readonly=True)
    error_message = fields.Text(string="Error Message", readonly=True)

    @api.model
    def log(self, action, user=None, application=None, ip=None, user_agent=None, success=True, error_message=None):
        """Create a log entry."""
        return self.create(
            {
                "user_id": user.id if user else False,
                "application_id": application.id if application else False,
                "action": action,
                "ip": ip,
                "user_agent": user_agent,
                "success": success,
                "error_message": error_message,
            }
        )
