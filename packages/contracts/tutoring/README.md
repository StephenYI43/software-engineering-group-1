# Tutoring 契约（M3 → M2 / M4 / M5）

本目录是「AI 智能答疑」领域的对外契约，由 M3 提供，M2（学生端展示）、M4（数字人播报）、
M5（导学建议保存）消费。契约先于实现，目的是让调用方可以并行开发。

状态：**草案**。M2 已于 2026-09-15 通读全部文件与样例并给出确认，
其提出的四处补充已并入本次修订（见文末「修订记录」）；**仍待 M4 / M5 评审确认**。
确认前不应据此编写生产代码。

## 文件

| 文件 | 内容 |
| --- | --- |
| [tutoring-response.md](tutoring-response.md) | 一次答疑回答的数据结构、教学阶段枚举、引用结构、不变量 |
| [sse-events.md](sse-events.md) | 流式答疑的事件名、载荷、序号规则、终止语义 |
| [samples/](samples/) | 手写样例，供调用方对照实现与编写 Mock |

## 本契约新增了哪些内容

本契约不是重新设计，而是把 `docs/code-standards.md` 已有的规定形式化。原文已明确的：

| 内容 | 原文出处 |
| --- | --- |
| `stage` / `content` / `citations` / `followUps` / `emotion` / `action` | code-standards.md:90 |
| `thought` / `hint` / `step` / `summary` | code-standards.md:95 |
| SSE `started` / `delta` / `completed` / `error`、序号、停止行为 | code-standards.md:95 |
| 错误结构 `{code, message, requestId, details}` | code-standards.md:74-80 |
| JSON 一律 camelCase | code-standards.md:48 |
| 样例先于实现 | team-plan.md:41,59；code-standards.md:69 |

原文未覆盖、由本契约补齐的空白：

- `hasEvidence` 字段与「无依据」语义
- `isMock` 字段（假模型标记）
- `seq` 序号规则与终止事件唯一性
- `stopped` 终止态（用户中断）与 `completed` 的区别
- `citation` 对象的具体形状
- 请求体的 `extra="forbid"` 约束（客户端不得自行推进教学阶段）

## 仍待团队拍板

**`emotion` / `action` 的取值集合由 M4 冻结。**
`docs/tasks/m3.md:23` 写「（依赖）M4 情绪/动作枚举」，`docs/tasks/m4.md:23` 写
「（依赖）M3 回答文本与动作白名单」，两份文档互相矛盾。
本契约暂用**占位值**（见 tutoring-response.md 的取值表），M4 给出正式枚举后必须替换。
**在这些值冻结前，本契约不应被视为最终版。**

## 已确认事项

| 事项 | 结论 | 确认人 / 日期 |
| --- | --- | --- |
| HTTP 路径形状 | 采用会话嵌套式：`POST /api/v1/tutoring/sessions/{sessionId}/messages`、`POST /api/v1/tutoring/sessions/{sessionId}/turns/{turnId}/stop`。`docs/code-standards.md:47` 的 `/api/v1/study-plans` 是**命名形态**示例，不限制资源嵌套；前端据此刻板，不再返工 | M2 / 2026-09-15 |
| SSE 传输方式 | `fetch` + `ReadableStream`，**不使用** `EventSource` | M2 / 2026-09-15 |
| 断点续传 | S1 只支持整轮重试，不实现续传；`seq` 为将来的 `Last-Event-ID` 预留 | M2 / 2026-09-15 |

## 修订记录

### 2026-09-15：并入 M2 评审结论

M2 通读全部文件与样例后给出「三处确认 + 四处补充」。本次修订把结论落进契约：

| 改动 | 文件 |
| --- | --- |
| 补：服务端发起上游取消后**立即**下发 `stopped`，不等供应商确认 | [sse-events.md](sse-events.md) |
| 补：`error` 与 `stopped` 同构，**教学阶段不推进** | [sse-events.md](sse-events.md) |
| 补：前端实现责任（自行切帧、自行校验 `seq`、不用 `AbortController` 实现停止） | [sse-events.md](sse-events.md) |
| 补：停止的兜底超时为 **5 秒**（双方共同约定） | [sse-events.md](sse-events.md) |
| 改：删除「按实际来源如实标注」这一自相矛盾的表述 | [samples/README.md](samples/README.md) |
| 补：样例枚举同步的责任方明确为 **M3**，M4 冻结 `emotion`/`action` 后由 M3 统一替换 | [samples/README.md](samples/README.md) |
| 记：HTTP 路径、SSE 传输、不续传三项转为已确认 | 本文档 |

**未采纳 M2 的一处建议，理由如下**：他建议把样例的 `isMock` 统一改为 `true`。
但 `samples/04-error-model-output-invalid.json` 是 **HTTP 错误响应体**，
结构为 `{code, message, requestId, details}`（`docs/code-standards.md:74-80`、
`sse-events.md:113-125`），**不含** `isMock` 字段，加上会使其非法。
`05-sse-stream.txt` 变体三保留 `isMock: false`，因为它是前端实现「不显示 Mock 标识」
那条渲染路径的唯一样例。

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，公共接口变更需要至少 2 名评审人，
且必须包含相关领域负责人。修改本目录前先与 M2 / M4 / M5 确认。

契约变更时需同步：本文档、样例、以及（实现后的）OpenAPI 快照。
