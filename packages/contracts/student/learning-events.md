# 学生端学习事件契约（M2 → M6，S1）

本文定义 M2 学生页面触发的学习事件。S1 只冻结已经被上游契约点名的
`chapter_viewed`，不提前扩张点击、停留时长等事件。

## 发布边界

浏览器**不直接写** `learning_events`，也不提交完整规范事件。页面仅在章节正文已经成功渲染、
页面处于可见状态后，通过受鉴权的服务端接口提交最小 `ChapterViewedIntent`：

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `courseId` | string | 否 | 当前课程 ID；服务端必须校验访问权 |
| `chapterId` | string | 否 | 当前章节 ID；服务端必须校验其属于 `courseId` |
| `idempotencyKey` | string | 否 | 一次真实浏览动作的稳定重试键；网络重试必须复用 |

服务端完成鉴权和资源归属校验后，才把意图转换为规范事件并追加到
`learning_events`。职责边界如下：

- `userId` 来自服务端认证上下文，客户端不能传入或覆盖；
- `eventId`、`occurredAt`、`traceId`、`schemaVersion` 由服务端生成；
- `courseId` / `chapterId` 必须通过课程访问权和父子归属校验；越权资源按平台统一策略返回 404；
- 同一 `(userId, idempotencyKey)` 只生成一个规范事件，重试返回原结果；
- 前端不得调用通用“自选 `eventType`”入口，避免伪造其他领域事件。

S1 不支持离线积压后跨会话补传。上报失败不阻塞章节阅读；页面可做有上限的网络重试，
但必须复用同一 `idempotencyKey`。具体 HTTP 路径由 M1 / M5 在实现任务中冻结，本契约不越权指定
API 路由或数据库归属。

## 规范事件公共字段

下列六个字段与 M5 的
[学习事件契约](../learning/learning-events.md#公共字段所有事件必填)保持相同字段名、类型和可空性；
六个字段均为必填且不可为 `null`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `eventId` | string | `event_` + 32 位小写 hex（UUIDv4.hex），全局唯一 |
| `eventType` | string | 本文当前仅允许 `chapter_viewed` |
| `userId` | string | 学生用户 ID（事件主体），从认证上下文取得 |
| `occurredAt` | string | UTC ISO 8601；M2 行为事件以服务端接受并验证意图的时间为准 |
| `traceId` | string | 关联 M1 requestId，便于跨服务追踪 |
| `schemaVersion` | string | 初版固定为 `1.0` |

规范事件还包含 M5 已定义的公共 envelope 字段：

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `courseId` | string \| null | 是 | 通用 envelope 允许为空；`chapter_viewed` 必须为非空字符串 |
| `payload` | object | 否 | 事件特有字段，见下节 |

客户端提交时间和客户端时钟不进入规范事件。这样可避免设备时钟漂移或延迟补传制造倒序时间；
但 M6 仍应使用数据库写入顺序上的单调 ingestion cursor，不能把 `occurredAt` 当作不会迟到的写入游标。

## `chapter_viewed`

触发时机：章节正文已成功渲染，且文档处于可见状态。以下情况不发布：

- 仅点击导航但章节请求失败；
- 路由预取、后台预加载或隐藏标签页渲染；
- 同一次页面挂载导致的重复 effect；
- 服务端鉴权或章节归属校验失败。

规范事件：

| 字段 | 约束 |
| --- | --- |
| `eventType` | 常量 `chapter_viewed` |
| `courseId` | 非空，且与章节所属课程一致 |
| `payload.chapterId` | string，必填且不可为 `null` |

每次学生主动进入章节可形成一次新的浏览动作；同一浏览动作的重试不得重复计数。刷新或离开后再次进入
是否算新动作，由页面生成新的 `idempotencyKey` 明确表达，而不是由 M6 猜测或按时间窗口去重。

## 样例

- [客户端意图](samples/01-chapter-viewed-intent.json)
- [服务端规范事件](samples/02-chapter-viewed-event.json)

样例仅使用合成 ID，不含真实学生资料。

## 隐私与禁止字段

事件只记录统计所需的 ID。禁止在 `payload` 或日志中加入：

- 学生姓名、学号、邮箱、手机号等直接身份信息；
- 章节标题、正文、题目、答案、完整对话或录音；
- 页面完整 URL、查询参数、浏览器指纹或未经同意的设备标识；
- 访问令牌、Cookie 或其他凭据。

M6 如需展示姓名，应通过获授权的平台接口解析 `userId`，不能从事件复制身份资料。

## 版本与兼容性

- 新增可选 payload 字段可保持 `schemaVersion: "1.0"`，但消费方不得因此失败；
- 删除字段、改变含义或改变可空性属于破坏性变更，必须升级版本并与 M6 协调迁移；
- 新事件类型需单独补充触发语义、payload、样例、隐私检查和消费方确认。

## 待评审确认

- [ ] M1：身份来源、requestId/traceId、ID 形态和 404 防枚举规则一致；
- [ ] M5：服务端接收意图与 `learning_events` 写入边界可实现；
- [ ] M6：`chapter_viewed` schema、幂等语义和时间语义可消费；
- [ ] 至少 2 名非作者评审后才可合并。
