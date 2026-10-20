# 学生端字段映射与偏好归属（M2）

关联 [#70](https://github.com/StephenYI43/software-engineering-group-1/issues/70)、[#69](https://github.com/StephenYI43/software-engineering-group-1/issues/69)。
owner：M2 / @Saber-www；评审：M1、M5。
基线：`main` `d01f32e`；格式参照 PR #73 head `c71de57`（**未合并**，本文件不声称模板已在 main）。
状态：**字段映射草案。本文件不登记新表**，不建迁移、不改 API、不改其他 owner 的字典。

本文回答四件事：学生端每个字段从哪来、落到哪张表的哪一列（或为什么不落库）、由谁拥有、
现在是真数据还是示意数据。七要素字典按 owner 分文件，M2 只做映射与归属判定。

## 0. 口径

### 0.1 两条不同的状态轴：契约冻结 ≠ 列冻结

| 轴       | 取值                                    | 含义                                  |
| -------- | --------------------------------------- | ------------------------------------- |
| 契约状态 | `已冻结` / `待定(Qn)` / `无契约`        | JSON 字段是否已被已合并的契约文本定义 |
| 列状态   | `已登记` / `候选` / `未登记` / `不适用` | 该列是否已出现在某份数据字典里        |

`已登记` 指某份 `docs/data-model/*.md` 已写明该表该列；`候选` 指按
`docs/code-standards.md:49`（复数表名、snake_case 列）从 JSON 字段推导，**等对应 owner 的字典合并后才算数**。

> 当前事实：main 上**没有任何学生端相关表列被登记**。`learning` 只有契约附带的表概览；
> `platform` 的七表在未合并的 PR #73；`tutoring`/`avatar`/`analytics` 的字典尚未提交。
> 因此本文绝大多数列状态是 `候选`——这不是保守写法，是当前仓库的真实状态。

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
| `/courses/:courseId`   | 课程详情 + 章节列表 | 已实现（S0，fixture）      | 同上                                                | `GET /courses/{id}`、`/chapters`               | M5，未实现                             |
| `/tutoring/:sessionId` | 答疑（单轮展示）    | 已实现（S0，fixture）      | `mocks/` 的 `fetchTutoringTurn`                     | `POST /tutoring/sessions/{id}/messages`（SSE） | M3：#62 未合并；M2 的 SSE 客户端在 #68 |
| 章节正文               | 阅读页              | **未实现**（只有章节列表） | —                                                   | `ChapterViewedIntent`                          | M5/M1，路径未冻结                      |
| 作业列表/详情/提交     | 作业                | **未实现**                 | —                                                   | `/courses/{id}/assignments` 等                 | M5，未实现                             |
| 错题本                 | 错题                | **未实现**                 | —                                                   | `/api/v1/mistakes`                             | M5，未实现                             |
| 复习计划/提醒          | 计划                | **未实现**                 | —                                                   | `/api/v1/study-plans`、`/reminders`            | M5，未实现                             |
| 数字人播报             | 组件                | **未接线**                 | —                                                   | `AvatarController`（组件契约）                 | M4：#61 未合并                         |

## 2. 逐页字段映射

列说明：`契约状态`、`列状态` 见 0.1；`来源` 见 0.2。

### 2.1 课程列表 `/courses`

| 前端字段                       | JSON 契约字段   | 领域表.列                              | owner           | 契约状态 | 列状态 | 来源     |
| ------------------------------ | --------------- | -------------------------------------- | --------------- | -------- | ------ | -------- |
| `Course.id`                    | `id`            | `courses.id`                           | M5              | 已冻结   | 候选   | fixture  |
| `Course.title`                 | `title`         | `courses.title`                        | M5              | 已冻结   | 候选   | fixture  |
| `Course.description`           | `description`   | `courses.description`                  | M5              | 已冻结   | 候选   | fixture  |
| `Course.subject`               | `subject`       | `courses.subject`                      | M5              | 已冻结   | 候选   | fixture  |
| `Course.coverImageUrl`         | `coverImageUrl` | `courses.cover_image_url`              | M5              | 已冻结   | 候选   | fixture  |
| `Course.teacherId`             | `teacherId`     | `courses.teacher_id`                   | M5              | 已冻结   | 候选   | fixture  |
| `Course.teacherName`           | `teacherName`   | 响应组合：`user_profiles.display_name` | M1              | 已冻结   | 候选   | 响应组合 |
| `Course.studentCount`          | `studentCount`  | 聚合：`enrollments` 计数               | M5（写入见 Q1） | 已冻结   | 候选   | fixture  |
| `Course.chapterCount`          | `chapterCount`  | 聚合：`chapters` 计数                  | M5              | 已冻结   | 候选   | fixture  |
| `Course.createdAt`             | `createdAt`     | `courses.created_at`                   | M5              | 已冻结   | 候选   | fixture  |
| `Course.updatedAt`             | `updatedAt`     | `courses.updated_at`                   | M5              | 已冻结   | 候选   | fixture  |
| 分页 `page`/`pageSize`/`total` | 查询参数与信封  | 不适用                                 | —               | 已冻结   | 不适用 | fixture  |

要点：

- `teacherName` 按 `courses.md:228` 不存进 `courses`，由服务端按 `teacher_id` 组合 M1 资料回填。
  前端必须能处理 `null`（当前实现缺省不显示主讲）。
- `studentCount`/`chapterCount` 契约只写「可回填」。**建议不物化成列**（Q2）：物化列没有约束能保证与
  `enrollments`、`chapters` 的真实行数同步。
- `subject` 收到枚举外取值时回退显示原值，是纯前端逻辑，不产生持久化字段。

### 2.2 课程详情与章节 `/courses/:courseId`

| 前端字段                        | JSON 契约字段      | 领域表.列                                    | owner         | 契约状态 | 列状态 | 来源    |
| ------------------------------- | ------------------ | -------------------------------------------- | ------------- | -------- | ------ | ------- |
| 课程头部                        | 同 2.1             | 同 2.1                                       | M5            | 已冻结   | 候选   | fixture |
| `Chapter.id`                    | `id`               | `chapters.id`                                | M5            | 已冻结   | 候选   | fixture |
| `Chapter.courseId`              | `courseId`         | `chapters.course_id`                         | M5            | 已冻结   | 候选   | fixture |
| `Chapter.title`                 | `title`            | `chapters.title`                             | M5            | 已冻结   | 候选   | fixture |
| `Chapter.order`                 | `order`            | `chapters.order`                             | M5            | 已冻结   | 候选   | fixture |
| `Chapter.description`           | `description`      | `chapters.description`                       | M5            | 已冻结   | 候选   | fixture |
| `Chapter.documentId`            | `documentId`       | `chapters.document_id` → 引用 `documents.id` | M5（引用 M3） | 已冻结   | 候选   | fixture |
| `Chapter.createdAt`/`updatedAt` | 同名               | `chapters.created_at`/`updated_at`           | M5            | 已冻结   | 候选   | fixture |
| 章节正文                        | 无（当前无阅读页） | `document_chunks` 等                         | M3            | 待定     | 候选   | 未实现  |

要点：

- `document_id` 是跨域引用，**不含文档内容**，也不代表学生有权阅读（授权在 M3 的 `document_grants`，
  检索前校验）。前端只显示「已关联课件」。
- 章节删除后 `document_id` 置空还是禁止删除，属 M5/M3 边界（Q3），M2 不单方定义。

### 2.3 章节浏览事件（无阅读页，契约已冻结）

| 前端字段   | JSON 契约字段                                    | 领域表.列                                      | owner             | 契约状态 | 列状态 | 来源   |
| ---------- | ------------------------------------------------ | ---------------------------------------------- | ----------------- | -------- | ------ | ------ |
| 路由参数   | `courseId`                                       | `learning_events.course_id`                    | M5                | 已冻结   | 候选   | 未实现 |
| 路由参数   | `payload.chapterId`                              | `learning_events.payload`（JSONB，内部键见下） | M5                | 已冻结   | 候选   | 未实现 |
| 会话身份   | `userId`                                         | `learning_events.user_id`                      | M1 注入 / M5 写入 | 已冻结   | 候选   | 未实现 |
| 前端生成   | `idempotencyKey`                                 | `learning_events.idempotency_key`              | M5                | 已冻结   | 候选   | 未实现 |
| 服务端生成 | `eventId`/`occurredAt`/`traceId`/`schemaVersion` | 同名同义                                       | M5                | 已冻结   | 候选   | 未实现 |

要点：

- **JSONB 内部键名不随外层列改名**：契约 payload 的键是 `chapterId`（camelCase），
  外层列是 snake_case 不代表内部键要改成 `chapter_id`。内部键命名与 `schemaVersion` 由 M5 在
  `learning.md` 的 JSONB 内部字典里定（Q9）；M2 只写映射，不改契约键名。
- `payload` 是 JSONB，必须给内部属性（至少 `chapterId` 与 `schemaVersion`），
  不能用「payload 一个字段」掩盖未建模数据（#69「持久化共同基线」）。
- 幂等：同一 `(userId, idempotencyKey)` 且课程/章节相同只产生一个事件；同键换课程/章节返回 409
  （`packages/contracts/student/learning-events.md:22-27`）。浏览器只在内存持键，服务端负责去重。
- `occurredAt` 由服务端生成，不是写入游标；M6 用 ingestion 单调键消费，M2 不传客户端时钟。

### 2.4 答疑 `/tutoring/:sessionId`

| 前端字段                                     | JSON 契约字段                | 领域表.列                                                                         | owner | 契约状态          | 列状态 | 来源           |
| -------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------- | ----- | ----------------- | ------ | -------------- |
| 路由参数                                     | `sessionId`                  | `tutoring_sessions.id`                                                            | M3    | 已冻结            | 候选   | fixture        |
| 会话归属                                     | 会话上下文                   | `tutoring_sessions.user_id`                                                       | M3    | 已冻结            | 候选   | 服务端写入     |
| 课程限定                                     | `courseId`                   | `tutoring_sessions.course_id`                                                     | M3    | 已冻结            | 候选   | 不适用（透传） |
| 输入框内容                                   | `content`（1—2000）          | `tutoring_turns.user_content`                                                     | M3    | 已冻结            | 候选   | 运行时         |
| 学生请求阶段                                 | `requestedStage`             | `tutoring_turns.requested_stage`（可空）                                          | M3    | 已冻结            | 候选   | 不适用（透传） |
| 回答正文                                     | `content`                    | `tutoring_turns.content`                                                          | M3    | 已冻结            | 候选   | fixture        |
| 教学阶段                                     | `stage`                      | `tutoring_turns.stage`                                                            | M3    | 已冻结            | 候选   | fixture        |
| 轮次是否完整                                 | `isComplete`（终止帧）       | `tutoring_turns.is_complete`                                                      | M3    | 已冻结            | 候选   | 未实现         |
| 轮次状态                                     | 无独立字段（由终止事件推导） | `tutoring_turns.status`（`completed`/`aborted`，Q8）                              | M3    | 待定(Q8)          | 未登记 | 未实现         |
| 中断原因                                     | `stopped.reason`             | `tutoring_turns.abort_reason`（Q8）                                               | M3    | 已冻结（wire 值） | 未登记 | 未实现         |
| 引用列表                                     | `citations[]`                | `turn_citations`（`turn_id`/`citation_id`/`document_id`/`page_number`/`snippet`） | M3    | 已冻结            | 候选   | fixture        |
| 引用标题                                     | `citations[].documentTitle`  | `turn_citations.document_title`（快照）或 join `documents.title`                  | M3    | 已冻结            | 候选   | fixture        |
| 是否有依据                                   | `hasEvidence`                | 不单独建列，由引用数推导                                                          | M3    | 已冻结            | 不适用 | fixture        |
| 追问建议                                     | `followUps[]`（≤3×200）      | `tutoring_turns.follow_ups`（JSONB，Q4）                                          | M3    | 已冻结            | 候选   | fixture        |
| 情绪/动作                                    | `emotion`/`action`           | `tutoring_turns.emotion`/`action`                                                 | M3    | 已冻结            | 候选   | fixture        |
| 是否 Mock                                    | `isMock`                     | `tutoring_turns.is_mock`                                                          | M3    | 已冻结            | 候选   | fixture        |
| 提示词版本                                   | `promptVersion`              | `tutoring_turns.prompt_version_id` → `prompt_versions`                            | M3    | 已冻结            | 候选   | fixture        |
| 轮次时间                                     | `createdAt`                  | `tutoring_turns.created_at`                                                       | M3    | 已冻结            | 候选   | fixture        |
| 播报标识                                     | `utteranceId`                | 不适用（M4 若记 `playback_records` 由 M4 登记）                                   | M4    | 已冻结            | 不适用 | 运行时         |
| 流内 `seq`、已拼接半截文本、停止中、重试计数 | 无（传输层）                 | 不适用                                                                            | —     | 无契约            | 不适用 | 运行时         |

要点（本次修正的重点）：

- **`stopped` / `error` / 连接断开都不是「不落库」**。契约明确：该轮**持久化为 `aborted`、
  `isComplete = false`**，教学阶段不推进；`stopped` 与 `error` 的区别只是「用户意图」与「系统失败」
  （`packages/contracts/tutoring/sse-events.md`「stopped」「error」「断连行为」）。
- **半截正文存不存是另一个问题**：契约允许「已生成的部分文本可以保留供展示」，但**不得计入
  「已完成回答」**。存到哪一列、是否存原文、是否截断，由 M3 在 `tutoring-knowledge.md` 定（Q8）；
  M2 既不写「一律不落库」，也不写「一律保留」。
- 前端展示：`aborted` 轮次只展示已收到内容并标「未完成」，不渲染引用/追问；重试是**新轮**，
  阶段指示器不需要重置，因为它从未推进。
- `emotion`/`action` 是 M3 映射、M4 消费的输出；M2 只透传，不推导、不缓存成偏好。

### 2.5 作业与提交（未实现，契约已冻结）

| 前端字段                   | JSON 契约字段                             | 领域表.列                                                | owner | 契约状态 | 列状态 | 来源     |
| -------------------------- | ----------------------------------------- | -------------------------------------------------------- | ----- | -------- | ------ | -------- |
| 标识与关联                 | `id`/`courseId`/`classId`/`chapterId`     | `assignments.id`/`course_id`/`class_id`/`chapter_id`     | M5    | 已冻结   | 候选   | 未实现   |
| 标题/说明                  | `title`/`description`                     | `assignments.title`/`description`                        | M5    | 已冻结   | 候选   | 未实现   |
| 题型                       | `questionType`                            | `assignments.question_type`                              | M5    | 已冻结   | 候选   | 未实现   |
| 标准答案（学生视角不存在） | `answerKey`                               | `assignments.answer_key`（JSONB，服务端私有）            | M5    | 已冻结   | 候选   | 未实现   |
| 满分/截止/发布             | `maxScore`/`dueAt`/`publishedAt`          | `assignments.max_score`/`due_at`/`published_at`          | M5    | 已冻结   | 候选   | 未实现   |
| 发布教师                   | `teacherId`                               | `assignments.teacher_id`                                 | M5    | 已冻结   | 候选   | 未实现   |
| 学生答案                   | `answer`                                  | `submissions.answer`（JSONB）                            | M5    | 已冻结   | 候选   | 未实现   |
| 判分结果                   | `isCorrect`/`score`/`gradedAt`/`gradedBy` | `submissions.is_correct`/`score`/`graded_at`/`graded_by` | M5    | 已冻结   | 候选   | 未实现   |
| 幂等键                     | `idempotencyKey`                          | `submissions.idempotency_key`                            | M5    | 已冻结   | 候选   | 未实现   |
| 提交时间                   | `submittedAt`/`createdAt`                 | `submissions.submitted_at`/`created_at`                  | M5    | 已冻结   | 候选   | 未实现   |
| 学生姓名/学号（教师视角）  | `studentSummary.*`                        | 响应组合：`user_profiles`                                | M1    | 已冻结   | 候选   | 响应组合 |

要点：

- `answerKey` 学生视角**字段不存在**（不是 `null`），前端类型里也不定义它。
- `idempotencyKey` 由前端打开表单时生成、表单会话内复用；**浏览器只在内存持有，服务端落库用于去重**。
  不写 localStorage：跨会话复用旧键会把新提交命中成历史记录。
- `studentSummary` 是组合字段，`submissions` 只存 `student_id`。

### 2.6 错题本（未实现，契约已冻结）

| 前端字段     | JSON 契约字段                                                                   | 领域表.列                                                                                       | owner | 契约状态 | 列状态 | 来源   |
| ------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----- | -------- | ------ | ------ |
| 归属与关联   | `studentId`/`courseId`/`chapterId`/`assignmentId`/`submissionId`/`sourceTurnId` | `mistakes.student_id`/`course_id`/`chapter_id`/`assignment_id`/`submission_id`/`source_turn_id` | M5    | 已冻结   | 候选   | 未实现 |
| 收录来源     | `source`（`wrong_submission`/`manual`）                                         | `mistakes.source`                                                                               | M5    | 已冻结   | 候选   | 未实现 |
| 题目快照     | `question`（`stem`/`questionType`/`options`/`attachmentUrl`，JSONB）            | `mistakes.question`                                                                             | M5    | 已冻结   | 候选   | 未实现 |
| 学生答案快照 | `studentAnswer`（JSONB）                                                        | `mistakes.student_answer`                                                                       | M5    | 已冻结   | 候选   | 未实现 |
| 学生备注     | `note`（≤500）                                                                  | `mistakes.note`                                                                                 | M5    | 已冻结   | 候选   | 未实现 |
| 复习状态     | `status`（`active`/`resolved`/`archived`）                                      | `mistakes.status`                                                                               | M5    | 已冻结   | 候选   | 未实现 |

要点：

- 「加入错题本」只发 `source: "manual"`；**答疑结束不自动收录**（`mistakes.md` 的禁止路径）。
- `question`/`studentAnswer` 是快照，随快照走不 join 当前题面；其 JSONB 内部结构需带 `schemaVersion`（Q5）。

### 2.7 复习计划与提醒（未实现，契约已冻结）

| 前端字段               | JSON 契约字段                                                                                                 | 领域表.列                                    | owner | 契约状态 | 列状态 | 来源   |
| ---------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ----- | -------- | ------ | ------ |
| 计划标识与归属         | `id`/`studentId`                                                                                              | `study_plans.id`/`student_id`                | M5    | 已冻结   | 候选   | 未实现 |
| 标题/课程/章节         | `title`/`courseId`/`chapterId`                                                                                | `study_plans.title`/`course_id`/`chapter_id` | M5    | 已冻结   | 候选   | 未实现 |
| 来源                   | `source`（`tutoring`/`manual`/`imported`）                                                                    | `study_plans.source`                         | M5    | 已冻结   | 候选   | 未实现 |
| 来源轮次               | `sourceTurnId`                                                                                                | `study_plans.source_turn_id`                 | M5    | 已冻结   | 候选   | 未实现 |
| 状态/截止              | `status`/`dueAt`                                                                                              | `study_plans.status`/`due_at`                | M5    | 已冻结   | 候选   | 未实现 |
| 计划项                 | `items[]{id,planId,content,order,status,dueAt,chapterId,knowledgePoint,relatedMistakeId,relatedAssignmentId}` | `plan_items.*`                               | M5    | 已冻结   | 候选   | 未实现 |
| 「保存为计划」         | 只发 `sourceTurnId`（可覆盖 `courseId`/`dueAt`）                                                              | 不适用（M5 按 turnId 向 M3 取用建议）        | M3/M5 | 已冻结   | 不适用 | 未实现 |
| 提醒                   | `id`/`type`/`title`/`body`/`dueAt`/`isRead`/`readAt`                                                          | `reminders.*`                                | M5    | 已冻结   | 候选   | 未实现 |
| 计划项勾选（乐观更新） | `status`                                                                                                      | `plan_items.status`                          | M5    | 已冻结   | 候选   | 运行时 |

要点：

- 前端**不转存 `planSuggestion`**，只发 `sourceTurnId`，由 M5 调 M3 取用接口拉取并校验
  （`study-plans.md:9-25`）。客户端改写建议的路径因此不存在。
- 乐观勾选只在内存翻转，失败必须回滚；不得先写本地存储再假装成功。

### 2.8 数字人播报（未接线）

| 前端字段                | JSON 契约字段          | 领域表.列                                       | owner  | 契约状态 | 列状态 | 来源   |
| ----------------------- | ---------------------- | ----------------------------------------------- | ------ | -------- | ------ | ------ |
| 播报标识                | `utteranceId`          | 不适用（M4 若记 `playback_records` 由 M4 登记） | M4     | 已冻结   | 不适用 | 运行时 |
| 播报文本                | `text`                 | 不复制；正文在 `tutoring_turns.content`         | M3/M4  | 已冻结   | 不适用 | 运行时 |
| 情绪/动作               | `emotion`/`action`     | `tutoring_turns.emotion`/`action`               | M3     | 已冻结   | 候选   | 运行时 |
| 播放状态                | `AvatarPlaybackStatus` | 不适用                                          | —      | 已冻结   | 不适用 | 运行时 |
| 音量/语速/自动播报/字幕 | **契约无此字段**       | 见第 6 节（候选，未登记）                       | 待认领 | 无契约   | 未登记 | 未实现 |

要点：

- 只播报 `completed` 的完整回答；`delta` 拼接中的半截文本不播报。
- 停止播报用 `stop(utteranceId)`；停止**答疑**走 M3 的 stop 端点。两者不是同一件事。

## 3. 「浏览器不保存」≠「服务端不落库」

这一节单独列出：把两者混为一谈最容易在验收时漏账。

| 数据项                       | 浏览器侧                 | 服务端侧（契约要求）                                         | 归属      |
| ---------------------------- | ------------------------ | ------------------------------------------------------------ | --------- |
| 章节浏览 `idempotencyKey`    | 只在内存，刷新即换新键   | `learning_events` 落幂等键，用于同键去重与 409 判定          | M5        |
| 作业提交 `idempotencyKey`    | 只在内存，表单会话内复用 | `submissions` 落幂等键 + 唯一约束，重复提交返回首次记录      | M5        |
| `stopped`/`error`/断连的轮次 | 半截文本只在内存展示     | 轮次落库为 `aborted`、`isComplete=false`；阶段不推进         | M3        |
| 中断轮次的部分正文           | 只在内存展示             | **是否保存由 M3 定**（允许保留供展示，但不得计入已完成回答） | M3        |
| 播放状态、音量、字幕开关     | 只在内存                 | 无契约字段，当前不落库                                       | M4/待认领 |
| 输入草稿、加载/错误态        | 只在内存                 | 不涉及                                                       | —         |

结论：**浏览器不保存只说明「前端没有持久化」，不能推出「服务端没有这条记录」**；
反过来，前端有状态也不代表服务端已保存。验收必须分别取证。

## 4. 组合字段（不建列）

| 字段                                  | 为什么不落库                                    | 正确来源                             |
| ------------------------------------- | ----------------------------------------------- | ------------------------------------ |
| `Course.teacherName`                  | 改名后课程行不跟着变，会漂移                    | M1 `user_profiles.display_name` 组合 |
| `Course.studentCount`/`chapterCount`  | 与真实行数可能不一致，无约束保证同步            | 聚合计数                             |
| `StudentSummary.name`/`studentNumber` | 复制到提交/错题会随改名失真                     | M1 profile 组合                      |
| `TutoringResponse.hasEvidence`        | 与 `citations` 为空互为充要，存两处必有一处先坏 | 由引用数推导                         |
| `planSuggestion` 内容                 | 属 M3 生成的建议，M5 保存时重新取用             | M3 取用接口                          |
| 分页 `page`/`pageSize`/`total`        | 每次请求的视图参数                              | 查询参数                             |

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

学生端目前没有任何持久化偏好，也没有 `localStorage`/`sessionStorage` 使用（全仓检索确认）。
下面四项是产品上可能要、但**当前契约没有字段**的偏好。M2 不建表、不落库；谁认领谁登记。

| 偏好项                   | 现状               | 需要持久化吗         | 建议归属                               | 若持久化的候选列（未登记，不得引用）              | 影响                                                   |
| ------------------------ | ------------------ | -------------------- | -------------------------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| 自动播报下一轮           | 无（数字人未接线） | 需要（跨设备一致）   | M4 先定入参，M1/M5 择一持久化          | `student_preferences.auto_play_avatar`            | 只在前端存会换设备失效，且与 M4 组件不认的参数不一致   |
| 音量/语速                | 无                 | 需要                 | 同上                                   | `student_preferences.avatar_volume`/`avatar_rate` | 取值域（0—1、0.5—2）未定，先定契约再定列               |
| 字幕默认开启             | 无                 | 可选                 | 同上                                   | `student_preferences.subtitle_enabled`            | S1 不做，避免为一项偏好建表                            |
| 上次阅读章节（学习进度） | 无                 | 需要，但**不是偏好** | M5 按 `learning_events` 推导 + M6 展示 | 不建议新表                                        | 用 localStorage 记进度会跨设备丢失，且与 M6 统计对不上 |

> `student_preferences` 只是候选名：M2 不提交它的字典、不在任何 PR 建这张表。
> 认领前前端不读不写任何持久偏好设置。

## 7. 需要 owner 确认的问题（附建议与影响）

| #   | 问题                                                                                                    | 涉及  | 建议                                                                                            | 不解决的后果                                                        |
| --- | ------------------------------------------------------------------------------------------------------- | ----- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Q1  | `enrollments` 写入归 M1 还是 M5：`courses.md:207-217` 说选课端点属 M1，#69 矩阵把 `enrollments` 列在 M5 | M1/M5 | 契约优先：M1 写访问关系，M5 只读用于列表过滤；表 owner 记 M5、写入入口记 M1                     | 两边各建一张学生-班级表，鉴权与列表读到不同数据，学生能看到没选的课 |
| Q2  | `studentCount`/`chapterCount` 是否物化                                                                  | M5    | 不物化，查询聚合；确需性能再加快照并写刷新策略                                                  | 删章节后计数不减，教师端与学生端人数不一致且无人能修                |
| Q3  | `citations[].documentTitle` 存快照还是 join；章节删除时 `document_id` 的处置                            | M3/M5 | 引用存快照并记文档版本；删除课件前检查引用                                                      | 改名/删文档后历史引用标题变样，学生按旧标题找不到资料               |
| Q4  | `followUps` 用 JSONB 还是子表                                                                           | M3    | JSONB + `schemaVersion`，顺序由数组保证                                                         | 用子表却没有 `order`，刷新后追问顺序乱                              |
| Q5  | `mistakes.question`/`student_answer` 的 JSONB 是否版本化                                                | M5    | 加 `schemaVersion`，题型扩容按版本兼容读                                                        | 新增题型后旧错题渲染崩，复习时看不到题干                            |
| Q6  | 学习进度（最后阅读章节）由谁建模                                                                        | M5/M6 | 由 `learning_events` 推导，不新增进度表                                                         | 前端用 localStorage 记进度，换设备即丢                              |
| Q7  | 数字人偏好是否进 M4 组件契约                                                                            | M4    | 先补 `avatar-controller.md` 入参，再谈持久化                                                    | 前端自存音量，组件不认，改了没效果                                  |
| Q8  | 中断轮次存储：`status`/`abort_reason` 列名、半截正文是否入库、是否截断                                  | M3    | 轮次必须落 `aborted` + `isComplete=false`；正文按「可保留但标记未完成」实现并带 `schemaVersion` | 只落一半：要么统计把中断算成完成，要么学生回看时正文消失            |
| Q9  | `learning_events.payload` 的 JSONB 键命名（`chapterId` 还是 `chapter_id`）与 `schemaVersion`            | M5    | 内部键与契约一致（camelCase），版本字段必填；不要因外层列 snake_case 就改内部键                 | 键名漂移后 M6 消费端读不到 `chapterId`，事件静默丢字段              |

## 8. 与验收的关系

本文件只到「映射与归属」，**不含任何数据库证据**。真实 PostgreSQL 的读写、重启读回、幂等与越权验收
按 [acceptance.md](acceptance.md) 执行，未运行的项目一律不勾选。
前端参与验收只认两类证据：真实接口返回（浏览器 network / 服务端日志）与页面截图；
**fixture 渲染、`?mock=` 场景截图不得作为验收证据**。
