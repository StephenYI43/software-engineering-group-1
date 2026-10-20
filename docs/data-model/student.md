# 学生端字段映射与偏好归属（M2）

关联 [#70](https://github.com/StephenYI43/software-engineering-group-1/issues/70)、[#69](https://github.com/StephenYI43/software-engineering-group-1/issues/69)。
owner：M2 / @Saber-www；评审：M1、M5。
基线：`main` `d01f32e`；格式参照 PR #73 head `c71de57`（**未合并**，本文件不声称模板已在 main）。
状态：**字段映射草案。本文件不登记新表**，不建迁移、不改 API、不改其他 owner 的字典。

本文回答四件事：学生端每个字段从哪来、落到哪张表的哪一列（或为什么不落库）、由谁拥有、
现在是真数据还是示意数据。七要素字典按 owner 分文件，M2 只做映射与归属判定。

## 0. 口径

### 0.1 两条不同的状态轴：契约冻结 ≠ 列冻结

| 轴       | 取值                                                | 含义                                                |
| -------- | --------------------------------------------------- | --------------------------------------------------- |
| 契约状态 | `已冻结` / `已合入，待确认` / `待定(Qn)` / `无契约` | 字段约定及提供方/调用方确认状态；合并不自动等于冻结 |
| 列状态   | `已登记` / `候选` / `未登记` / `不适用`             | 该列是否已出现在某份数据字典里                      |

`已登记` 指领域 owner 已确认的字典表列；`候选` 包括尚待评审的领域草案，或按
`docs/code-standards.md:49`（复数表名、snake_case 列）从 JSON 字段推导，**等对应 owner 的字典合并后才算数**。

> 当前事实：main 上**没有任何学生端相关表列被登记**。`learning` 只有契约附带的表概览；
> `platform` 的七表在未合并的 #73/#75；`tutoring` 九表草案已提交 #76，待修订/合入；`avatar`/`analytics` 字典尚未提交。
> 因此本文绝大多数列状态是 `候选`——这不是保守写法，是当前仓库的真实状态。

已合并的 learning 契约沿用其既有评审确认口径，不因 README 的历史草案文字重新撤销确认。
学生事件单独记录为「已合入，M5 批准；待 M1/M6 确认」：见 [PR #56](https://github.com/StephenYI43/software-engineering-group-1/pull/56) 的 M5 review 与 [#30](https://github.com/StephenYI43/software-engineering-group-1/issues/30) 的确认记录；当前未见 M1/M6 的明确答复。字段定义存在、契约确认完成、物理列登记是三件不同的事。

### 0.2 来源五档

| 取值       | 含义                                              |
| ---------- | ------------------------------------------------- |
| `fixture`  | 前端示意数据，界面带「示意数据」标识              |
| `真实API`  | 已接通后端并取到真实响应（当前学生端为 **0 项**） |
| `未实现`   | 只有契约、没有代码通路                            |
| `响应组合` | 由服务端按引用/聚合拼出的字段，本身不落库         |
| `运行时`   | 浏览器内状态，服务端不保存                        |

「未实现」说的是**没有代码**，不是「服务端不落库」；两者在下面分开标注，不要混读。

### 0.3 本文不做的事

- 不替 M3/M5 定列名、表名（`候选` 就是候选，不因写进表格而变成已确认）；
- 不替 M3 决定中断轮次的正文存哪里（Q8）；
- 不建用户/事件/课程/偏好表，也不为凑板块重复登记业务表；
- 不把「浏览器不保存」写成「服务端不落库」（见第 3 节）。

## 1. 页面现状与数据来源

| 路由                   | 页面/能力           | main 现状                  | 数据入口                                            | 契约端点                                       | 后端实现                               |
| ---------------------- | ------------------- | -------------------------- | --------------------------------------------------- | ---------------------------------------------- | -------------------------------------- |
| `/courses`             | 课程列表            | 已实现（S0，fixture）      | `features/student/api/courses-client.ts` → `mocks/` | `GET /api/v1/courses`                          | M5，未实现                             |
| `/courses/:courseId`   | 课程详情 + 章节列表 | 已实现（S0，fixture）      | `features/student/api/courses-client.ts` → `mocks/` | `GET /courses/{id}`、`/chapters`               | M5，未实现                             |
| `/tutoring/:sessionId` | 答疑（单轮展示）    | 已实现（S0，fixture）      | `mocks/` 的 `fetchTutoringTurn`                     | `POST /tutoring/sessions/{id}/messages`（SSE） | M3：#62 未合并；M2 的 SSE 客户端在 #68 |
| 章节正文               | 阅读页              | **未实现**（只有章节列表） | —                                                   | `ChapterViewedIntent`                          | M5/M1，路径未冻结                      |
| 作业列表/详情/提交     | 作业                | **未实现**                 | —                                                   | `/courses/{id}/assignments` 等                 | M5，未实现                             |
| 错题本                 | 错题                | **未实现**                 | —                                                   | `/api/v1/mistakes`                             | M5，未实现                             |
| 复习计划/提醒          | 计划                | **未实现**                 | —                                                   | `/api/v1/study-plans`、`/reminders`            | M5，未实现                             |
| 数字人播报             | 组件                | **未接线**                 | —                                                   | `AvatarController`（组件契约）                 | M4：#61 未合并                         |

## 2. 逐页字段映射

列说明：`契约状态`、`列状态` 见 0.1；`来源` 见 0.2。

### 2.1 课程列表 `/courses`

依据：`packages/contracts/learning/courses.md` 的 Course 与分页响应。

| 前端字段               | JSON 契约字段   | 领域表.列                                             | owner | 契约状态 | 列状态 | 来源     |
| ---------------------- | --------------- | ----------------------------------------------------- | ----- | -------- | ------ | -------- |
| `Course.id`            | `id`            | `courses.id`                                          | M5    | 已冻结   | 候选   | fixture  |
| `Course.title`         | `title`         | `courses.title`                                       | M5    | 已冻结   | 候选   | fixture  |
| `Course.description`   | `description`   | `courses.description`                                 | M5    | 已冻结   | 候选   | fixture  |
| `Course.subject`       | `subject`       | `courses.subject`                                     | M5    | 已冻结   | 候选   | fixture  |
| `Course.coverImageUrl` | `coverImageUrl` | `courses.cover_image_url`                             | M5    | 已冻结   | 候选   | fixture  |
| `Course.teacherId`     | `teacherId`     | `courses.teacher_id`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.createdAt`     | `createdAt`     | `courses.created_at`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.updatedAt`     | `updatedAt`     | `courses.updated_at`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.teacherName`   | `teacherName`   | 响应组合：`user_profiles.display_name`（PR #73 候选） | M1    | 已冻结   | 候选   | 响应组合 |
| `Course.studentCount`  | `studentCount`  | 响应组合：选课关系计数，物理表列待 M5（Q1/Q2）        | M5    | 已冻结   | 未登记 | fixture  |
| `Course.chapterCount`  | `chapterCount`  | 响应组合：按 `chapters.id` 计数（Q2）                 | M5    | 已冻结   | 不适用 | fixture  |
| 分页页码               | `page`          | 不适用                                                | —     | 已冻结   | 不适用 | fixture  |
| 分页大小               | `pageSize`      | 不适用                                                | —     | 已冻结   | 不适用 | fixture  |
| 分页总数               | `total`         | 不适用                                                | —     | 已冻结   | 不适用 | fixture  |

要点：

- `teacherName` 不存入课程行，由服务端按 `courses.teacher_id` 组合 M1 资料；前端处理 `null`。
- `studentCount` / `chapterCount` 契约只写「可回填」。建议查询聚合（Q2），不在本文登记物化列。
- `subject` 未知取值回退显示原值，不产生持久化字段。

### 2.2 课程详情与章节 `/courses/:courseId`

课程详情使用同一 Course 契约，以下仍逐字段列出，逐项给出物理候选与响应组合来源。

| 前端字段               | JSON 契约字段   | 领域表.列                                             | owner | 契约状态 | 列状态 | 来源     |
| ---------------------- | --------------- | ----------------------------------------------------- | ----- | -------- | ------ | -------- |
| `Course.id`            | `id`            | `courses.id`                                          | M5    | 已冻结   | 候选   | fixture  |
| `Course.title`         | `title`         | `courses.title`                                       | M5    | 已冻结   | 候选   | fixture  |
| `Course.description`   | `description`   | `courses.description`                                 | M5    | 已冻结   | 候选   | fixture  |
| `Course.subject`       | `subject`       | `courses.subject`                                     | M5    | 已冻结   | 候选   | fixture  |
| `Course.coverImageUrl` | `coverImageUrl` | `courses.cover_image_url`                             | M5    | 已冻结   | 候选   | fixture  |
| `Course.teacherId`     | `teacherId`     | `courses.teacher_id`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.createdAt`     | `createdAt`     | `courses.created_at`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.updatedAt`     | `updatedAt`     | `courses.updated_at`                                  | M5    | 已冻结   | 候选   | fixture  |
| `Course.teacherName`   | `teacherName`   | 响应组合：`user_profiles.display_name`（PR #73 候选） | M1    | 已冻结   | 候选   | 响应组合 |
| `Course.studentCount`  | `studentCount`  | 响应组合：选课关系计数，物理表列待 M5（Q1/Q2）        | M5    | 已冻结   | 未登记 | fixture  |
| `Course.chapterCount`  | `chapterCount`  | 响应组合：按 `chapters.id` 计数（Q2）                 | M5    | 已冻结   | 不适用 | fixture  |

| 前端字段              | JSON 契约字段 | 领域表.列                                          | owner         | 契约状态 | 列状态 | 来源    |
| --------------------- | ------------- | -------------------------------------------------- | ------------- | -------- | ------ | ------- |
| `Chapter.id`          | `id`          | `chapters.id`                                      | M5            | 已冻结   | 候选   | fixture |
| `Chapter.courseId`    | `courseId`    | `chapters.course_id`                               | M5            | 已冻结   | 候选   | fixture |
| `Chapter.title`       | `title`       | `chapters.title`                                   | M5            | 已冻结   | 候选   | fixture |
| `Chapter.order`       | `order`       | `chapters.order`                                   | M5            | 已冻结   | 候选   | fixture |
| `Chapter.description` | `description` | `chapters.description`                             | M5            | 已冻结   | 候选   | fixture |
| `Chapter.createdAt`   | `createdAt`   | `chapters.created_at`                              | M5            | 已冻结   | 候选   | fixture |
| `Chapter.updatedAt`   | `updatedAt`   | `chapters.updated_at`                              | M5            | 已冻结   | 候选   | fixture |
| `Chapter.documentId`  | `documentId`  | `chapters.document_id` → `documents.id`（M3 候选） | M5（引用 M3） | 已冻结   | 候选   | fixture |
| 章节正文              | 无契约字段    | 无已定义的正文响应与物理列；待 M3 定稿             | M3            | 无契约   | 未登记 | 未实现  |
| 分页页码              | `page`        | 不适用                                             | —             | 已冻结   | 不适用 | fixture |
| 分页大小              | `pageSize`    | 不适用                                             | —             | 已冻结   | 不适用 | fixture |
| 分页总数              | `total`       | 不适用                                             | —             | 已冻结   | 不适用 | fixture |

`chapters.document_id` 只引用文档，不含正文，也不授予阅读权。文档授权的物理模型待 M3/M1 定稿，
本文不将候选授权表当作已存在事实。章节/文档删除策略见 Q3。

### 2.3 章节浏览事件（阅读页未实现）

契约状态：**已合入，M5 批准；待 M1/M6 确认**（[PR #56](https://github.com/StephenYI43/software-engineering-group-1/pull/56)、[#30](https://github.com/StephenYI43/software-engineering-group-1/issues/30)）。
下表区分客户端 intent 与服务端规范事件；规范事件不是由浏览器构造。

| 前端字段                | JSON 契约字段       | 领域表.列                                                     | owner                | 契约状态              | 列状态 | 来源   |
| ----------------------- | ------------------- | ------------------------------------------------------------- | -------------------- | --------------------- | ------ | ------ |
| intent / 规范事件：课程 | `courseId`          | `learning_events.course_id`                                   | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| intent：重试键          | `idempotencyKey`    | `learning_events.idempotency_key`                             | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：事件 ID       | `eventId`           | `learning_events.id`                                          | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：类型          | `eventType`         | `learning_events.event_type`                                  | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：认证身份      | `userId`            | `learning_events.student_user_id`                             | M5（身份由 M1 注入） | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：接受时间      | `occurredAt`        | `learning_events.occurred_at`                                 | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：请求追踪      | `traceId`           | `learning_events.trace_id`                                    | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：版本          | `schemaVersion`     | `learning_events.schema_version`                              | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| intent：章节            | `chapterId`         | 服务端映射到 `learning_events.payload` 的 `chapterId` 属性    | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |
| 规范事件：章节          | `payload.chapterId` | `learning_events.payload` 的 `chapterId` 属性；不是独立物理列 | M5                   | 已合入，待 M1/M6 确认 | 候选   | 未实现 |

要点：

- `learning_events.id` / `learning_events.student_user_id` 的候选拼写来自 learning 表概览；其余映射仍待 M5 字典，不能靠 JSON 字段推断列已存在。
- 现有 wire 的 `schemaVersion` 在事件 envelope 外层，`payload` 当前只有 `chapterId`。
  物理 JSONB 是否保留 envelope 版本、采用独立版本元数据或内部版本属性，均是待 M5 确认的 Q9；
  **本文不要求浏览器或 M6 增加 `payload.schemaVersion`，不改变现有 wire**。
- 同一 `(userId, idempotencyKey)` 且课程/章节相同只生成一个事件；同键换参数返回 409。
  浏览器内存持键，服务端实现去重；具体存储方案待 M5，并非必须在事件表加列。
- `occurredAt` 由服务端生成，M2 不传客户端时钟。M6 真实消费的 ingestion 游标是**目标方案**，
  待 [#65](https://github.com/StephenYI43/software-engineering-group-1/issues/65) 与 M5 确认；当前 analytics 契约仍采用 `(occurredAt, eventId)`。
  单纯自增取号不保证事务提交顺序，需验证迟到提交不会漏读，不能宣称目标已实现。

### 2.4 答疑 `/tutoring/:sessionId`

依据：`packages/contracts/tutoring/tutoring-response.md`、`sse-events.md` 与 avatar 冻结枚举。
M3 已在 [PR #76](https://github.com/StephenYI43/software-engineering-group-1/pull/76) `b2eab6b` 登记九表设计草案；下列已登记列按其拼写对齐，仍为待评审、未迁移的候选，不代表 main 已有表。

| 前端字段                   | JSON 契约字段               | 领域表.列                                                                                       | owner | 契约状态 | 列状态 | 来源    |
| -------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------- | ----- | -------- | ------ | ------- |
| 会话路由                   | `sessionId`                 | `tutoring_sessions.id`                                                                          | M3    | 已冻结   | 候选   | fixture |
| 会话归属                   | 无契约字段                  | `tutoring_sessions.student_user_id`                                                             | M3    | 待定(Q8) | 候选   | 未实现  |
| 课程限定                   | `courseId`                  | `tutoring_sessions.course_id`                                                                   | M3    | 已冻结   | 候选   | 未实现  |
| 学生提问                   | `content（请求）`           | `tutoring_turns.student_content`                                                                | M3    | 已冻结   | 候选   | 运行时  |
| 学生请求阶段               | `requestedStage`            | 无独立持久列；请求参数，服务端确定的阶段记 `tutoring_turns.stage`                               | M3    | 已冻结   | 候选   | 未实现  |
| 回答轮次                   | `turnId`                    | `tutoring_turns.id`                                                                             | M3    | 已冻结   | 候选   | fixture |
| 轮次所属会话               | `sessionId（响应）`         | `tutoring_turns.session_id`                                                                     | M3    | 已冻结   | 候选   | fixture |
| 回答正文                   | `content（响应）`           | `tutoring_turns.assistant_content`                                                              | M3    | 已冻结   | 候选   | fixture |
| 教学阶段                   | `stage`                     | `tutoring_turns.stage`                                                                          | M3    | 已冻结   | 候选   | fixture |
| 是否完整                   | `isComplete`                | `tutoring_turns.is_complete`                                                                    | M3    | 已冻结   | 候选   | 未实现  |
| 轮次状态                   | 无契约字段                  | `tutoring_turns.status`                                                                         | M3    | 待定(Q8) | 候选   | 未实现  |
| 中断原因                   | `stopped.reason`            | 未登记；Q8 待 M3 确认中断原因的存储映射                                                         | M3    | 待定(Q8) | 候选   | 未实现  |
| 建议追问                   | `followUps[]`               | `tutoring_turns.follow_ups`                                                                     | M3    | 已冻结   | 候选   | fixture |
| 情绪                       | `emotion`                   | `tutoring_turns.emotion`                                                                        | M3    | 已冻结   | 候选   | fixture |
| 动作                       | `action`                    | `tutoring_turns.action`                                                                         | M3    | 已冻结   | 候选   | fixture |
| 是否 Mock                  | `isMock`                    | `tutoring_turns.is_mock`                                                                        | M3    | 已冻结   | 候选   | fixture |
| 轮次时间                   | `createdAt`                 | `tutoring_turns.created_at`                                                                     | M3    | 已冻结   | 候选   | fixture |
| 引用：`turnId`             | `turnId（引用归属）`        | `turn_citations.turn_id`                                                                        | M3    | 已冻结   | 候选   | fixture |
| 引用：`citationId`         | `citations[].citationId`    | `turn_citations.citation_id`                                                                    | M3    | 已冻结   | 候选   | fixture |
| 引用：`documentId`         | `citations[].documentId`    | `turn_citations.document_id`                                                                    | M3    | 已冻结   | 候选   | fixture |
| 引用：`pageNumber`         | `citations[].pageNumber`    | `turn_citations.page_number`                                                                    | M3    | 已冻结   | 候选   | fixture |
| 引用：`snippet`            | `citations[].snippet`       | `turn_citations.snippet`                                                                        | M3    | 已冻结   | 候选   | fixture |
| 引用标题                   | `citations[].documentTitle` | `turn_citations.document_title_snapshot`（#76 草案快照；删除策略待 Q3）                         | M3    | 已冻结   | 候选   | fixture |
| 是否有依据                 | `hasEvidence`               | 由 `turn_citations.turn_id` 对应引用数推导，不另建列                                            | M3    | 已冻结   | 不适用 | fixture |
| 提示词版本                 | `promptVersion`             | `tutoring_turns.prompt_version_id` → `prompt_versions.id`，输出 `prompt_versions.version_label` | M3    | 已冻结   | 候选   | fixture |
| 流内序号                   | `seq`                       | 不适用，传输层序号                                                                              | —     | 已冻结   | 不适用 | 运行时  |
| 拼接文本、停止中、重试计数 | 无契约字段                  | 不适用，浏览器临时态                                                                            | —     | 无契约   | 不适用 | 运行时  |

要点：

- 当前已合并 SSE 契约要求停止/断连轮次为未完成并不推进阶段；错误轮同样不推进。
  已冻结契约要求停止/断连为 `aborted`、`isComplete=false` 且不推进；#76 当前状态枚举与之冲突，须由 M3 修订确认。中断原因字段尚未登记，正文存储及截断策略仍待 Q8，不把内存状态直接升级为持久化约定。
  PR #62 的内部 `disconnected` 及 stop 204 修订尚未合并，不在本文冒充已冻结存储模型。
- 契约允许部分文本保留供展示，但不能计入完整回答；M2 不擅自决定原文是否落库。
- 未完成轮次不渲染引用/追问；重试创建新轮，不通过客户端推进阶段。
- `emotion` / `action` 是 M3 输出，M2 透传给 M4，不转换成持久偏好。

### 2.5 作业与提交（页面未实现，沿用 learning 已确认契约）

依据：`packages/contracts/learning/homework.md`。

| 前端字段                    | JSON 契约字段                  | 领域表.列                                               | owner | 契约状态 | 列状态 | 来源     |
| --------------------------- | ------------------------------ | ------------------------------------------------------- | ----- | -------- | ------ | -------- |
| `Assignment.id`             | `id`                           | `assignments.id`                                        | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.courseId`       | `courseId`                     | `assignments.course_id`                                 | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.classId`        | `classId`                      | `assignments.class_id`                                  | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.chapterId`      | `chapterId`                    | `assignments.chapter_id`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.title`          | `title`                        | `assignments.title`                                     | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.description`    | `description`                  | `assignments.description`                               | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.questionType`   | `questionType`                 | `assignments.question_type`                             | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.answerKey`      | `answerKey`                    | `assignments.answer_key`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.maxScore`       | `maxScore`                     | `assignments.max_score`                                 | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.dueAt`          | `dueAt`                        | `assignments.due_at`                                    | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.publishedAt`    | `publishedAt`                  | `assignments.published_at`                              | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.teacherId`      | `teacherId`                    | `assignments.teacher_id`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.createdAt`      | `createdAt`                    | `assignments.created_at`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Assignment.updatedAt`      | `updatedAt`                    | `assignments.updated_at`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.id`             | `id`                           | `submissions.id`                                        | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.assignmentId`   | `assignmentId`                 | `submissions.assignment_id`                             | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.classId`        | `classId`                      | `submissions.class_id`                                  | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.studentId`      | `studentId`                    | `submissions.student_user_id`                           | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.answer`         | `answer`                       | `submissions.answer`                                    | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.isCorrect`      | `isCorrect`                    | `submissions.is_correct`                                | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.score`          | `score`                        | `submissions.score`                                     | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.gradedAt`       | `gradedAt`                     | `submissions.graded_at`                                 | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.gradedBy`       | `gradedBy`                     | `submissions.graded_by`                                 | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.idempotencyKey` | `idempotencyKey`               | `submissions.idempotency_key`                           | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.submittedAt`    | `submittedAt`                  | `submissions.submitted_at`                              | M5    | 已冻结   | 候选   | 未实现   |
| `Submission.createdAt`      | `createdAt`                    | `submissions.created_at`                                | M5    | 已冻结   | 候选   | 未实现   |
| 自己是否提交                | `submission`                   | 响应信封；null 表示尚未提交，无额外物理列               | M5    | 已冻结   | 不适用 | 未实现   |
| 教师列表学生摘要：ID        | `studentSummary.studentId`     | 响应组合：`submissions.student_user_id` → `users.id`    | M1/M5 | 已冻结   | 候选   | 响应组合 |
| 教师列表学生摘要：姓名      | `studentSummary.name`          | 响应组合：`user_profiles.display_name`（PR #73 候选）   | M1    | 已冻结   | 候选   | 响应组合 |
| 教师列表学生摘要：学号      | `studentSummary.studentNumber` | 响应组合：`user_profiles.student_number`（PR #73 候选） | M1    | 已冻结   | 候选   | 响应组合 |
| 学生修改答案入口            | 无契约字段                     | 未定义；契约要求 PATCH，但未给学生编辑端点/请求         | M5    | 无契约   | 未登记 | 未实现   |
| 选择题公开选项              | 无契约字段                     | 未定义；不能拿私有标准答案代替可见选项                  | M5    | 无契约   | 未登记 | 未实现   |

`answerKey` 在学生响应里必须不存在；`assignments.answer_key` 是服务端私有候选 JSONB。
`submissions.answer` 的 wire 允许对象或字符串，物理存储及版本规则待 M5，不能直接断定全是 JSONB。
幂等键由客户端在表单会话内复用，服务端去重；姓名/学号不复制进提交行。

### 2.6 错题本（页面未实现，沿用 learning 已确认契约）

依据：`packages/contracts/learning/mistakes.md`。

| 前端字段                      | JSON 契约字段            | 领域表.列                                                   | owner | 契约状态 | 列状态 | 来源   |
| ----------------------------- | ------------------------ | ----------------------------------------------------------- | ----- | -------- | ------ | ------ |
| `Mistake.id`                  | `id`                     | `mistakes.id`                                               | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.studentId`           | `studentId`              | `mistakes.student_user_id`                                  | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.courseId`            | `courseId`               | `mistakes.course_id`                                        | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.chapterId`           | `chapterId`              | `mistakes.chapter_id`                                       | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.assignmentId`        | `assignmentId`           | `mistakes.assignment_id`                                    | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.submissionId`        | `submissionId`           | `mistakes.submission_id`                                    | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.sourceTurnId`        | `sourceTurnId`           | `mistakes.source_turn_id`                                   | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.source`              | `source`                 | `mistakes.source`                                           | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.question`            | `question`               | `mistakes.question`                                         | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.studentAnswer`       | `studentAnswer`          | `mistakes.student_answer`                                   | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.note`                | `note`                   | `mistakes.note`                                             | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.status`              | `status`                 | `mistakes.status`                                           | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.createdAt`           | `createdAt`              | `mistakes.created_at`                                       | M5    | 已冻结   | 候选   | 未实现 |
| `Mistake.updatedAt`           | `updatedAt`              | `mistakes.updated_at`                                       | M5    | 已冻结   | 候选   | 未实现 |
| 题目快照属性：`stem`          | `question.stem`          | `mistakes.question` 的 `stem` 属性；不是独立物理列          | M5    | 已冻结   | 候选   | 未实现 |
| 题目快照属性：`questionType`  | `question.questionType`  | `mistakes.question` 的 `questionType` 属性；不是独立物理列  | M5    | 已冻结   | 候选   | 未实现 |
| 题目快照属性：`options`       | `question.options`       | `mistakes.question` 的 `options` 属性；不是独立物理列       | M5    | 已冻结   | 候选   | 未实现 |
| 题目快照属性：`attachmentUrl` | `question.attachmentUrl` | `mistakes.question` 的 `attachmentUrl` 属性；不是独立物理列 | M5    | 已冻结   | 候选   | 未实现 |

只在错答或学生主动标记时收录；客户端不能声明 `wrong_submission`，答疑结束不能默认收录。
`mistakes.question` / `mistakes.student_answer` 是快照，版本化方案由 M5 定稿（Q5），
不擅自在现有请求里增加 `schemaVersion`。

### 2.7 复习计划与提醒（页面未实现，沿用 learning 已确认契约）

依据：`packages/contracts/learning/study-plans.md`。

| 前端字段                       | JSON 契约字段                     | 领域表.列                                                                  | owner | 契约状态 | 列状态 | 来源   |
| ------------------------------ | --------------------------------- | -------------------------------------------------------------------------- | ----- | -------- | ------ | ------ |
| `StudyPlan.id`                 | `id`                              | `study_plans.id`                                                           | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.studentId`          | `studentId`                       | `study_plans.student_user_id`                                              | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.title`              | `title`                           | `study_plans.title`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.courseId`           | `courseId`                        | `study_plans.course_id`                                                    | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.chapterId`          | `chapterId`                       | `study_plans.chapter_id`                                                   | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.source`             | `source`                          | `study_plans.source`                                                       | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.sourceTurnId`       | `sourceTurnId`                    | `study_plans.source_turn_id`                                               | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.status`             | `status`                          | `study_plans.status`                                                       | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.dueAt`              | `dueAt`                           | `study_plans.due_at`                                                       | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.createdAt`          | `createdAt`                       | `study_plans.created_at`                                                   | M5    | 已冻结   | 候选   | 未实现 |
| `StudyPlan.updatedAt`          | `updatedAt`                       | `study_plans.updated_at`                                                   | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.id`                  | `items[].id`                      | `plan_items.id`                                                            | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.planId`              | `items[].planId`                  | `plan_items.plan_id`                                                       | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.content`             | `items[].content`                 | `plan_items.content`                                                       | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.order`               | `items[].order`                   | `plan_items.order`                                                         | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.status`              | `items[].status`                  | `plan_items.status`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.dueAt`               | `items[].dueAt`                   | `plan_items.due_at`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.chapterId`           | `items[].chapterId`               | `plan_items.chapter_id`                                                    | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.knowledgePoint`      | `items[].knowledgePoint`          | `plan_items.knowledge_point`                                               | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.relatedMistakeId`    | `items[].relatedMistakeId`        | `plan_items.related_mistake_id`                                            | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.relatedAssignmentId` | `items[].relatedAssignmentId`     | `plan_items.related_assignment_id`                                         | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.createdAt`           | `items[].createdAt`               | `plan_items.created_at`                                                    | M5    | 已冻结   | 候选   | 未实现 |
| `PlanItem.updatedAt`           | `items[].updatedAt`               | `plan_items.updated_at`                                                    | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.id`                  | `id`                              | `reminders.id`                                                             | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.studentId`           | `studentId`                       | `reminders.student_user_id`                                                | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.planId`              | `planId`                          | `reminders.plan_id`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.assignmentId`        | `assignmentId`                    | `reminders.assignment_id`                                                  | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.type`                | `type`                            | `reminders.type`                                                           | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.title`               | `title`                           | `reminders.title`                                                          | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.body`                | `body`                            | `reminders.body`                                                           | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.dueAt`               | `dueAt`                           | `reminders.due_at`                                                         | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.isRead`              | `isRead`                          | `reminders.is_read`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.createdAt`           | `createdAt`                       | `reminders.created_at`                                                     | M5    | 已冻结   | 候选   | 未实现 |
| `Reminder.readAt`              | `readAt`                          | `reminders.read_at`                                                        | M5    | 已冻结   | 候选   | 未实现 |
| 计划项集合                     | `items[]`                         | 按 `plan_items.plan_id` 关联；集合本身不新增列                             | M5    | 已冻结   | 不适用 | 未实现 |
| 保存答疑建议                   | `sourceTurnId（source=tutoring）` | 请求引用，持久化候选为 `study_plans.source_turn_id`；M5 服务端取用 M3 建议 | M3/M5 | 已冻结   | 候选   | 未实现 |
| 计划项勾选（尚无页面）         | `items[].status`                  | `plan_items.status`；未来乐观更新仅在内存，失败回滚                        | M5    | 已冻结   | 候选   | 未实现 |

前端不转存 `planSuggestion`、不发送建议 items；M3 取用接口尚未落地，M5 应拒绝未能取用的建议保存。
不能把上述字段映射当作计划页面或保存链路已实现。

### 2.8 数字人播报（未接线）

依据：`packages/contracts/avatar/avatar-controller.md`。

| 前端字段              | JSON 契约字段          | 领域表.列                                           | owner  | 契约状态 | 列状态 | 来源   |
| --------------------- | ---------------------- | --------------------------------------------------- | ------ | -------- | ------ | ------ |
| 播报标识              | `utteranceId`          | 不适用；M4 是否保存播放记录及列名待其字典           | M4     | 已冻结   | 不适用 | 未实现 |
| 播报文本              | `text`                 | 不复制；来源候选 `tutoring_turns.assistant_content` | M3/M4  | 已冻结   | 不适用 | 未实现 |
| 情绪                  | `emotion`              | `tutoring_turns.emotion`                            | M3     | 已冻结   | 候选   | 未实现 |
| 动作                  | `action`               | `tutoring_turns.action`                             | M3     | 已冻结   | 候选   | 未实现 |
| 播放状态              | `AvatarPlaybackStatus` | 不适用，组件运行时                                  | M4     | 已冻结   | 不适用 | 未实现 |
| 播放事件类型          | `type`                 | 不适用，组件回调事件                                | M4     | 已冻结   | 不适用 | 未实现 |
| 停止原因              | `reason`               | 不适用，组件回调事件                                | M4     | 已冻结   | 不适用 | 未实现 |
| 播放错误：`code`      | `error.code`           | 不适用，错误回调；日志/审计是否保存待 M4            | M4     | 已冻结   | 不适用 | 未实现 |
| 播放错误：`message`   | `error.message`        | 不适用，错误回调；日志/审计是否保存待 M4            | M4     | 已冻结   | 不适用 | 未实现 |
| 播放错误：`requestId` | `error.requestId`      | 不适用，错误回调；日志/审计是否保存待 M4            | M4     | 已冻结   | 不适用 | 未实现 |
| 播放错误：`details`   | `error.details`        | 不适用，错误回调；日志/审计是否保存待 M4            | M4     | 已冻结   | 不适用 | 未实现 |
| 音量                  | 无契约字段             | 见第 6 节，owner 与字段待确认                       | 待认领 | 无契约   | 未登记 | 未实现 |
| 语速                  | 无契约字段             | 见第 6 节，owner 与字段待确认                       | 待认领 | 无契约   | 未登记 | 未实现 |
| 自动播报              | 无契约字段             | 见第 6 节，owner 与字段待确认                       | 待认领 | 无契约   | 未登记 | 未实现 |
| 字幕                  | 无契约字段             | 见第 6 节，owner 与字段待确认                       | 待认领 | 无契约   | 未登记 | 未实现 |

上述接口字段均未在当前学生页面接线；播放状态属于组件运行时，不表示已有媒体持久化。
只播报 tutoring `completed` 完整回答；停止播报用 `stop(utteranceId)`，停止答疑走 M3 stop 端点。

## 3. 「浏览器不保存」≠「服务端不落库」

这一节单独列出：把两者混为一谈最容易在验收时漏账。

| 数据项                       | 浏览器侧                 | 服务端侧（契约要求）                                                                        | 归属      |
| ---------------------------- | ------------------------ | ------------------------------------------------------------------------------------------- | --------- |
| 章节浏览 `idempotencyKey`    | 只在内存，刷新即换新键   | 服务端保存幂等映射；候选 `learning_events.idempotency_key`，具体位置待 M5                   | M5        |
| 作业提交 `idempotencyKey`    | 只在内存，表单会话内复用 | 候选 `submissions.idempotency_key` + 唯一约束，重复提交返回首次记录                         | M5        |
| `stopped`/`error`/断连的轮次 | 半截文本只在内存展示     | 候选 `tutoring_turns.status` / `tutoring_turns.is_complete`，值及正文按 Q8 定稿；阶段不推进 | M3        |
| 中断轮次的部分正文           | 只在内存展示             | **是否保存由 M3 定**（允许保留供展示，但不得计入已完成回答）                                | M3        |
| 播放状态、音量、字幕开关     | 只在内存                 | 无契约字段，当前不落库                                                                      | M4/待认领 |
| 输入草稿、加载/错误态        | 只在内存                 | 不涉及                                                                                      | —         |

结论：**浏览器不保存只说明「前端没有持久化」，不能推出「服务端没有这条记录」**；
反过来，前端有状态也不代表服务端已保存。验收必须分别取证。

## 4. 组合字段（不建列）

| 字段                                  | 为什么不落库                                    | 正确来源                                                                |
| ------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------- |
| `Course.teacherName`                  | 改名后课程行不跟着变，会漂移                    | M1 `user_profiles.display_name` 组合                                    |
| `Course.studentCount`/`chapterCount`  | 与真实行数可能不一致，无约束保证同步            | 聚合计数                                                                |
| `StudentSummary.name`/`studentNumber` | 复制到提交/错题会随改名失真                     | 候选 `user_profiles.display_name` / `user_profiles.student_number` 组合 |
| `TutoringResponse.hasEvidence`        | 与 `citations` 为空互为充要，存两处必有一处先坏 | 由引用数推导                                                            |
| `planSuggestion` 内容                 | 属 M3 生成的建议，M5 保存时重新取用             | M3 取用接口                                                             |
| 分页 `page`/`pageSize`/`total`        | 每次请求的视图参数                              | 查询参数                                                                |

## 5. UI 临时态（不持久化）

| 状态                         | 位置           | 为什么不持久化                     | 误持久化的后果                                     |
| ---------------------------- | -------------- | ---------------------------------- | -------------------------------------------------- |
| 输入草稿（提问、答案、备注） | 答疑/作业/错题 | 未提交内容不是业务事实             | 「没提交」变成「有记录」，与幂等键语义冲突         |
| 流内 `seq`、已拼接半截文本   | 答疑           | 由连接生命周期决定，终止帧才是结果 | 半截文本进库后无法区分「模型中断」与「学生看到过」 |
| 停止中/停止超时提示          | 答疑           | 连接状态，重启即失效               | 伪造「已停止」的服务端事实                         |
| 加载/空/错误态               | 全部页面       | 由请求状态派生                     | 掩盖真实错误                                       |
| 表单校验错误                 | 全部表单       | 派生状态                           | —                                                  |
| `?mock=`/`?turn=` 演示开关   | 全部页面       | 开发态开关，生产构建移除           | 把 Mock 行为带进验收证据                           |
| 列表排序/筛选/页码           | 列表页         | 放 URL query，可分享、可回溯       | 同链接在不同人处显示不同内容                       |
| 计划项乐观勾选               | 计划页         | 以服务端结果为准                   | 断网时显示「已完成」而库里没有                     |
| 数字人播放状态               | 播报组件       | 运行时状态                         | —                                                  |

判断标准：**这个状态是不是「服务端必须知道的事实」**。是，走服务端接口；不是，留在内存或 URL。
本节只说明前端不保存，**不推论服务端业务事实是否存在**（见第 3 节）。

## 6. 偏好归属（待评审，不建表）

学生端当前 main 基线代码没有持久化偏好；检索结果与可执行证据由验收 F1 单独记录，本文不代替验收执行。
以下为产品候选，**当前契约没有字段，需求和持久化 owner 均待确认**。M2 不建表、不落库；谁认领谁登记。

| 偏好项                   | 现状               | 持久化需求       | 建议归属（均待确认）                    | 候选列（未登记，不得作为现有列引用）   | 影响                           |
| ------------------------ | ------------------ | ---------------- | --------------------------------------- | -------------------------------------- | ------------------------------ |
| 自动播报下一轮           | 无，数字人未接线   | 跨设备需求待确认 | M4 先定入参；持久化 owner 待 M1/M5 确认 | `student_preferences.auto_play_avatar` | 组件接口与存储必须使用同一语义 |
| 音量                     | 未实现             | 待确认           | M4 先定入参；持久化 owner 待 M1/M5 确认 | `student_preferences.avatar_volume`    | 取值域待 M4 确认               |
| 语速                     | 未实现             | 待确认           | M4 先定入参；持久化 owner 待 M1/M5 确认 | `student_preferences.avatar_rate`      | 取值域待 M4 确认               |
| 字幕默认开启             | 未实现             | 可选，待确认     | M4 先定入参；持久化 owner 待 M1/M5 确认 | `student_preferences.subtitle_enabled` | 实施阶段及是否保存待确认       |
| 上次阅读章节（学习进度） | 未实现，且不是偏好 | 跨设备需求待确认 | 建议 M5 从事件推导、M6 展示，双方待确认 | 无定稿列；不在本文新增进度表           | 需先完成正文阅读与章节事件通路 |

> `student_preferences` 只是候选名：M2 不提交它的字典、不在任何 PR 建这张表。
> 认领前前端不读不写任何持久偏好设置。

## 7. 需要 owner 确认的问题（附建议与影响）

| #   | 问题                                                                                                                                                                                    | 涉及  | 建议                                                                                                                                          | 不解决的后果                                                        |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Q1  | [#16](https://github.com/StephenYI43/software-engineering-group-1/issues/16) 已明确 M5 维护选课关系表；选课端点属 M1。M1 已在 #70 确认归属；#47 路径/schema 与公开 service 签名仍待冻结 | M1/M5 | 沿用 M5 表 owner 与建模/写入职责；M1 端点按 #47 调 M5 公开 service 写入口，并供鉴权/列表复用。具体调用签名待 M1/M5 确认；不另建关系表         | 两边各建一张学生-班级表，鉴权与列表读到不同数据，学生能看到没选的课 |
| Q2  | `studentCount`/`chapterCount` 是否物化                                                                                                                                                  | M5    | 不物化，查询聚合；确需性能再加快照并写刷新策略                                                                                                | 删章节后计数不减，教师端与学生端人数不一致且无人能修                |
| Q3  | `citations[].documentTitle` 存快照还是 join；章节删除时 `document_id` 的处置                                                                                                            | M3/M5 | 引用存快照并记文档版本；删除课件前检查引用                                                                                                    | 改名/删文档后历史引用标题变样，学生按旧标题找不到资料               |
| Q4  | `followUps` 用 JSONB 还是子表                                                                                                                                                           | M3    | 建议 JSONB 保序；内部版本属性或外置版本对应规则待 M3，不改现有 wire                                                                           | 用子表却没有 `order`，刷新后追问顺序乱                              |
| Q5  | `mistakes.question` / `mistakes.student_answer` 的 JSONB 是否版本化                                                                                                                     | M5    | 建议冻结快照版本及兼容读规则；可内置或外置版本，待 M5，不改变现有 wire                                                                        | 新增题型后旧错题渲染崩，复习时看不到题干                            |
| Q6  | 学习进度（最后阅读章节）由谁建模                                                                                                                                                        | M5/M6 | 由 `learning_events` 推导，不新增进度表                                                                                                       | 前端用 localStorage 记进度，换设备即丢                              |
| Q7  | 数字人偏好是否进 M4 组件契约                                                                                                                                                            | M4    | 先补 `avatar-controller.md` 入参，再谈持久化                                                                                                  | 前端自存音量，组件不认，改了没效果                                  |
| Q8  | 中断轮次存储：#76 状态与冻结 `aborted` 语义冲突；原因字段未登记；半截正文保存/截断待定                                                                                                  | M3    | 沿用冻结停止/断连 `aborted`、未完成且不推进；M3 修订 #76 并定稿原因、正文保存/截断与版本策略                                                  | 只落一半：要么统计把中断算成完成，要么学生回看时正文消失            |
| Q9  | `learning_events.payload` 的 JSONB 键命名（`chapterId` 还是 `chapter_id`）与 `schemaVersion`                                                                                            | M5    | 现有 wire 的 envelope.schemaVersion 与 payload.chapterId 保持不变；物理 JSONB 内部版本或外置版本对应方案待 M5。不能从外层列命名推导内部键改名 | 键名漂移后 M6 消费端读不到 `chapterId`，事件静默丢字段              |

## 8. 与验收的关系

本文件只到「映射与归属」，**不含任何数据库证据**。真实 PostgreSQL 的读写、重启读回、幂等与越权验收
按 [acceptance.md](acceptance.md) 执行，未运行的项目一律不勾选。
前端参与验收只认两类证据：真实接口返回（浏览器 network / 服务端日志）与页面截图；
**fixture 渲染、`?mock=` 场景截图不得作为验收证据**。
