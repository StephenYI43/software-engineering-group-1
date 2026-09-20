# Learning 契约（M5 → M2 / M3 / M6）

本目录是「学习业务后端」领域的对外契约，由 M5 提供。

- **消费方**：M2（学生端展示作业/错题/计划/提醒页面）、M3（生成导学建议后交 M5 校验保存）、
  M6（消费学习事件聚合统计，教师后台通过 M5 API 发布作业与课程）。
- **提供方**：M5。

状态：**草案 v2，已按 M1/M2/M3/M6 在 PR #26 的评审反馈修订，再次评审确认中**。
确认前不应据此编写生产代码。本契约与 [packages/contracts/tutoring/](../tutoring/) 同期立项，
沿用同一契约优先流程（`docs/code-standards.md:69`：实现前提交请求/响应/错误样例，由提供方与调用方共同评审）。

## 与 M1 脚手架的关系

M1 的 API 脚手架（原 PR #12，对应 Issue #11）**已合并到 main**，`apps/api/` 已就绪。
M5 的 S1 实现可在 `apps/api/app/domains/learning/` 下落地 router / schemas / service / repository 分层
（`docs/code-standards.md:33`），并在 `apps/api/migrations/` 下编写本契约对应表的迁移
（M5 协调迁移顺序，见 `docs/team-plan.md:27`）。

本契约只定义 JSON 契约与样例，**不含**数据库或业务代码实现。迁移与 service 实现按 S1 子 Issue 推进。

## 文件

| 文件 | 内容 |
| --- | --- |
| [courses.md](courses.md) | 课程、班级与章节的列表/详情/章节 API，权限边界，选课归属 |
| [homework.md](homework.md) | 作业发布、提交、幂等键生命周期与错题触发 |
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

- 课程/班级/章节/作业/提交/错题/计划的具体字段、状态枚举与不变量
- 作业提交的幂等键设计与**生命周期约定**（重复提交不重复收录）
- 错题收录的两条触发路径与「禁止问题一律归错题」的硬约束实现
- 计划从 M3 答疑建议到 M5 持久化对象的映射规则
- 学习事件的 `eventType` 取值集合（M5 发布侧）与 payload 形状

## 重要：ID 形态与待团队拍板项

> 本节列出在冻结前需要明确的点。每项标注**谁需要拍板**与**当前结论**。

1. **ID 形态：前缀 + UUIDv4.hex（32 位小写 hex）。**
   按 M1 在 PR #26 评审的硬要求，所有实体与事件示例 ID 统一采用 `<前缀>_<32 位小写 hex>` 形式
   （如 `course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6`），不再使用短后缀。
   ID 对调用方仍是**不透明字符串**，调用方不得解析前缀做权限或业务判断。
   前缀取值：`course_` / `class_` / `chapter_` / `assignment_` / `submission_` / `mistake_` / `plan_` / `plan_item_` / `reminder_` / `event_`。
   引用其他域的 ID（`user_` / `doc_` / `turn_` / `req_`）同样沿用 32 位 hex 后缀，最终以各域契约为准。

2. **课程与班级分离（M1 在 PR #26 评审第 1 条要求）。** course 不是 class：
   - `courses` 描述课程内容（高数上），`classes` 描述教学班（王老师的高数班）。
   - `assignments` / `submissions` 的访问边界落到 `classId`：学生只能看到自己所在班级的作业与提交。
   - S1 单班演示允许 `classId` 为空或默认单班；`courses` / `assignments` 增加可空 `classId` 字段，
     迁移与 ACL 在 S1 实现时由 M5 协调 M1（班级访问规则属 M1，见 code-standards.md:88）。
   - 详见 [courses.md](courses.md) 的 Course / Class 资源与 [homework.md](homework.md) 的 Assignment。

3. **选课 / 加入课程端点归属 M1。**
   `courses.md` 的列表返回「学生看到自己选的课」，但选课（加入班级）是访问关系写入，
   属 M1 的鉴权/访问规则域（code-standards.md:88 把课程/班级访问规则划给 M1）。
   **M5 不实现选课端点**，M2 的选课入口调 M1 提供的接口；M1 冻结选课端点路径后，本契约在
   `courses.md` 同步引用。当前 `courses.md` 已在「选课与班级 ACL」一节明确该边界。

