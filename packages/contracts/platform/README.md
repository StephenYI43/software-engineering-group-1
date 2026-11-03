# 平台基础契约（M1 → 全员）

状态：候选草案，关联 Issue #11。健康检查与登录/凭证（Issue #45）已有开发骨架供验证；实体 ID 与错误结构尚未冻结，须经调用方评审。保留 M3 已合并的 tutoring 草案与样例。

## 已实现的健康检查候选行为

GET /api/v1/health 无需凭证，HTTP 200，Cache-Control: no-store：

```json
{"status":"ok","service":"learning-assistant-api","requestId":"req_0123456789ab4def8123456789abcdef"}
```

requestId 由服务端每次重新生成 req_ + UUIDv4 的 32 位小写十六进制，不采用客户端 X-Request-ID；响应头 X-Request-ID 与正文一致。格式见 [schema](health-response.schema.json)。
此端点不访问数据库或模型，不报告身份认证状态。未知路径返回下方统一错误结构。

## 实体 ID 提议（回应 M3 PR #9）

API 将实体 ID 当作不可解析的字符串，不能从中推断权限。建议新生成 ID 使用前缀 + UUIDv4.hex；数据库可使用 UUID 类型，转换由领域服务统一负责。

| 类型 | 候选前缀 | 负责方 |
| --- | --- | --- |
| 用户 | user_ | M1 |
| 班级 / 课程 | class_ / course_ | M5，M6 协作 |
| 文档 | doc_ | M3 |
| 答疑会话 / 回合 | sess_ / turn_ | M3 |
| 作业 / 提交 | assignment_ / submission_ | M5 |
| 复习计划 / 错题 | plan_ / mistake_ | M5 |
| 媒体任务 | media_ | M4 |
| 学习事件 | event_ | M6 协调各生产方 |
| 请求追踪 | req_ | M1，骨架已实现 |

citationId=c1/c2 是轮内标签，保持原约定，不作为实体主键。现有 M3 短后缀样例仍是示意数据，本 PR 不修改它们；在 M3/M5 确认格式之前不能批量替换或收紧其输入验证。

## 身份与权限

手机号验证码与第三方登录的配置、候选契约及限制见 [扩展登录](external-sign-in.md)。

角色 student/teacher/admin。服务端从已验证的会话获取 userId/role，不信任请求体或头里的自报角色。学生仅访问自己的私有学习记录；教师仅访问所属授课班级与课程；管理员权限须有明确授权和审计，不能靠客户端菜单控制。

资源不存在和无权访问可统一返回 404 防枚举，未登录 401。鉴权必须先于 RAG 检索，courseId 只能收窄已授权范围。开发期禁止可被外部请求激活的鉴权旁路。

### 登录与凭证（已实现，Issue #45，待调用方评审）

`POST /api/v1/auth/login`，请求体 `{"username", "password"}`；成功 200：

```json
{
  "token": "<jwt>",
  "tokenType": "bearer",
  "expiresAt": "2026-09-21T03:00:00+00:00",
  "user": { "userId": "user_11111111111111111111111111111111", "role": "student", "name": "学生甲" }
}
```

- 凭证为 HS256 会话 token，默认 24 小时（`AUTH_SESSION_TTL_SECONDS` 可调）
- 校验失败统一 401 `INVALID_CREDENTIALS`，不区分「用户名不存在」与「密码错误」（防枚举）
- `POST /api/v1/auth/logout` 以进程内吊销列表使凭证失效；幂等，不跨重启（S1 口径）
- 合成账号为演示数据，见 `docs/development.md`；`require_user` 等鉴权依赖消费本凭证（Issue #16）

### 服务端鉴权依赖（Issue #16）

- `require_user` 校验签名、有效期和吊销状态，从凭证读取主体；`require_teacher` 只允许教师。
- `require_owner` 比较主体与服务端查得的资源所有者。课程路由通过 `require_course_access` 接入 M5 的课程授权查询；查询未接入时返回 503，拒绝访问时返回 404。
- `resolve_user_summaries` 为进程内调用提供学生摘要，只返回服务端已授权名单中的学生 ID、姓名、学号（可空）。暂无公开摘要接口，当前数据为合成账号。

## 统一错误响应（Issue #46）

继续使用 code/message/requestId/details，匹配现有规范，内部堆栈与凭证不得进入响应。跨服务透传 requestId 需要后续可信调用策略；当前服务拒用外部 requestId，不能据此宣称实现了分布式追踪。

## 待确认事项

- [ ] M3/M5 确认 ID 格式和数据库到 API 映射
- [ ] M2/M6 确认健康检查和后续身份使用方式
- [ ] M4 确认媒体任务 ID，另在其模块冻结 emotion/action 枚举
- [ ] M1 在下一项实现前补完整登录/错误 schema 与安全测试计划

此清单未勾选即未确认，不以 AI 自评代替成员评审。
