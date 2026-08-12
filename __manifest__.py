# -*- coding: utf-8 -*-
{
    "name": "SSO",
    "summary": "Single Sign-On OAuth2 Provider for Odoo",
    "description": """
        SSO - OAuth2 Provider
        =====================
        Provides OAuth2 authorization code flow for third-party applications
        to authenticate users through Odoo's user system.
    """,
    "author": "",
    "website": "",
    "license": "LGPL-3",
    "category": "Authentication",
    "version": "19.0.1.0.0",
    "depends": [
        "base",
        "web",
    ],
    "external_dependencies": {
        "python": [
            "jwt",
            "cryptography",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/sso_data.xml",
        "views/sso_application_views.xml",
        "views/sso_auth_code_views.xml",
        "views/sso_access_token_views.xml",
        "views/sso_user_consent_views.xml",
        "views/sso_log_views.xml",
        "views/sso_jwk_views.xml",
        "views/oauth_authorize_template.xml",
        "views/menu.xml",
    ],
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
