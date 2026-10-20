# 学生端字段映射与偏好归属（M2）

关联 [#70](https://github.com/StephenYI43/software-engineering-group-1/issues/70)、[#69](https://github.com/StephenYI43/software-engineering-group-1/issues/69)。
owner：M2 / @Saber-www；评审：M1、M5。
基线：`main` `d01f32e`（2026-10-20）。
状态：**字段映射草案。本文件不登记新表**，不建迁移、不改 API，也不代表任何列已在数据库中存在。

本文回答的是「学生端每一页显示的每个字段，最终落在哪张表的哪一列、由谁拥有、现在是真数据还是示意数据」。
七要素字典按 owner 分文件（平台 `platform.md`、学习 `learning.md`、答疑 `tutoring-knowledge.md`、
数字人 `avatar-media.md`），**M2 不重复登记业务表**；这里只做映射、偏好归属判定与 UI 临时态说明。

## 0. 口径（读之前先确认这四条）

1. **列名状态分两档。** `已冻结` 表示该列已被契约或已合并文档点名（例如 `courses.md` 的 JSON 字段）；
   `候选` 表示按 `docs/code-standards.md:49`（表名复数、列 snake_case）从 JSON 字段推导，
   **等对应 owner 的字典提交后才算数**。全表只标注，不把候选列当作已确认。
2. **来源分三档。** `fixture` = 前端示意数据，界面带「示意数据」标识；
   `未实现` = 只有契约、没有代码通路；`不落库` = 组合字段或运行时状态。
   main 上**没有任何学生端数据来自真实后端**，验收时不得把 fixture 当持久化证据。
3. **表名沿用 #69 的候选清单**（`courses`/`chapters`/`assignments`/`submissions`/`mistakes`/`study_plans`/`plan_items`/`reminders`/
   `tutoring_sessions`/`tutoring_turns`/`turn_citations`/`learning_events`）。除 learning 域外，这些表名仍是候选。
4. **学生端不直连数据库，也不持有模型密钥。** 本文只描述字段来源，任何写路径都必须经服务端接口
   （`docs/code-standards.md:33`、`AGENTS.md:5`）。

## 1. 页面清单与当前数据来源

| 路由 | 页面 | main 现状 | 数据入口 | 契约端点 | 后端实现 |
| --- | --- | --- | --- | --- | --- |
| `/courses` | 课程列表 | 已实现（S0，示意数据） | `features/student/api/courses-client.ts` → `mocks/index.ts` | `GET /api/v1/courses` | M5，未实现 |
| `/courses/:courseId` | 课程详情 + 章节列表 | 已实现（S0，示意数据） | 同上 | `GET /api/v1/courses/{courseId}`、`/chapters` | M5，未实现 |
| `/tutoring/:sessionId` | 答疑（单轮展示） | 已实现（S0，示意数据） | `mocks/index.ts` 的 `fetchTutoringTurn` | `POST /tutoring/sessions/{id}/messages`（SSE） | M3，PR #62 未合并；M2 SSE 客户端在 PR #68，未合并 |
| 章节正文 | 阅读页 | **未实现**（只有章节列表） | — | `ChapterViewedIntent` 上报 | M5/M1 未冻结路径（`packages/contracts/student/learning-events.md:30`） |
| 作业列表/详情/提交 | 作业 | **未实现** | — | `GET /courses/{courseId}/assignments` 等 | M5，未实现 |
| 错题本 | 错题 | **未实现** | — | `/api/v1/mistakes` | M5，未实现 |
| 复习计划/提醒 | 计划 | **未实现** | — | `/api/v1/study-plans`、`/reminders` | M5，未实现 |
| 数字人播报 | 组件 | **未接线** | — | `AvatarController`（组件契约，非 HTTP） | M4，PR #61 未合并 |

> 上表是 main 的实际情况。已合并的只有 S0 路由骨架与示意数据；SSE 交互、数字人接线都还是开放 PR，
> 阅读时不要把 PR 描述当成已上线的能力。

## 2. 逐页字段映射

### 2.1 课程列表 `/courses`

| 前端字段 | JSON 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| `Course.id` | `id` | `courses.id` | M5 | 候选 | fixture |
| `Course.title` | `title` | `courses.title` | M5 | 候选 | fixture |
| `Course.description` | `description` | `courses.description` | M5 | 候选 | fixture |
| `Course.subject` | `subject` | `courses.subject` | M5 | 候选 | fixture |
| `Course.coverImageUrl` | `coverImageUrl` | `courses.cover_image_url` | M5 | 候选 | fixture |
| `Course.teacherId` | `teacherId` | `courses.teacher_id` | M5 | 候选 | fixture |
| `Course.teacherName` | `teacherName` | 组合：`user_profiles.display_name` | M1 | 已冻结 | 不落库 |
| `Course.studentCount` | `studentCount` | 聚合：`enrollments` 计数 | M5（写入待确认，见 Q1） | 候选 | fixture |
| `Course.chapterCount` | `chapterCount` | 聚合：`chapters` 计数 | M5 | 候选 | fixture |
| `Course.createdAt` | `createdAt` | `courses.created_at` | M5 | 候选 | fixture |
| `Course.updatedAt` | `updatedAt` | `courses.updated_at` | M5 | 候选 | fixture |
| 分页 `page` / `pageSize` / `total` | 查询参数与信封 | 不落库 | — | — | fixture |

要点：

- `teacherName` 按 `courses.md:228` 不持久化在 `courses`，由服务端按 `teacher_id` 组合 M1 的 profile 回填。
  前端拿到 `null` 时必须能渲染（当前实现是「主讲：—」缺省不显示）。
- `studentCount` / `chapterCount` 契约只写「可回填」。**建议不物化成列**（见 Q2）：物化列会与 `enrollments`、
  `chapters` 的真实行数漂移，且没有约束能在删课时同步修正。
- `subject` 收到枚举外的值时回退显示原值，这是前端逻辑，不产生任何持久化字段。

### 2.2 课程详情与章节 `/courses/:courseId`

| 前端字段 | JSON 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 课程头部字段 | 同 2.1 | 同 2.1 | M5 | 候选 | fixture |
| `Chapter.id` | `id` | `chapters.id` | M5 | 候选 | fixture |
| `Chapter.courseId` | `courseId` | `chapters.course_id` | M5 | 候选 | fixture |
| `Chapter.title` | `title` | `chapters.title` | M5 | 候选 | fixture |
| `Chapter.order` | `order` | `chapters.order` | M5 | 候选 | fixture |
| `Chapter.description` | `description` | `chapters.description` | M5 | 候选 | fixture |
| `Chapter.documentId` | `documentId` | `chapters.document_id` | M5（引用 M3 `documents.id`） | 候选 | fixture |
| `Chapter.createdAt` / `updatedAt` | 同名 | `chapters.created_at` / `updated_at` | M5 | 候选 | fixture |
| 章节正文（当前无阅读页） | — | `document_chunks` 等 | M3 | — | 未实现 |

要点：

- `documentId` 只是跨域引用，**不存放文档内容**，也不代表学生有权阅读（授权在 M3 的 `document_grants`，
  检索前校验，见 `avatar` 之外的 `0004-rag-retrieval-boundary.md`）。前端只显示「已关联课件」。
- 章节删除后 `document_id` 如何处理（置空还是禁止删除）属 M5/M3 边界，M2 不单方定义。

### 2.3 章节浏览事件（当前无阅读页，契约已冻结）

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 路由参数 `courseId` | `courseId` | `learning_events.course_id` | M5 | 候选 | 未实现 |
| 路由参数 `chapterId` | `payload.chapterId` | `learning_events.payload.chapter_id`（JSONB） | M5 | 候选 | 未实现 |
| 会话身份 | `userId` | `learning_events.user_id` | M1（注入）/ M5（写入） | 候选 | 不落库 |
| 前端生成 `idempotencyKey` | `idempotencyKey` | `learning_events.idempotency_key`（幂等唯一键） | M5 | 候选 | 本地生成 |
| — | `eventId` / `occurredAt` / `traceId` / `schemaVersion` | 同名同义 | M5 | 候选 | 服务端生成 |

要点：

- 浏览器只提交「意图」，`eventType` 由服务端固定为 `chapter_viewed`，客户端不能自选事件类型。
- `idempotencyKey` 只活在一次浏览动作内（内存即可），**不写 localStorage**：写本地会让「刷新后是否算新浏览」
  变成设备相关行为，而契约要求由页面显式生成新键来表达。
- 事件与统计的时间语义：`occurredAt` 不是写入游标（M6 用 ingestion 单调键），M2 不传客户端时钟。

### 2.4 答疑 `/tutoring/:sessionId`

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 路由参数 | `sessionId` | `tutoring_sessions.id` | M3 | 候选 | fixture |
| 输入框内容 | `content`（1—2000 字） | `tutoring_turns.user_content` | M3 | 候选 | 本地输入 |
| 课程限定（可选） | `courseId` | `tutoring_sessions.course_id` | M3 | 候选 | 不落库（透传） |
| 学生请求阶段（可选） | `requestedStage` | `tutoring_turns.requested_stage`（可空） | M3 | 候选 | 不落库 |
| 落库归属学生 | — | `tutoring_sessions.user_id` | M3 | 候选 | 服务端会话 |
| 回答正文 | `content` | `tutoring_turns.content` | M3 | 候选 | fixture |
| 教学阶段 | `stage` | `tutoring_turns.stage` | M3 | 候选 | fixture |
| 引用列表 | `citations[]` | `turn_citations`（`turn_id`、`citation_id`、`document_id`、`page_number`、`snippet`） | M3 | 候选 | fixture |
| 引用标题 | `citations[].documentTitle` | `turn_citations.document_title`（快照）或 join `documents.title` | M3 | 待定（Q3） | fixture |
| 是否有依据 | `hasEvidence` | 可推导（引用数 > 0），不建议单独存列 | M3 | 候选 | fixture |
| 追问建议 | `followUps[]`（≤3×200 字） | `tutoring_turns.follow_ups`（JSONB，见 Q4） | M3 | 候选 | fixture |
| 情绪/动作 | `emotion` / `action` | `tutoring_turns.emotion` / `action` | M3 | 候选 | fixture |
| 是否 Mock | `isMock` | `tutoring_turns.is_mock` | M3 | 候选 | fixture |
| 提示词版本 | `promptVersion` | `tutoring_turns.prompt_version_id`（引用 `prompt_versions`） | M3 | 候选 | fixture |
| 本轮时间 | `createdAt` | `tutoring_turns.created_at` | M3 | 候选 | fixture |
| 播报标识 | `utteranceId` | 不落库（M4 若要 `playback_records` 由 M4 登记） | M4 | — | 本地生成 |
| 流式中间态（`seq`、已拼接的半截文本、停止中、重试计数） | 不落库 | — | — | — | 运行时 |

要点：

- **半截回答不算一轮**：只有收到终止帧（`isComplete: true`）的 `completed` 才是完整回答；`error` / `stopped` 的正文
  在服务端不落库，前端也不能把它当完整记录展示（`docs/code-standards.md:95`）。
- `emotion` / `action` 是 M3 映射、M4 消费的输出字段，M2 只透传，不自行推导、不缓存成偏好。
- `isMock` 必须原样展示（当前 `MockDataBadge`），它表示「这轮回答由假模型产生」，与「fixture 示意数据」是两件事。

### 2.5 作业与提交（未实现，契约已冻结）

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 作业标识/课程/班级/章节 | `id`/`courseId`/`classId`/`chapterId` | `assignments.id` / `course_id` / `class_id` / `chapter_id` | M5 | 候选 | 未实现 |
| 作业标题/说明 | `title`/`description` | `assignments.title` / `description` | M5 | 候选 | 未实现 |
| 题型 | `questionType` | `assignments.question_type` | M5 | 候选 | 未实现 |
| 标准答案（**学生视角不存在该字段**） | `answerKey` | `assignments.answer_key`（JSONB，服务端私有） | M5 | 候选 | 未实现 |
| 满分/截止/发布时间 | `maxScore`/`dueAt`/`publishedAt` | `assignments.max_score` / `due_at` / `published_at` | M5 | 候选 | 未实现 |
| 发布教师 | `teacherId` | `assignments.teacher_id` | M5 | 候选 | 未实现 |
| 学生答案 | `answer`（object 或 string） | `submissions.answer`（JSONB） | M5 | 候选 | 未实现 |
| 判分结果 | `isCorrect`/`score`/`gradedAt`/`gradedBy` | `submissions.is_correct` / `score` / `graded_at` / `graded_by` | M5 | 候选 | 未实现 |
| 幂等键 | `idempotencyKey`（≤128 字符） | `submissions.idempotency_key` | M5 | 候选 | 本地生成 |
| 提交时间 | `submittedAt`/`createdAt` | `submissions.submitted_at` / `created_at` | M5 | 候选 | 未实现 |
| 学生姓名/学号（教师视角组合） | `studentSummary.name` / `studentNumber` | 组合：`user_profiles` | M1 | 已冻结 | 不落库 |

要点：

- `answerKey` 学生视角**字段不存在**（不是 `null`），避免枚举答案是否存在。前端类型里也刻意不定义该字段。
- `idempotencyKey` 由前端在打开表单时生成一次、表单会话内复用；**只存内存**，不进 localStorage——
  跨会话复用旧键会在服务端命中历史提交，让「新一次提交」被当成重试。
- `studentSummary` 是响应组合字段，`submissions` 只存 `student_id`，不复制姓名学号。

### 2.6 错题本（未实现，契约已冻结）

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 归属与关联 | `studentId`/`courseId`/`chapterId`/`assignmentId`/`submissionId`/`sourceTurnId` | `mistakes.student_id` / `course_id` / `chapter_id` / `assignment_id` / `submission_id` / `source_turn_id` | M5 | 候选 | 未实现 |
| 收录来源 | `source`（`wrong_submission`/`manual`） | `mistakes.source` | M5 | 候选 | 未实现 |
| 题目快照 | `question`（`stem`/`questionType`/`options`/`attachmentUrl`） | `mistakes.question`（JSONB） | M5 | 候选 | 未实现 |
| 学生答案快照 | `studentAnswer` | `mistakes.student_answer`（JSONB） | M5 | 候选 | 未实现 |
| 学生备注 | `note`（≤500 字） | `mistakes.note` | M5 | 候选 | 未实现 |
| 复习状态 | `status`（`active`/`resolved`/`archived`） | `mistakes.status` | M5 | 候选 | 未实现 |

要点：

- 「加入错题本」按钮只发 `source: "manual"`；**答疑结束不自动收录**（`mistakes.md` 禁止路径）。
  前端不得因为「这题看着难」或「模型提到了它」就提交收录。
- `question` 是收录时刻的快照，`options` / `attachmentUrl` 随快照走，不 join 当前作业题面。
- `note` 是学生自己的文字，前端只做长度校验，不做内容改写；服务端负责最终校验。

### 2.7 复习计划与提醒（未实现，契约已冻结）

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 计划标识与归属 | `id`/`studentId` | `study_plans.id` / `student_id` | M5 | 候选 | 未实现 |
| 计划标题/课程/章节 | `title`/`courseId`/`chapterId` | `study_plans.title` / `course_id` / `chapter_id` | M5 | 候选 | 未实现 |
| 来源 | `source`（`tutoring`/`manual`/`imported`） | `study_plans.source` | M5 | 候选 | 未实现 |
| 来源轮次 | `sourceTurnId` | `study_plans.source_turn_id` | M5 | 候选 | 未实现 |
| 计划状态/截止 | `status`/`dueAt` | `study_plans.status` / `due_at` | M5 | 候选 | 未实现 |
| 计划项 | `items[]{id,planId,content,order,status,dueAt,chapterId,knowledgePoint,relatedMistakeId,relatedAssignmentId}` | `plan_items.*`（同名 snake_case） | M5 | 候选 | 未实现 |
| 答疑页「保存为计划」 | 只发 `sourceTurnId`（+ 可覆盖 `courseId`/`dueAt`） | 不落库（建议内容由 M3 取用接口提供） | M3/M5 | — | 未实现 |
| 提醒 | `id`/`type`/`title`/`body`/`dueAt`/`isRead`/`readAt` | `reminders.*` | M5 | 候选 | 未实现 |
| 计划项勾选（乐观更新） | `status` | `plan_items.status` | M5 | 候选 | 运行时 |

要点：

- 前端**不转存 `planSuggestion` 内容**，只发 `sourceTurnId`，由 M5 调 M3 取用接口拉取并校验
  （`study-plans.md:9-25`）。这样「客户端改写建议」这条攻击面直接消失。
- 乐观勾选只在内存里翻转，失败必须回滚并提示；不得先写本地存储再假装成功。

### 2.8 数字人播报（未接线）

| 前端字段 | 契约字段 | 领域表.列 | owner | 列名状态 | 当前来源 |
| --- | --- | --- | --- | --- | --- |
| 播报标识 | `utteranceId` | 不落库；M4 若记 `playback_records` 由 M4 登记 | M4 | — | 本地生成 |
| 播报文本 | `text` | 不落库（正文在 `tutoring_turns.content`，不复制） | M3/M4 | — | 运行时 |
| 情绪/动作 | `emotion`/`action` | `tutoring_turns.emotion` / `action` | M3 | 候选 | 运行时 |
| 播放状态 | `AvatarPlaybackStatus` | 不落库 | — | — | 运行时 |
| 音量/语速/自动播报/字幕 | **契约无此字段** | 见第 5 节 | 待认领 | 未登记 | 未实现 |

要点：

- `speak` 的文本**只应是 `completed` 的完整回答**，`delta` 拼接中的半截文本不播报；
  停止播报用 `stop(utteranceId)`，不用 `AbortController` 去掐 SSE（两者语义不同）。
- 播放状态是运行时状态，刷新即丢，不持久化。

## 3. 组合字段与不落库字段（防止重复建列）

| 字段 | 为什么不落库 | 正确来源 |
| --- | --- | --- |
| `Course.teacherName` | 用户改名后课程行不跟着变，会漂移 | M1 `user_profiles.display_name` 组合 |
| `Course.studentCount` / `chapterCount` | 与真实行数可能不一致，且无约束能保证同步 | 聚合计数 |
| `StudentSummary.name` / `studentNumber` | 复制到提交/错题会随改名失真 | M1 profile 组合 |
| `TutoringResponse.hasEvidence` | 与 `citations` 是否为空互为充要，存两处必有一处先坏 | 由引用数推导 |
| `citations[].documentTitle` | 若为快照则需固定文档版本；若 join 则改名后历史引用变样 | 待 M3 定（Q3） |
| `planSuggestion` 全部内容 | 属 M3 生成的建议，M5 保存时重新取用 | M3 取用接口 |
| 分页 `page`/`pageSize`/`total` | 每次请求的视图参数 | 查询参数 |

## 4. UI 临时态：无需持久化

| 状态 | 位置 | 为什么不需要持久化 | 若误持久化的后果 |
| --- | --- | --- | --- |
| 输入框草稿（提问、答案、备注） | 答疑/作业/错题 | 未提交内容不是业务事实，刷新即弃是明确产品语义 | 会把「没提交」变成「有记录」，与提交幂等键冲突 |
| 流式半截回答、`seq`、重试计数 | 答疑 | 只有终止帧才是完整回答，中间态由连接生命周期决定 | 半截文本进库后无法区分「模型中断」与「学生看到过」 |
| 停止中/停止超时提示 | 答疑 | 连接状态，重启即失效 | 会伪造「已停止」的服务端事实 |
| 加载/空/错误态 | 全部页面 | 由请求状态派生 | 会掩盖真实错误 |
| 表单校验错误、行内提示 | 全部表单 | 派生状态 | — |
| `?mock=` 场景开关、`?turn=` 演示轮次 | 全部页面 | **开发态**演示开关，生产构建会移除 | 会把 Mock 行为带进验收证据 |
| 列表排序/筛选/页码 | 列表页 | 放 URL query，可分享、可前进后退 | 放本地存储会让同一链接在不同人处显示不同内容 |
| 计划项乐观勾选 | 计划页 | 以服务端结果为准，失败回滚 | 断网时显示「已完成」而库里没有 |
| 数字人播放状态 | 播报组件 | 运行时状态 | — |

判断标准只有一条：**这个状态是不是「服务端必须知道的事实」**。是，就走服务端接口；不是，就留在内存或 URL。

## 5. 偏好归属：候选表不归 M2

学生端目前**没有任何持久化偏好**，也没有 `localStorage`/`sessionStorage` 使用（已 grep 确认）。
下面四项是产品上可能会要、但**当前契约里不存在字段**的偏好。M2 不建表、不自行落库，
按「服务端 owner 认领」处理。

| 偏好项 | 现状 | 是否需持久化 | 建议归属 | 若持久化的候选列（**未登记，不得引用**） | 结论 |
| --- | --- | --- | --- | --- | --- |
| 自动播报下一轮回答 | 无（数字人未接线） | 需要（跨设备一致） | M4 定义入参 + M1/M5 择一持久化 | `student_preferences.auto_play_avatar` | 等 M4 契约补字段再谈持久化 |
| 音量 / 语速 | 无 | 需要 | 同上 | `student_preferences.avatar_volume` / `avatar_rate` | 同上；范围为 0—1、0.5—2 需 M4 定 |
| 字幕默认开启 | 无 | 可选 | 同上 | `student_preferences.subtitle_enabled` | S1 不做 |
| 上次阅读到哪一章（学习进度） | 无 | 需要，但**不是偏好** | M5 学习进度（`learning_events` 可推导）+ M6 展示 | 不建议新表；按事件推导 | 不得用 localStorage 冒充进度 |

> `student_preferences` 只是候选名，**M2 不提交它的字典，也不在任何 PR 里建这张表**。
> 谁认领谁登记：若 M1 认为属于平台用户设置，放 `user_profiles` 扩展；若 M5 认为属学习业务，走 `student_preferences`。
> 在认领前，前端不读取、不写入任何持久偏好。

## 6. 需要 owner 确认的问题（带建议与反例）

| # | 问题 | 涉及 | 建议 | 反例（不解决会怎样） |
| --- | --- | --- | --- | --- |
| Q1 | `enrollments` 的写入归 M1 还是 M5：`courses.md:207-217` 说选课端点属 M1，#69 矩阵把 `enrollments` 列在 M5 | M1/M5 | 以契约为主：M1 写访问关系、M5 只读用于列表过滤；表 owner 写 M5、写入入口归 M1 | 两边各建一张「学生-班级」表，列表过滤与鉴权读到不同数据，学生能看到没选的课 |
| Q2 | `studentCount`/`chapterCount` 是否物化成列 | M5 | 不物化，查询时聚合；确需性能再加快照并写清刷新策略 | 删章节后计数不减，教师端与学生端人数不一致且无人能修 |
| Q3 | `citations[].documentTitle` 存快照还是 join `documents.title` | M3 | 存快照并同时记文档版本；否则改标题/删文档后历史引用不可追溯 | 教师改名后旧回答的引用标题全变，学生按旧标题找不到资料 |
| Q4 | `followUps` 用 JSONB 还是子表 | M3 | JSONB + `schemaVersion`，顺序敏感但无需按条查询 | 用子表却没有 `order` 列，刷新后追问顺序乱 |
| Q5 | `mistakes.question` / `student_answer` 的 JSONB 内部结构是否随题型版本化 | M5 | 加 `schemaVersion`，题型扩容时按版本兼容读 | 新增题型后旧错题渲染崩，复习时看不到题干 |
| Q6 | 学习进度（最后阅读章节）由谁建模 | M5/M6 | 由 `learning_events` 推导，不新增「进度表」 | 前端用 localStorage 记进度，换设备即丢，且与 M6 统计对不上 |
| Q7 | 数字人偏好（音量/语速/自动播报）是否进 M4 组件契约 | M4 | 若要持久化，先在 `avatar-controller.md` 补入参，再谈库 | 前端自己存一个音量，M4 组件不认，改了没效果 |

## 7. 与验收的关系

本文件只到「映射与归属」，**不含任何数据库证据**。真实 PostgreSQL 的读写、重启读回、幂等与越权验收
按 [acceptance.md](acceptance.md) 执行，未运行的项目一律不勾选。
前端参与验收时只允许两类证据：真实接口返回（浏览器 network / 服务端日志）与页面截图；
**fixture 渲染结果、`?mock=` 场景下的截图不得作为验收证据**。
