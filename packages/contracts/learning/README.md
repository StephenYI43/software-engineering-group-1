# Learning 契约（M5 → M2 / M3 / M6）

本目录是「学习业务后端」领域的对外契约，由 M5 提供。

- **消费方**：M2（学生端展示作业/错题/计划/提醒页面）、M3（生成导学建议后交 M5 校验保存）、
  M6（消费学习事件聚合统计，教师后台通过 M5 API 发布作业与课程）。
- **提供方**：M5。

状态：**草案，待 M2 / M3 / M6 评审确认**。确认前不应据此编写生产代码。
本契约与 [packages/contracts/tutoring/](../tutoring/) 同期立项，沿用同一契约优先流程
（`docs/code-standards.md:69`：实现前提交请求/响应/错误样例，由提供方与调用方共同评审）。

## 与 M1 脚手架的关系

截至本契约提交时，`apps/api/` 脚手架仍在 `codex/feat/m1-api-bootstrap` 分支
（PR 未合并到 main）。**本契约不假定脚手架已存在**（`AGENTS.md:2`），
只定义 JSON 契约与样例。等 M1 的 PR 合并后，M5 才在 `apps/api/app/domains/learning/`
下落地 router / schemas / service / repository 分层（`docs/code-standards.md:33`），
并在 `apps/api/migrations/` 下编写本契约对应表的迁移（M5 协调迁移顺序，见 `docs/team-plan.md:27`）。

## 文件

| 文件 | 内容 |
| --- | --- |
| [courses.md](courses.md) | 课程与章节的列表/详情/章节 API，权限边界 |
| [homework.md](homework.md) | 作业发布、提交、幂等与错题触发 |
| [mistakes.md](mistakes.md) | 错题本：仅错答或学生主动标记才收录，幂等去重 |
| [study-plans.md](study-plans.md) | 复习计划保存（M3 建议 → M5 校验保存）、可编辑、站内截止提醒 |
| [learning-events.md](learning-events.md) | M5 发布给 M6 的学习事件 schema |
| [samples/](samples/) | 手写样例，供调用方对照实现与编写 Mock |

## 本契约新增了哪些内容

本契约不是重新设计，而是把 `docs/code-standards.md` 已有的规定形式化。原文已明确的：

| 内容 | 原文出处 |
| --- | --- |
| API 路径小写复数名词、kebab-case | code-standards.md:47 |
| JSON 字段一律 camelCase | code-standards.md:48 |
| 表名复数、列 snake_case；主键 `id`、外键 `实体_id` | code-standards.md:49-50 |
| 时间字段 `created_at` / `updated_at` 等，UTC ISO 8601 | code-standards.md:51,55 |
| 列表分页 `page` / `pageSize`，返回 `items` / `total` / `page` / `pageSize` | code-standards.md:71 |
| 错误结构 `{code, message, requestId, details}` | code-standards.md:74-80 |
| 状态码：401 / 403 / 404 / 409 / 422 / 429 | code-standards.md:82 |
| 越权访问返回 404 而非 403（防枚举） | code-standards.md:82 |
| 异步解析返回 202 + jobId，状态查询接口，幂等 | code-standards.md:82 |
| M5 → M2/M6：课程章节、作业提交、错题、计划、提醒 | code-standards.md:89 |
| M2/M4/M5 → M6：学习事件 eventId/eventType/userId/occurredAt/traceId/schemaVersion | code-standards.md:92 |
| 跨领域走公开服务函数或事件，不直接写其他模块的表 | code-standards.md:33 |
| 数据写入使用事务；迁移需从 main 现有 schema 升级验证；已合并迁移不回改 | code-standards.md:64 |

原文未覆盖、由本契约补齐的空白：

- 课程/章节/作业/提交/错题/计划的具体字段、状态枚举与不变量
- 作业提交的幂等键设计（重复提交不重复收录）
- 错题收录的两条触发路径与「禁止问题一律归错题」的硬约束实现
- 计划从 M3 答疑建议到 M5 持久化对象的映射规则
- 学习事件的 `eventType` 取值集合（M5 发布侧）与 payload 形状

## 重要：四处仍待团队拍板

> 在以下四项冻结前，本契约不应被视为最终版。每项都标注了**谁需要拍板**与**为什么卡住**。