4. **错题收录的「错答」判定来源。**
   `docs/tasks/m5.md:13`：「基于错误提交/主动确认幂等收录错题，禁止问题一律归错题」。
   `docs/team-plan.md:61`：「只有用户提交错误答案或明确标记错题时才收录」。
   两条触发路径：
   - **学生主动标记**：学生在作业详情或答疑后点「加入错题本」—— 服务端只需鉴权，无需判分。
   - **错答自动收录**：作业提交被判为错误时自动写入错题本——但**判分来源**未定：
     客观题（选择/填空）可由 M5 服务端对照 `answerKey` 自动判分；
     主观题需教师批阅（M6 教师端调用 M5 提交批阅结果）。
   本契约定义**两路径都支持**，自动路径以 `submission.isCorrect = false` 为触发条件，
   `isCorrect` 的计算来源在 `homework.md` 中标注为「待 M3/M6 确认判分权责」。

5. **M3 导学建议到 M5 计划的承载字段** —— ✅ **已确认**（Issue #17，M3 已回复）。
   M3 在 `TutoringResponse` 新增 `planSuggestion` 字段（可选，无建议时为 `null`），并提供服务端取用接口。
   **前端不参与转存**——学生在 M2 答疑界面点「保存为计划」后，前端只发 `sourceTurnId` 给 M5，
   M5 service 层按 `sourceTurnId` 调用 M3 取用接口拉取 `planSuggestion` 后保存
   （校验 `turnId` 归属与取内容合并为同一次调用，M3 对不归属 `turnId` 返回 404 防枚举）。
   `planSuggestion.items[].chapterId` 由 **M5 保存时**按学生当前课程/章节或 `knowledgePoint` 匹配填入，
   M3 在建议中传 `null`（章节是 M5 实体，M3 不生成 M5 域 ID，见 [study-plans.md](study-plans.md)「与 M3 的边界」）。
   M3 落地依赖：M3 待开 Issue 扩展 `tutoring-response.md`。

## 数据模型概览（对应表）

> 本节是契约的附属说明，**不是迁移脚本**。M5 在 `apps/api/migrations/` 下按本表结构编写迁移；
> 表名遵循 code-standards.md:49 的「复数表名、snake_case 列」。

| 表 | 主键 | 关键外键 | 归属 |
| --- | --- | --- | --- |
| `courses` | `id` | — | M5 |
| `classes` | `id` | `course_id`, `teacher_user_id` | M5 写、M1 维护访问关系 |
| `chapters` | `id` | `course_id` | M5 |
| `assignments` | `id` | `course_id`, `class_id?`, `chapter_id?` | M5 |
| `submissions` | `id` | `assignment_id`, `student_user_id`, `class_id?` | M5 |
| `mistakes` | `id` | `student_user_id`, `course_id`, `assignment_id?`, `submission_id?`, `source_turn_id?` | M5 |
| `study_plans` | `id` | `student_user_id`, `course_id?`, `chapter_id?` | M5 |
| `plan_items` | `id` | `plan_id` | M5 |
| `reminders` | `id` | `student_user_id`, `plan_id?`, `assignment_id?` | M5 |
| `learning_events` | `id` | `student_user_id` | M5 写、M6 读（跨领域，见 learning-events.md） |

`student_user_id` / `teacher_user_id` 引用 M1 的用户身份（code-standards.md:88 把用户身份划给 M1）。
**M5 不在 learning 表内存储用户姓名/角色**，需要展示时按 M1 的用户接口解析；教师批阅列表的
最小学生摘要（`StudentSummary`）由服务端在响应时组合，不持久化在 `submissions` 表（见 [homework.md](homework.md)）。

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，公共接口变更需要至少 2 名评审人，
且必须包含相关领域负责人。修改本目录前先与 M2 / M3 / M6 确认。

契约变更时需同步：本文档、对应领域文档、样例、以及（实现后的）OpenAPI 快照。
