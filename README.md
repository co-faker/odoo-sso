# SSO — OAuth2 Provider API 使用说明

Odoo `sso` 模块将 Odoo 作为 **OAuth2 Provider（授权服务器）**，基于 Odoo 自身的
`res.users` 账号体系，为第三方应用提供标准的 **授权码模式（Authorization Code Flow）**
单点登录能力。本模块**不接入任何第三方 IdP**，所有认证都在 Odoo 内完成。

- 版本：19.0.1.0.0
- 依赖：`base`、`web`
- 授权模式：`authorization_code`（支持 Refresh Token）

---

## 1. 前置条件（在 Odoo 后台配置）

1. 以系统管理员身份进入 **SSO → SSO Applications → 创建**。
2. 记录系统生成的 **Client ID**（`client_id`）与 **Client Secret**（仅创建/重生成时明文显示一次）。
3. 在 **Redirect URIs** 中填写第三方应用的回调地址（可填多个，必须精确匹配）。
   - 退出登录（见 `GET /auth/oauth2/logout`）跳转回的地址也**必须**在白名单内，否则会 fallback 到 Odoo 登录页。
4. 关键字段：
   - **Scope**：空格分隔的作用域，默认 `openid profile`。
   - **Access Token Validity (seconds)**：Access Token 有效期，默认 `3600`（1 小时）。
   - **Refresh Token Validity (seconds)**：Refresh Token 有效期，默认 `86400`（24 小时）。
   - **Approval Prompt**：`force`（每次都要求用户确认）/ `auto`（老用户自动跳过确认页）。
   - **Consent Expiry (days)**：授权记忆有效期，`0` 表示永不过期。

---

## 2. 端点总览

| 方法 | 路径 | 认证 | CSRF | 说明 |
|------|------|------|------|------|
| GET | `/auth/oauth2/authorize` | `user`（需登录） | 需要 | 展示授权确认页面（浏览器流程） |
| POST | `/auth/oauth2/authorize` | `user`（需登录） | 需要 | 用户确认/拒绝授权（浏览器流程） |
| POST | `/auth/oauth2/token` | `none` | 否 | 用授权码换 Token / 用 Refresh Token 刷新 |
| GET | `/auth/oauth2/userinfo` | `none`（Bearer Token） | 否 | 获取已登录用户信息 |
| GET | `/auth/oauth2/logout` | `user`（需登录） | 否 | 销毁 Odoo SSO 会话并跳转 |

> 所有路径前缀均为 Odoo 服务地址，例如 `http://192.168.8.7:8069/auth/oauth2/...`。

---

## 3. 端点详细说明

### 3.1 GET `/auth/oauth2/authorize`

展示授权页面。**此端点用于浏览器重定向**，不应由服务端直接调用。

**查询参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `client_id` | 是 | 应用的 Client ID |
| `redirect_uri` | 是 | 必须与应用白名单完全一致 |
| `response_type` | 是 | 固定为 `code` |
| `state` | 是 | 客户端生成的随机串，用于防 CSRF，原样随回调返回 |
| `scope` | 否 | 请求的作用域，缺省使用应用配置值 |

**行为：**
- 参数缺失或 `response_type != code` → 返回错误页。
- `client_id` / `redirect_uri` 校验失败 → 返回错误页。
- `Approval Prompt = auto` 且用户已有有效授权记忆 → 直接生成授权码并重定向，**跳过确认页**。
- 否则渲染授权确认页（含 CSRF Token）。

---

### 3.2 POST `/auth/oauth2/authorize`

用户点击「Authorize / Deny」提交。**浏览器表单提交，必须携带 CSRF Token**。

**表单字段：**

| 字段 | 说明 |
|------|------|
| `csrf_token` | Odoo 表单 CSRF 令牌（页面已预填） |
| `action` | `confirm`（授权）或 `deny`（拒绝） |
| `client_id` / `redirect_uri` / `state` / `scope` | 与 GET 请求一致，页面隐藏字段带回 |

**行为：**
- `action = deny` → 302 重定向回 `redirect_uri?error=access_denied&state=...`。
- `action = confirm` →
  - 若 `Approval Prompt = auto`，记录用户授权记忆（`sso.user.consent`）。
  - 生成授权码（5 分钟有效期，一次性），302 重定向回 `redirect_uri?code=...&state=...`。

> 授权码见 `sso.auth.code`，有效期 5 分钟，使用一次后立即作废。

---

### 3.3 POST `/auth/oauth2/token`

**客户端凭证（back-channel）调用**，无需用户登录，用于换取/刷新 Token。

**客户端认证方式（任选其一）：**
- HTTP Basic Auth：`Authorization: Basic base64(client_id:client_secret)`
- 表单字段：`client_id` + `client_secret`

#### 3.3.1 授权码换 Token — `grant_type=authorization_code`

**请求字段：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `grant_type` | 是 | `authorization_code` |
| `code` | 是 | 回调拿到的授权码 |
| `redirect_uri` | 是 | 必须与申请授权码时一致 |
| `client_id` | 有条件 | Basic Auth 缺省时必填 |
| `client_secret` | 有条件 | Basic Auth 缺省时必填 |

**成功响应（200，application/json）：**

```json
{
  "access_token": "at_xxxx",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "rt_xxxx",
  "scope": "openid profile"
}
```

#### 3.3.2 刷新 Token — `grant_type=refresh_token`

**请求字段：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `grant_type` | 是 | `refresh_token` |
| `refresh_token` | 是 | 之前获取的 Refresh Token |
| `client_id` | 有条件 | Basic Auth 缺省时必填 |
| `client_secret` | 有条件 | Basic Auth 缺省时必填 |