1. **ID 形态：是否沿用 M3 在 `tutoring-response.md` 中给出的 `<前缀>_<不透明后缀>` 形式。**
   M3 已为 `courseId` 给出示例 `course_b3f1c2d4`，但明确标注「待 M1 的共享基础契约确认」。
   本契约**沿用同一写法**以保持一致：`course_` / `chapter_` / `assignment_` / `submission_` / `mistake_` / `plan_` / `reminder_` / `event_` 前缀。
   **最终以 M1 的共享基础契约为准**，M1 冻结后本契约同步替换。

2. **课程创建/作业发布的 API 归属：M5 提供 API、M6 提供教师 UI。**
   `docs/team-plan.md:24` 把「学习业务后端」划给 M5，把「教师后台」划给 M6。
   `docs/team-plan.md:29` 进一步写「M6 自行实现教师端，不把所有 UI 工作交给 M2」。
   因此**业务 API 由 M5 提供，教师入口 UI 由 M6 实现**，M6 通过 M5 API 操作。
   本契约据此定义 `POST /api/v1/courses` 与 `POST /api/v1/assignments` 由 M5 实现，
   但鉴权层只允许 `teacher` / `admin` 角色调用（角色规则由 M1 定义，见 code-standards.md:88）。
   **需 M6 确认教师端调用的路径形态与字段需求。**

3. **错题收录的「错答」判定来源。**
   `docs/tasks/m5.md:13`：「基于错误提交/主动确认幂等收录错题，禁止问题一律归错题」。
   `docs/team-plan.md:61`：「只有用户提交错误答案或明确标记错题时才收录」。
   两条触发路径：
   - **学生主动标记**：学生在作业详情或答疑后点「加入错题本」—— 服务端只需鉴权，无需判分。
   - **错答自动收录**：作业提交被判为错误时自动写入错题本—— 但**判分来源**未定：
     客观题（选择/填空）可由 M5 服务端对照 `answerKey` 自动判分；
     主观题需教师批阅（M6 教师端调用 M5 提交批阅结果）。
   本契约暂定义**两路径都支持**，自动路径以 `submission.isCorrect = false` 为触发条件，
   `isCorrect` 的计算来源在 `homework.md` 中标注为「待 M3/M6 确认判分权责」。

4. **M3 导学建议到 M5 计划的承载字段**——✅ **已确认**（Issue #17，M3 已回复）。
   M3 在 `TutoringResponse` 新增 `planSuggestion` 字段（可选，无建议时为 `null`），并提供服务端取用接口。
   **前端不参与转存**——学生在 M2 答疑界面点「保存为计划」后，前端只发 `sourceTurnId` 给 M5，
   M5 service 层按 `sourceTurnId` 调用 M3 取用接口拉取 `planSuggestion` 后保存
   （校验 `turnId` 归属与取内容合并为同一次调用，M3 对不归属 `turnId` 返回 404 防枚举）。
   `planSuggestion` 字段形状与 M5 保存路径细节见 [study-plans.md](study-plans.md)「与 M3 的边界」一节。
   M3 落地依赖：M3 待开 Issue 扩展 `tutoring-response.md`。

## 数据模型概览（对应表）

> 本节是契约的附属说明，**不是迁移脚本**。等 M1 脚手架合并后，M5 在 `apps/api/migrations/` 下
> 按本表结构编写迁移；表名遵循 code-standards.md:49 的「复数表名、snake_case 列」。

| 表 | 主键 | 关键外键 | 归属 |
| --- | --- | --- | --- |
| `courses` | `id` | — | M5 |
| `chapters` | `id` | `course_id` | M5 |
| `assignments` | `id` | `course_id`, `chapter_id?` | M5 |
| `submissions` | `id` | `assignment_id`, `student_user_id` | M5 |
| `mistakes` | `id` | `student_user_id`, `assignment_id?`, `submission_id?`, `source_turn_id?` | M5 |
| `study_plans` | `id` | `student_user_id`, `course_id?`, `chapter_id?` | M5 |
| `plan_items` | `id` | `plan_id` | M5 |
| `reminders` | `id` | `student_user_id`, `plan_id?`, `assignment_id?` | M5 |
| `learning_events` | `id` | `student_user_id` | M5 写、M6 读（跨领域，见 learning-events.md） |

`student_user_id` / `teacher_user_id` 引用 M1 的用户身份（code-standards.md:88 把用户身份划给 M1）。
**M5 不在 learning 表内存储用户姓名/角色**，需要展示时按 M1 的用户接口解析。

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，公共接口变更需要至少 2 名评审人，
且必须包含相关领域负责人。修改本目录前先与 M2 / M3 / M6 确认。

契约变更时需同步：本文档、对应领域文档、样例、以及（实现后的）OpenAPI 快照。
