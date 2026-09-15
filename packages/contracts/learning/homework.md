# 作业发布与提交契约（M5 → M2 / M6）

教师发布作业、学生提交、自动/手动判分、错题自动收录触发。本契约**不含批阅 UI**
（M6 教师后台通过 M5 API 操作；team-plan.md:29）。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。

## 资源：Assignment

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `assignment_4d8e2b` |
| `courseId` | string | 是 | 所属课程 |
| `chapterId` | string \| null | 否 | 关联章节；可为 null（综合作业） |
| `title` | string | 是 | 1—100 字符 |
| `description` | string \| null | 否 | 题面/作业说明，≤ 8000 字符 |
| `questionType` | string | 是 | 见下方枚举 |
| `answerKey` | object \| null | 否 | 客观题答案键；**服务端私有不返回给学生**，见下方 |
| `maxScore` | integer | 是 | 满分，≥ 1 |
| `dueAt` | string \| null | 否 | 截止时间 UTC ISO 8601；null 表示无截止 |
| `publishedAt` | string \| null | 否 | 发布时间；为 null 表示草稿，学生不可见 |
| `teacherId` | string | 是 | 发布教师 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

### questionType 枚举

| 值 | 含义 | 判分来源 |
| --- | --- | --- |
| `single_choice` | 单选 | M5 服务端对照 `answerKey` 自动判分 |
| `multiple_choice` | 多选 | M5 服务端对照 `answerKey` 自动判分 |
| `fill_blank` | 填空 | M5 服务端对照 `answerKey` 自动判分（支持多个等价答案） |
| `short_answer` | 简答 | **教师批阅**（M6 教师端调用 M5 提交批阅结果） |
| `proof` | 证明/推导 | **教师批阅** |

> 客观题与主观题的判分权责**待 M3 / M6 共同确认**（见 [README.md](README.md) 待拍板第 3 条）。
> 本契约先按题型划分；若 M3 后续提供 AI 辅助判分，主观题可新增 `ai_assisted` 判分路径，
> 但**最终判定权仍在服务端**（不允许客户端自行声明 `isCorrect`）。

### answerKey 结构（学生请求中**永不返回**）

```json
{
  "options": ["A", "C"],
  "acceptableBlanks": ["极限", "limit"]
}
```

`answerKey` 是教师发布的标准答案，仅服务端可读。学生端调用 `GET /api/v1/assignments/{id}`
时**字段被剔除**（不返回 null，而是**字段不存在**）。这避免学生通过 `answerKey: null`
与 `answerKey: {…}` 的差异枚举答案是否存在。

## 资源：Submission

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `submission_7a3c1d` |
| `assignmentId` | string | 是 | 关联作业 |
| `studentId` | string | 是 | 提交学生用户 ID |
| `answer` | object \| string | 是 | 学生答案，结构随 `questionType` 而定 |
| `isCorrect` | boolean \| null | 否 | 判分结果；null 表示未判分（主观题待批阅） |
| `score` | integer \| null | 否 | 得分；null 表示未判分 |
| `gradedAt` | string \| null | 否 | 判分时间 UTC ISO 8601 |
| `gradedBy` | string | 是 | 判分来源：`auto` / `teacher` / `ai_assisted`（占位） |
| `idempotencyKey` | string | 是 | 客户端生成的幂等键，≤ 128 字符 |
| `submittedAt` | string | 是 | UTC ISO 8601 |
| `createdAt` | string | 是 | 服务端写入时间 UTC ISO 8601 |

> `submittedAt` 与 `createdAt` 通常是同一时刻，但 `submittedAt` 是学生意图时间，
> `createdAt` 是服务端持久化时间。重复请求（同一 `idempotencyKey`）返回首次的 `createdAt`。

## 端点

### `POST /api/v1/courses/{courseId}/assignments`

教师发布作业。学生角色调用返回 403。

请求：

```json
{
  "chapterId": "chapter_2c9e1a",
  "title": "习题 1.2 极限计算",
  "description": "求下列极限，写出主要步骤。",
  "questionType": "short_answer",
  "answerKey": null,
  "maxScore": 10,
  "dueAt": "2026-09-22T23:59:00Z"
}
```

响应 201：返回 Assignment 对象，**`answerKey` 字段保留**（教师视角）。
`publishedAt` 默认为当前时间（即时发布）；传 `publishedAt: null` 表示存为草稿。

### `GET /api/v1/courses/{courseId}/assignments`

学生列出已发布作业（`publishedAt` 非 null 且 ≤ 当前时间）。教师列出所有（含草稿）。

查询参数：`page` / `pageSize` / `chapterId?` / `published?`（仅教师有效）。

响应 200：分页列表，学生视角下**列表项不含 `answerKey`**。

### `GET /api/v1/assignments/{assignmentId}`

作业详情。学生视角剔除 `answerKey` 字段；越权返回 404。

