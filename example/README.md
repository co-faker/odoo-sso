# SSO Client Example

一个模拟第三方应用通过 OAuth2 接入 Odoo SSO 的示例网站。

## 前置条件

- Odoo 已安装并启动 `sso` 模块
- Python 3.8+
- pip

## 快速开始

### 1. 安装依赖

```bash
pip install flask requests
```

### 2. 在 Odoo 后台创建 SSO 应用

1. 登录 Odoo 后台（系统管理员）
2. 进入 **SSO → SSO Applications**
3. 点击 **创建**
4. 填写：
   - **Application Name**: `SSO Client Example`
   - **Approval Prompt**: `Auto`（或 `Force`，按需选择）
   - **Redirect URIs**: 添加 `http://localhost:5000/callback`
5. 点击 **保存**
6. 点击 **Generate New Secret** 生成密钥
7. 复制 **Client ID** 和 **Client Secret**

### 3. 配置并运行

编辑 `sso_client_example.py`，修改文件顶部的 `CONFIG`：

```python
CONFIG = {
    "ODOO_SSO_BASE": "http://localhost:8069",   # Odoo 服务地址
    "CLIENT_ID": "sso_xxx...",                   # 上一步复制的 Client ID
    "CLIENT_SECRET": "xxx...",                   # 上一步复制的 Client Secret
    "REDIRECT_URI": "http://localhost:5000/callback",
    "PORT": 5000,
}
```

运行：

```bash
python sso_client_example.py
```

### 4. 访问

浏览器打开 `http://localhost:5000`

## 测试流程

```
1. 打开 http://localhost:5000
2. 点击 "通过 Odoo 登录"
3. 跳转到 Odoo SSO 授权页（如未登录 Odoo，先输入账号密码）
4. 点击 "Authorize" 确认授权
5. 自动跳转回示例网站，显示用户信息
```

## 功能说明

| 路由 | 说明 |
|------|------|
| `/` | 首页，显示用户信息或登录按钮 |
| `/login` | 跳转到 Odoo SSO 授权页 |
| `/callback` | OAuth2 回调地址，用授权码换取 Token 并获取用户信息 |
| `/refresh` | 手动刷新 Access Token |
| `/logout` | SSO 退出登录（同时清除本地 Session） |

## 完整 OAuth2 流程

```
用户                   示例网站                    Odoo SSO
 |                       |                          |
 |  点击"通过Odoo登录"    |                          |
 |---------------------->|                          |
 |                       |  GET /authorize          |
 |                       |  ?client_id&redirect_uri |
 |                       |  &response_type=code     |
 |                       |  &state=xxx              |
 |                       |------------------------->|
 |                       |                          |
 |  [Odoo 登录页/授权页]  |                          |
 |<------------------------------------------------>|
 |                       |                          |
 |  确认授权              |                          |
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
 |  显示用户信息           |                          |
 |<----------------------|                          |
```

## 注意事项

- 确保 Odoo 服务地址可从示例网站所在机器访问
- 回调地址必须与 Odoo 后台配置的完全一致（包括端口）
- 如使用 `Force` 模式，每次授权都需要用户确认
- 如使用 `Auto` 模式，同一用户再次授权时会自动跳过确认页
- **关于退出登录**：示例中 `/logout` 会同时退出 Odoo SSO 会话并返回示例网站主页。Odoo 的 `/auth/oauth2/logout` 要求 `redirect_uri` 必须在该应用的**回调白名单**中，否则会 fallback 到 Odoo 登录页。示例默认用 `REDIRECT_URI` 去掉 `/callback` 得到的主页地址（如 `http://192.168.8.7:5000/`）作为返回地址，请在 Odoo 后台该 SSO 应用的 **Redirect URIs** 中**额外添加此主页地址**，退出后才能正确返回示例主页。
