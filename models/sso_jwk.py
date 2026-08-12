import json

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt

from odoo import api
from odoo import fields
from odoo import models


class SSOJWK(models.Model):
    _name = "sso.jwk"
    _description = "SSO JSON Web Key"
    _order = "create_date DESC"

    name = fields.Char(string="Key ID (kid)", readonly=True, copy=False)
    active = fields.Boolean(string="Active", default=True)
    private_key = fields.Text(
        string="Private Key (PEM)",
        readonly=True,
        copy=False,
        groups="base.group_system",
        help="RSA private key in PEM format. Used to sign id_token.",
    )
    public_key = fields.Text(
        string="Public Key (PEM)",
        readonly=True,
        copy=False,
        groups="base.group_system",
        help="RSA public key in PEM format.",
    )
    algorithm = fields.Char(string="Algorithm", default="RS256", readonly=True)

    _sql_constraints = [
        ("unique_kid", "UNIQUE(name)", "Key ID must be unique!"),
    ]

    @api.model
    def _generate_kid(self):
        import secrets
        return "sso_" + secrets.token_hex(8)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = self._generate_kid()
            if not vals.get("private_key"):
                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                )
                priv_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ).decode("utf-8")
                pub_pem = private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
                vals["private_key"] = priv_pem
                vals["public_key"] = pub_pem
        return super().create(vals_list)

    @api.model
    def get_active_key(self):
        """Return the active signing key (create one if none exists)."""
        key = self.search([("active", "=", True)], limit=1, order="create_date DESC")
        if not key:
            key = self.create({})
        return key

    def _get_public_jwk(self):
        """Return the JWK public key dict for JWKS endpoint."""
        self.ensure_one()
        import json as _json
        public_key = serialization.load_pem_public_key(self.public_key.encode("utf-8"))
        jwk_json = jwt.algorithms.RSAAlgorithm.to_jwk(public_key)
        jwk = _json.loads(jwk_json) if isinstance(jwk_json, str) else jwk_json
        jwk.update({
            "use": "sig",
            "alg": self.algorithm,
            "kid": self.name,
        })
        return jwk

    @api.model
    def get_jwks(self):
        """Return the JWKS document with all active keys."""
        keys = self.search([("active", "=", True)])
        return {
            "keys": [k._get_public_jwk() for k in keys],
        }