**成功响应（200）：** 同 3.3.1，返回**新的** `access_token` 与 `refresh_token`，旧 Refresh Token 作废。

**错误响应（400）：**

```json
{ "error": "invalid_grant", "error_description": "..." }
```

常见 `error` 值：`invalid_client`、`invalid_request`、`invalid_grant`、`unsupported_grant_type`。

---

### 3.4 GET `/auth/oauth2/userinfo`

用 Access Token 获取用户信息。**back-channel 调用**。

**请求头：**

```
Authorization: Bearer <access_token>
```

**成功响应（200，application/json）：**

```json
{
  "sub": "7",
  "name": "Mitchell Admin",
  "login": "admin",
  "email": "admin@example.com",
  "user_id": 7,
  "partner_id": 10,
  "company_id": 1,
  "company_name": "My Company",
  "groups": [
    { "id": 1, "name": "Settings / Administrator", "xml_id": "base.group_system" },
    { "id": 9, "name": "User / Internal User", "xml_id": "base.group_user" }
  ]
}
```

**错误响应（400）：**

```json
{ "error": "invalid_token", "error_description": "Invalid or expired access token" }
```

> Token 校验规则：存在、未被吊销（`revoked=False`）、且未过期（`expires_at > now`）。

---

### 3.5 GET `/auth/oauth2/logout`

销毁 Odoo SSO 会话并跳转。**需用户已登录（浏览器流程）**。

**查询参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `redirect_uri` | 否 | 退出后跳转地址，默认 `/web`。**必须在应用回调白名单内**，否则 fallback 到 `/web`（Odoo 登录页） |

**行为：** 清除 Odoo 会话（`request.session.logout()`），302 跳转到 `redirect_uri`。

---

## 4. 完整流程（Authorization Code Flow）

```
第三方应用                      用户浏览器                    Odoo SSO
   |                               |                            |
   | 1. 用户点击"登录"             |                            |
   |------------------------------>|                            |
   |                               | 2. GET /authorize          |
   |                               |    ?client_id&redirect_uri |
   |                               |    &response_type=code     |
   |                               |    &state=xxx              |
   |                               |--------------------------->|
   |                               | 3. [授权页/登录页]         |
   |                               |<-------------------------->|
   |                               | 4. POST /authorize         |
   |                               |    action=confirm&csrf...  |
   |                               |--------------------------->|
   |                               | 5. 302 redirect_uri       |
   |                               |    ?code=yyy&state=xxx     |
   |                               |<---------------------------|
   | 6. GET /callback?code=yyy     |                            |
   |<------------------------------|                            |
   |                               |                            |
   | 7. POST /token (code) --------|--------------------------->|
   |<---- {access_token, rt} ------|                            |
   |                               |                            |
   | 8. GET /userinfo (Bearer) --->|--------------------------->|
   |<---- {user info} -------------|                            |
   |                               |                            |
   | 9. 显示用户，建立本地会话      |                            |
```

- 步骤 2–5 为**前端（front-channel）**重定向，由浏览器完成。
- 步骤 7–8 为**后端（back-channel）**，由第三方应用服务端直接调用 Odoo，浏览器不可见。
- `state` 在步骤 2 生成、步骤 6 校验，用于防 CSRF。

---

## 5. curl 调用示例

### 换取 Token（授权码模式）

```bash
curl -X POST http://192.168.8.7:8069/auth/oauth2/token \
  -u "<client_id>:<client_secret>" \
  -d "grant_type=authorization_code" \
  -d "code=<AUTH_CODE>" \
  -d "redirect_uri=http://192.168.8.7:5000/callback"
```

### 刷新 Token

```bash
curl -X POST http://192.168.8.7:8069/auth/oauth2/token \
  -u "<client_id>:<client_secret>" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=<REFRESH_TOKEN>"
```

### 获取用户信息

```bash
curl http://192.168.8.7:8069/auth/oauth2/userinfo \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 6. 作用域（Scope）

当前实现中 `scope` 会被记录并随 Token / 授权码透传，userinfo 始终返回完整基础档案
（`sub`、`name`、`login`、`email`、`user_id`、`partner_id`、`company_id`、`company_name`，
以及用户所属的 Odoo 用户组 `groups`）。`groups` 中每一项包含：
- `id`：组记录 ID
- `name`：组的完整名称（`full_name`）
- `xml_id`：组的外部技术标识（如 `base.group_system`），无外部 ID 时为空字符串

客户端可依据 `xml_id` 做权限映射，因名称可能被翻译或改名。
默认作用域为 `openid profile`，可按需在应用配置中扩展为空格分隔的自定义值。

---

## 7. 安全说明

- **授权码**：5 分钟有效期、一次性使用，验证 `client_id` 与 `redirect_uri` 一致性。
- **Client Secret**：以 SHA-256 哈希存储，明文仅创建/重生成时展示一次。
- **Access Token**：默认 1 小时过期，可单独吊销（`sso.access.token` 的 Revoked）。
- **CSRF**：`/authorize` 的 GET/POST 为浏览器流程，POST 需携带 CSRF Token；
  `/token`、`/userinfo` 为 `auth='none'` 且 `csrf=False`，依赖 Bearer Token / Basic Auth 保护。
- 所有认证事件记录在 `sso.log` 审计日志中。

---

## 8. 可参考示例

`example/sso_client_example.py` 是一个完整的 Flask 第三方应用示例，演示上述全流程
（登录 / 回调 / 刷新 / 退出）。详见 `example/README.md`。
