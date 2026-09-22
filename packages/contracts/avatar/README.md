# 数字人契约（M4 → M2）

本目录是「数字人组件」的对外契约，由 M4 提供，M2（学生端页面宿主）消费。
契约先于实现，目的是让提供方与调用方可以并行开发。

状态：**冻结**（Issue #33，2026-09-20）。M2（调用方）与 M3（emotion/action 映射与上游提供方）
已完成接口确认；`emotion` / `action` 枚举全集由 M4 在本目录冻结。
合并与后续变更仍按公共接口评审流程执行（见文末「变更流程」）。

## 文件

| 文件 | 内容 |
| --- | --- |
| [avatar-controller.md](avatar-controller.md) | `AvatarController` 接口、`speak` 结构化输入、播放事件、枚举全集、终止语义、降级与错误结构 |
| [samples/](samples/) | 手写场景样例，供 M2 / M4 对照实现与编写 Mock、测试 |

## 本契约形式化了哪些内容

本契约不是重新设计，而是把 `docs/code-standards.md` 已有的规定形式化。原文已明确的：

| 内容 | 原文出处 |
| --- | --- |
| M4 → M2：speak、stop()、状态与错误回调；语音/文字降级 | code-standards.md:91 |
| JSON 一律 camelCase | code-standards.md:48 |
| 枚举值小写 snake_case | code-standards.md:52 |
| 错误结构 `{code, message, requestId, details}` | code-standards.md:74-80 |
| 样例先于实现；Mock 必须明确标记 | code-standards.md:69；AGENTS.md:8 |

原文未覆盖、由本契约补齐的空白：

- `speak` 结构化输入 `{utteranceId, text, emotion, action}`——替代 code-standards.md:91 的 `speak(text)` 简写
- `AvatarEmotion` / `AvatarAction` 枚举全集（M4 冻结）
- `AvatarPlaybackStatus` 与四种 `avatar_playback_*` 事件
- `utteranceId` 语义，及其与 `requestId` 的区分
- 替换（`replaced`）、`stop()` 幂等、终止事件互斥
- 「只播报 tutoring `completed` 完整回答」的调用方约束
- 非法 `emotion` / `action` 的降级规则

## emotion / action 枚举已冻结

tutoring 契约在 [../tutoring/README.md](../tutoring/README.md)「仍待团队拍板」与
[../tutoring/tutoring-response.md](../tutoring/tutoring-response.md) 的占位表中，
等待 M4 给出正式枚举。本目录即冻结结果：

| 字段 | 冻结取值 |
| --- | --- |
| `emotion` | `neutral` / `encouraging` / `thinking` / `celebrating` |
| `action` | `idle` / `nod` / `point` / `write` |

冻结取值与 tutoring 契约的占位值一致，tutoring 数据结构本身无需变化；
其文档与样例中「占位值」表述的替换**由 M3 负责**
（见 [../tutoring/samples/README.md](../tutoring/samples/README.md)），不属于本 Issue 范围。

分工：**M4 定义枚举全集**；**M3 定义教学情境到取值的映射，并对模型输出做运行时校验**
（见 `docs/tasks/m4.md`「依赖与边界」）。

## 样例格式

样例是「场景对象」，不是 HTTP 报文：

- `scenario` / `description`：场景名与说明
- `calls`：按时间顺序排列的方法调用（`method` + 可选 `input`）
- `expectedEvents`：按分发顺序排列的完整事件序列
- 部分样例含 `expectedEffectiveInput`：降级后的实际渲染取值

**均为人工构造的示意数据，不是已实现功能的证据。**
`utteranceId` / `requestId` 的形态待 M1 统一 ID 约定，样例写法仅为示意。

| 文件 | 场景 |
| --- | --- |
| [01-speak.json](samples/01-speak.json) | 正常播报至完成 |
| [02-stop.json](samples/02-stop.json) | 播报中 `stop()`；重复 `stop()` 幂等 |
| [03-error-fallback.json](samples/03-error-fallback.json) | 播放失败：`started` 后发出 `avatar_playback_error`，文字回答继续保留 |
| [04-replaced.json](samples/04-replaced.json) | 播报中再次 `speak`，旧播报 `stopped`（`replaced`）后新播报完成 |
| [05-invalid-metadata-fallback.json](samples/05-invalid-metadata-fallback.json) | 非法 `emotion` / `action` 降级为 `neutral` / `idle`，播报照常完成 |

## Mock 声明

当前阶段为 **Mock**：不接入真实 TTS/ASR。契约只约束事件语义，
Mock 的计时策略是实现细节。Mock 实现不得作为生产完成证据（`AGENTS.md:8`）。

## 确认记录

| 事项 | 结论 | 确认方 / 日期 |
| --- | --- | --- |
| `speak` 结构化输入 `{utteranceId, text, emotion, action}` | 采用，替代 `speak(text)` 简写 | M2（调用方）/ 2026-09-20，Issue #33 |
| `emotion` / `action` 枚举全集 | M4 冻结上表取值 | M4（提供方）、M3（映射与上游提供方）/ 2026-09-20，Issue #33 |
| 终止语义（`replaced`、`stop()` 幂等、终止事件互斥）与降级规则 | 采用 | M2、M3 / 2026-09-20，Issue #33 |

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，公共接口变更需要至少 2 名评审人，
且必须包含 M2（调用方）与 M4（提供方）负责人。修改本目录前先与 M2 确认。

契约变更时需同步：本文档、[avatar-controller.md](avatar-controller.md)、
[samples/](samples/)。
