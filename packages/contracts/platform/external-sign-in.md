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

启用方式由服务端配置。手机号必须为 E.164 格式。外部身份匹配管理员预先配置的本地用户绑定，使用 GitHub 数字 ID、微信当前应用 openid、学校固定发行方的 sub 或已核验的手机号。数据库模式从 external_identities 读取绑定。登录使用本地账号的角色。

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
- 配置 DATABASE_URL 后，身份绑定和会话使用 PostgreSQL，校验凭证时查询账号状态和当前主角色。OAuth 流程及短信限流仍存放在单个 API 进程。课程与答疑等既有 Mock 页面按各自联调任务接入。

## PostgreSQL 接入

在 API 进程中设置 DATABASE_URL，维护终端使用同一个地址。先运行迁移和受控开发种子，再绑定测试身份。

```powershell
uv run --locked alembic upgrade head
uv run --locked python -m app.core.db.seed --confirm-development
$githubId = gh api user --jq '.id'
uv run --locked python -m app.core.db.identities --provider github --issuer https://github.com --subject $githubId --user-id user_11111111111111111111111111111111
```

API 保持独立 AUTH_SESSION_SECRET。AUTH_EXTERNAL_LOGIN 中保留供应商配置，把 bindings 设为 {}。数据库内的用户 ID 须符合 user_ 加 32 位十六进制的格式，旧演示 ID user_github_test 要重新映射到受控种子账号。受控开发种子使用公开的演示密码，真实用户需要单独配置账号。

身份范围由 provider、issuer、subject 三元组确定。GitHub issuer 为 https://github.com，微信为 wechat: 加 appid，学校为校方 OIDC issuer 原文，手机号为 phone:e164。相同的学校 sub 在不同发行方下可属于不同账号。维护命令持有数据库权限，操作会生成系统审计记录。重复绑定同一用户是幂等的，绑定到其他用户会失败。

撤销绑定时在同一条维护命令末尾添加 --revoke。解绑会在同一个事务里撤销该用户的全部有效会话。再次绑定原用户可恢复登录，先前撤销的会话仍保持失效。

数据库模式下 API 启动只建立连接工厂，迁移、种子和身份维护均由显式命令执行。登录成功响应在会话与审计事务提交后返回。数据库停机时需恢复数据库连接，随后重试请求。

参考 [GitHub OAuth](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)、[微信网站应用登录](https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html)、[OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html) 和 [Twilio Verify](https://www.twilio.com/docs/verify/api)。
