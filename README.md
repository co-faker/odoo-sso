# SSO Client Example

A sample website that simulates a third-party application integrating with Odoo SSO via OAuth2.

## Prerequisites

- Odoo is installed and the `sso` module is started
- Python 3.8+
- pip

## Quick Start

### 1. Install dependencies

```bash
pip install flask requests
```

### 2. Create an SSO application in the Odoo backend

1. Log in to the Odoo backend (as a system administrator)
2. Go to **SSO → SSO Applications**
3. Click **Create**
4. Fill in:
   - **Application Name**: `SSO Client Example`
   - **Approval Prompt**: `Auto` (or `Force`, as needed)
   - **Redirect URIs**: add `http://localhost:5000/callback`
5. Click **Save**
6. Click **Generate New Secret** to generate the secret
7. Copy the **Client ID** and **Client Secret**

### 3. Configure and run

Edit `sso_client_example.py` and modify the `CONFIG` block at the top of the file:

```python
CONFIG = {
    "ODOO_SSO_BASE": "http://localhost:8069",   # Odoo service address
    "CLIENT_ID": "sso_xxx...",                   # Client ID copied in the previous step
    "CLIENT_SECRET": "xxx...",                   # Client Secret copied in the previous step
    "REDIRECT_URI": "http://localhost:5000/callback",
    "PORT": 5000,
}
```

Run:

```bash
python sso_client_example.py
```

### 4. Access

Open `http://localhost:5000` in a browser.

## Test Flow

```
1. Open http://localhost:5000
2. Click "Log in with Odoo"
3. Redirect to the Odoo SSO authorization page (enter credentials first if not logged in to Odoo)
4. Click "Authorize" to confirm authorization
5. Automatically redirect back to the example website and display user information
```

## Feature Description

| Route | Description |
|-------|-------------|
| `/` | Home page, displays user information or a login button |
| `/login` | Redirects to the Odoo SSO authorization page |
| `/callback` | OAuth2 callback address, exchanges the authorization code for a Token and fetches user information |
| `/refresh` | Manually refreshes the Access Token |
| `/logout` | SSO logout (also clears the local Session) |

## Complete OAuth2 Flow

```
User                    Example website              Odoo SSO
 |                       |                          |
 |  Click "Log in        |                          |
 |  with Odoo"           |                          |
 |---------------------->|                          |
 |                       |  GET /authorize          |
 |                       |  ?client_id&redirect_uri |
 |                       |  &response_type=code     |
 |                       |  &state=xxx              |
 |                       |------------------------->|
 |                       |                          |
 |  [Odoo login /        |                          |
 |   authorize page]     |                          |
 |<------------------------------------------------>|
 |                       |                          |
 |  Confirm authorize    |                          |
 |------------------------------------------------->|
 |                       |                          |
 |                       |  302 callback            |
 |                       |  ?code=yyy&state=xxx     |
 |                       |<-------------------------|
 |                       |                          |
 |                       |  POST /token             |
 |                       |  code + client_secret    |
 |                       |------------------------->|
 |                       |                          |
 |                       |  {access_token,          |
 |                       |   refresh_token}         |
 |                       |<-------------------------|
 |                       |                          |
 |                       |  GET /userinfo           |
 |                       |  Bearer access_token     |
 |                       |------------------------->|
 |                       |                          |
 |                       |  {sub, name, email, ...} |
 |                       |<-------------------------|
 |                       |                          |
 |  Display user info    |                          |
 |<----------------------|                          |
```

## Notes

- Make sure the Odoo service address is reachable from the machine running the example website
- The callback URL must exactly match the one configured in the Odoo backend (including the port)
- If `Force` mode is used, the user must confirm authorization every time
- If `Auto` mode is used, authorization is confirmed automatically and the confirmation page is skipped for returning users
- **About logout**: the example's `/logout` also logs out of the Odoo SSO session and returns to the example website's home page. Odoo's `/sso/oauth2/logout` requires the `redirect_uri` to be in the application's **callback allowlist**, otherwise it falls back to the Odoo login page. By default the example uses the home page address derived from `REDIRECT_URI` by stripping `/callback` (e.g. `http://192.168.8.7:5000/`) as the return address, so please **add this home page address** to the **Redirect URIs** of the SSO application in the Odoo backend, otherwise logout will not return correctly to the example home page.
