# 扩展登录候选契约

保留 POST /api/v1/auth/login 和 logout。新增入口仅在服务端配置对应供应商后可用，供 M1 / M2 联调评审。

| 方法与路径（前缀 /api/v1/auth） | 请求 | 成功 |
| --- | --- | --- |
| GET /methods | 无 | 200 {"methods":["password","sms","github","wechat","school"]}（只列已启用项） |
| POST /sms/send | {"phone":"+8613800000000"} | 204 |
| POST /sms/login | {"phone":"+8613800000000","code":"123456"} | 200，沿用 LoginResponse |
| POST /oauth/{provider}/start | 无；provider 为 github / wechat / school | 200 {"authorizationUrl":"https://..."}，并设置 HttpOnly 流程 Cookie |
| POST /oauth/{provider}/exchange | {"code":"provider-code","state":"server-state"}，携带流程 Cookie | 200，沿用 LoginResponse |

OAuth 注册的回调 URL 指向 Web /login/{provider}，与 API 同源。Web 读取回调参数并立即移除 URL 中的授权码，再调用 exchange。登录凭证只出现在响应正文。回调状态一次性使用，5 分钟过期。GitHub 与学校流程使用 PKCE S256；学校同时校验 ID Token 签名、发行方、受众、有效期与 nonce。

启用方式由服务端配置。手机号必须为 E.164 格式。外部身份只匹配管理员预先配置的本地用户绑定，使用 GitHub 数字 ID、微信当前应用 openid、学校固定发行方的 sub 或已核验的手机号。通过登录不创建账号、不自动合并账号，也不采信外部角色。

使用统一错误响应。未启用返回 404，凭证或状态无效返回 401，限流返回 429，供应商不可用返回 503。所有登录响应禁止缓存。

## 本地联调配置

向 API **进程环境**提供 `AUTH_EXTERNAL_LOGIN`，内容为以下结构的 JSON。只配置实际启用的供应商。示例中的标识和密钥均为占位值。

```json
{
  "web_origin": "https://learning.example",
  "github": {"client_id":"example","client_secret":"replace-in-environment"},
  "wechat": {"client_id":"example-app-id","client_secret":"replace-in-environment"},
  "school": {
    "client_id":"example",
    "client_secret":"replace-in-environment",
    "issuer":"https://school.example",
    "authorization_endpoint":"https://school.example/authorize",
    "token_endpoint":"https://school.example/token",
    "public_key":"PEM RSA public key from school"
  },
  "sms": {
    "account_sid":"AC00000000000000000000000000000000",
    "service_sid":"VA00000000000000000000000000000000",
    "auth_token":"replace-in-environment"
  },
  "bindings": {
    "github":{"12345":"user_demo"},
    "wechat":{"example-openid":"user_demo"},
    "school":{"example-sub":"user_demo"},
    "sms":{"+15550100001":"user_demo"}
  }
}
```

- 使用独立随机 `AUTH_SESSION_SECRET` 和显式本地账号列表 `AUTH_SYNTHETIC_ACCOUNTS`，绑定目标须是列表中的用户 ID。当前用于受控联调，只填写合成账号，禁止把真实绑定、账号或凭证写入仓库。
- GitHub OAuth App 回调为 `<web_origin>/login/github`，微信开放平台网站应用回调为 `<web_origin>/login/wechat`，学校 OIDC 回调为 `<web_origin>/login/school`。学校当前支持 PKCE S256、`client_secret_basic` 和 RS256 单受众 ID Token，校方轮换签名公钥后需要更新配置。
- 短信使用专用 Twilio Verify Service。向中国大陆号码发码前需要完成 [Twilio 用途审核及注册](https://help.twilio.com/articles/17024185400859-Use-Case-Vetting-for-Verify-Messages-to-China)。服务端仅向已经绑定的号码发码，单进程按手机号限制发码和校验频率，短信有效期和校验由供应商管理。
- Vite 开发服务器默认把 `/api/v1/auth` 代理到 `127.0.0.1:8000`。API 改端口时，在 Vite 进程环境中设置 `AUTH_API_PROXY_TARGET`。部署时需让 Web 和 API 同源，回调路径由 SPA 接管，日志避免记录回调查询参数或供应商请求详情。OAuth 流程暂存在单个 API 进程，重启后要重新开始。
- 当前仍复用 S1 的会话签发与账号配置。待 PostgreSQL 底座与鉴权合入后，再将身份绑定、会话撤销和限流切换到共享存储。课程与答疑等既有 Mock 页面仍按各自联调任务接入。

参考 [GitHub OAuth](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)、[微信网站应用登录](https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html)、[OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html) 和 [Twilio Verify](https://www.twilio.com/docs/verify/api)。