### `POST /api/v1/assignments/{assignmentId}/submissions`

学生提交作业。**幂等设计**：

- 请求体必含 `idempotencyKey`，由客户端生成（建议 UUID v4 或随机串）
- 同一 `(assignmentId, studentId, idempotencyKey)` 重复提交：服务端返回**首次创建的 Submission**
  （含首次的 `id` 与 `createdAt`），HTTP 状态码 200（而非 201）
- 不同 `idempotencyKey` 但同一作业的二次提交：返回 409 `SUBMISSION_ALREADY_EXISTS`，
  响应体含已有 submission 的 `id`，引导客户端用 PATCH 修改

请求：

```json
{
  "answer": {
    "options": ["A", "C"]
  },
  "idempotencyKey": "idem_8f3a2b9c1d4e5f6a"
}
```

响应 201（首次）或 200（重复幂等键）：

```json
{
  "id": "submission_7a3c1d",
  "assignmentId": "assignment_4d8e2b",
  "studentId": "user_b8c1d2",
  "answer": { "options": ["A", "C"] },
  "isCorrect": true,
  "score": 10,
  "gradedAt": "2026-09-15T14:32:00Z",
  "gradedBy": "auto",
  "idempotencyKey": "idem_8f3a2b9c1d4e5f6a",
  "submittedAt": "2026-09-15T14:32:00Z",
  "createdAt": "2026-09-15T14:32:00Z"
}
```

### `GET /api/v1/assignments/{assignmentId}/submissions/me`

学生查看自己的提交。无提交返回 404 `SUBMISSION_NOT_FOUND`。

### `GET /api/v1/assignments/{assignmentId}/submissions`

教师列出该作业所有学生提交（用于批阅）。学生调用返回 403。
分页参数同上，可按 `studentId` / `isCorrect` 过滤。

### `PATCH /api/v1/submissions/{submissionId}/grading`

教师批阅主观题。请求体：

```json
{
  "isCorrect": false,
  "score": 6,
  "gradedBy": "teacher"
}
```

响应 200：返回更新后的 Submission。**批阅完成后触发错题自动收录**（见 [mistakes.md](mistakes.md)）。

> 本端点**学生角色调用返回 403**。判分结果由服务端写入，**客户端不得在提交请求中携带 `isCorrect`**
> （与 tutoring-response.md:31 的「请求体禁止 `stage`」是同源约束）。

## 不变量

1. **`answerKey` 不出现在学生视角的任何响应中。** 列表项与详情都剔除该字段，
   不是设为 null。这是防枚举的硬要求。
2. **同一 `(assignmentId, studentId)` 最多一条有效 Submission。**
   幂等键机制保证重试不重复创建；不同键的二次提交需走 PATCH 修改流程。
3. **客观题提交后立即判分（`gradedBy: "auto"`）。** 主观题 `isCorrect` / `score` 初始为 null，
   待教师批阅后填充。
4. **`isCorrect` 一旦写入不可回退为 null。** 教师可重新批阅覆盖 `true`↔`false`，
   但不得清除判分状态（保证错题收录的触发不会因状态翻转丢失）。
5. **错题自动收录只在 `isCorrect` 从 null → false 的翻转时刻触发一次。**
   重复请求或 `isCorrect` 已是 false 的二次批阅不重复收录。
6. **截止时间 `dueAt` 是软约束，不阻止提交。** 超时提交仍可创建，
   但 `submittedAt > dueAt` 时由 M6 统计层标注为「迟交」（不归 M5 业务范畴）。
7. **草稿作业（`publishedAt = null`）学生不可见。** 列表与详情都返回 404。

## 学习事件

提交完成、批阅完成均发布学习事件，见 [learning-events.md](learning-events.md)。

| 事件 | 触发时机 | 关键 payload |
| --- | --- | --- |
| `assignment_submitted` | 学生提交成功（含幂等重试命中已有记录） | `submissionId`, `assignmentId`, `isCorrect?` |
| `assignment_graded` | 教师批阅完成或自动判分完成 | `submissionId`, `isCorrect`, `score?` |

## 错误响应

| code | HTTP | 场景 |
| --- | --- | --- |
| `ASSIGNMENT_NOT_FOUND` | 404 | 作业不存在或无权访问 |
| `SUBMISSION_NOT_FOUND` | 404 | 学生查询自身提交时无记录 |
| `SUBMISSION_ALREADY_EXISTS` | 409 | 同一作业已有不同幂等键的提交 |
| `SUBMISSION_DRAFT_LOCKED` | 409 | 作业为草稿，不接受提交 |
| `VALIDATION_ERROR` | 422 | 请求体含禁止字段（如提交中的 `isCorrect`） |
| `FORBIDDEN_ROLE` | 403 | 学生调用教师端点 |

**越权访问私有 submission 返回 404**，与防枚举策略一致。
