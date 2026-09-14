# Tutoring 契约（M3 → M2 / M4 / M5）

本目录是「AI 智能答疑」领域的对外契约，由 M3 提供，M2（学生端展示）、M4（数字人播报）、
M5（导学建议保存）消费。契约先于实现，目的是让调用方可以并行开发。

状态：**草案，待 M2 / M4 / M5 评审确认**。确认前不应据此编写生产代码。

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

## 重要：两处仍待团队拍板

1. **`emotion` / `action` 的取值集合由 M4 冻结。**
   `docs/tasks/m3.md:23` 写「（依赖）M4 情绪/动作枚举」，`docs/tasks/m4.md:23` 写
   「（依赖）M3 回答文本与动作白名单」，两份文档互相矛盾。
   本契约暂用**占位值**（见 tutoring-response.md 的取值表），M4 给出正式枚举后必须替换。
   **在这些值冻结前，本契约不应被视为最终版。**

2. **HTTP 路径形状待 M2 确认。**
   本文档暂用 `/api/v1/tutoring/sessions/...`（领域命名空间形式）。
   `docs/code-standards.md:47` 给的是 `/api/v1/study-plans`（纯复数名词形式）。
   两种都符合规范精神，但必须二选一并让 M2 确认，因为前端会硬编码这个路径。

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，公共接口变更需要至少 2 名评审人，
且必须包含相关领域负责人。修改本目录前先与 M2 / M4 / M5 确认。

契约变更时需同步：本文档、样例、以及（实现后的）OpenAPI 快照。
