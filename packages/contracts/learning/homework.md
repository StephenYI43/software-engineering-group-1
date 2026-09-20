# 作业发布与提交契约（M5 → M2 / M6）

教师发布作业、学生提交、自动/手动判分、错题自动收录触发。本契约**不含批阅 UI**
（M6 教师后台通过 M5 API 操作；team-plan.md:29）。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。ID 形态为 `<前缀>_<32 位小写 hex>`
（见 [README.md](README.md)「ID 形态」）。

## 资源：Assignment

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c` |
| `courseId` | string | 是 | 所属课程 |
| `classId` | string \| null | 否 | 所属教学班；为 null 表示对有权学生全员可见（S1 单班演示可空） |
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

> 以上是**作业题型**。错题本 `question` 快照在「答疑后主动标记」场景下，
> 题目来源是 M3 答疑的自由文本，不属于作业题型——此时 `questionType` 用 `tutoring_question`，
> 详见 [mistakes.md](mistakes.md) 的 question 结构。

> 客观题与主观题的判分权责**待 M3 / M6 共同确认**（见 [README.md](README.md) 待拍板第 4 条）。
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
| `id` | string | 是 | 形如 `submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e` |
| `assignmentId` | string | 是 | 关联作业 |
| `classId` | string \| null | 否 | 提交时所在班级（从作业透传，便于统计） |
| `studentId` | string | 是 | 提交学生用户 ID（稳定 ID，不复制姓名/学号） |
| `answer` | object \| string | 是 | 学生答案，结构随 `questionType` 而定 |
| `isCorrect` | boolean \| null | 否 | 判分结果；null 表示未判分（主观题待批阅） |
| `score` | integer \| null | 否 | 得分；null 表示未判分 |
| `gradedAt` | string \| null | 否 | 判分时间 UTC ISO 8601 |
| `gradedBy` | string | 是 | 判分来源：`auto` / `teacher` / `ai_assisted`（占位）。**由服务端写入，不接受请求体传入** |
| `idempotencyKey` | string | 是 | 客户端生成的幂等键，≤ 128 字符 |
| `submittedAt` | string | 是 | UTC ISO 8601 |
| `createdAt` | string | 是 | 服务端写入时间 UTC ISO 8601 |

> `submittedAt` 与 `createdAt` 通常是同一时刻，但 `submittedAt` 是学生意图时间，
> `createdAt` 是服务端持久化时间。重复请求（同一 `idempotencyKey`）返回首次的 `createdAt`。

### StudentSummary（教师批阅列表响应中组合，不持久化）

`submissions` 表**只保存稳定 `studentId`**，不复制姓名/学号。教师批阅列表响应中，
服务端通过 M1 profile 组合最小 `StudentSummary` 嵌入列表项，便于 M6 批阅 UI 渲染：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `studentId` | string | 学生用户 ID |
| `name` | string \| null | 学生姓名（M1 profile 解析，可能为空） |
| `studentNumber` | string \| null | 学号（M1 维护，可能为空） |

> `StudentSummary` 是**响应组合字段**，不进 `submissions` 表（避免学生改姓名时数据漂移）。

## 端点

### `POST /api/v1/courses/{courseId}/assignments`

教师发布作业。学生角色调用返回 403。

请求：

```json
{
  "classId": "class_f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6",
  "chapterId": "chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b",
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

学生列出已发布作业（`publishedAt` 非 null 且 ≤ 当前时间），仅限自己所在班级。教师列出所有（含草稿）。

查询参数：`page` / `pageSize` / `classId?` / `chapterId?` / `published?`（仅教师有效）。

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

#### idempotencyKey 生命周期（M2 在 PR #26 第 B 条要求明确）

为避免「重试命中 409」与「改动静默丢失」两个坑，契约规定客户端键管理策略：

| 阶段 | 键状态 | 行为 |
| --- | --- | --- |
| 打开提交表单 | 生成一次新键 | 整个表单会话复用此键 |
| 提交成功前重试 | 复用同一键 | 网络超时/失败重试命中首次记录，返回 200，不触发 409 |
| 提交成功（201） | 键作废 | 该键不再用于后续编辑 |
| 进入编辑（PATCH 修改） | 重新生成新键 | 改答案再交走 PATCH 流程，不复用旧提交键 |

> 此策略与 M5 的 409 行为兼容：409 只在「同一作业已有**不同键**的提交」时出现，
> 即学生已成功提交后又用**新键**重新 POST——这是「二次提交」语义，由 PATCH 流程承接，
> 幂等重试（同键）不会落到 409。客户端按上表管理键即可避免误触 409。

请求：

```json
{
  "answer": {
    "options": ["A", "C"]
  },
  "idempotencyKey": "idem_8f3a2b9c1d4e5f6a7b8c9d0e1f2a3b4c"
}
```

响应 201（首次）或 200（重复幂等键）：

```json
{
  "id": "submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e",
  "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c",
  "classId": "class_f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6",
  "studentId": "user_b8c1d23e4f5a6b7c8d9e0f1a2b3c4d5e",
  "answer": { "options": ["A", "C"] },
  "isCorrect": true,
  "score": 10,
  "gradedAt": "2026-09-15T14:32:00Z",
  "gradedBy": "auto",
  "idempotencyKey": "idem_8f3a2b9c1d4e5f6a7b8c9d0e1f2a3b4c",
  "submittedAt": "2026-09-15T14:32:00Z",
  "createdAt": "2026-09-15T14:32:00Z"
}
```

### `GET /api/v1/assignments/{assignmentId}/submissions/me`

学生查看自己的提交。**无提交时返回 200 + `null`**（「尚未提交」是正常状态，不是错误）。

> 上一版用 404 `SUBMISSION_NOT_FOUND` 表达「尚未提交」，被 M2 评审（PR #26 第 C 条）指出与
> M1 的 HTTP 语义映射冲突（404 统一表述「未找到」会让正常状态被渲染成错误）。本版改为 200 + null。

响应 200（已提交）：

```json
{
  "submission": {
    "id": "submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e"
  }
}
```

响应 200（尚未提交）：

```json
{
  "submission": null
}
```

> 越权访问他人提交仍返回 404（防枚举），但「自己尚未提交」不再用 404。

### `GET /api/v1/assignments/{assignmentId}/submissions`

教师列出该作业所有学生提交（用于批阅）。学生调用返回 403。

查询参数：`page` / `pageSize` / `studentId?` / `graded?`（`true` / `false`）。

- `graded=true`：只返回已批阅（`gradedAt` 非 null）的提交
- `graded=false`：只返回未批阅（`gradedAt` 为 null）的提交，便于教师优先处理待批阅
- 不传 `graded`：返回全部

> 上一版让客户端以 `isCorrect=null` 猜测是否已批阅，被 M1 评审（PR #26 第 2 条）指出后改为显式
> `graded` 过滤。`isCorrect` 是判分结果，`gradedAt` 是否非 null 才是「是否已批阅」的判据。

响应 200（列表项含 `studentSummary`，不含 `answerKey` 影响只在学生视角，教师视角列表项可含 `answerKey`）：

```json
{
  "items": [
    {
      "id": "submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e",
      "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c",
      "studentId": "user_b8c1d23e4f5a6b7c8d9e0f1a2b3c4d5e",
      "studentSummary": {
        "studentId": "user_b8c1d23e4f5a6b7c8d9e0f1a2b3c4d5e",
        "name": "张三",
        "studentNumber": "20260001"
      },
      "answer": { "text": "设 ε>0 任给……" },
      "isCorrect": null,
      "score": null,
      "gradedAt": null,
      "gradedBy": "auto",
      "submittedAt": "2026-09-15T16:00:00Z",
      "createdAt": "2026-09-15T16:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "pageSize": 20
}
```

> 批量批阅留 S2，S1 不实现。

### `PATCH /api/v1/submissions/{submissionId}/grading`

教师批阅主观题。**`gradedBy` 由服务端按会话角色推导，不进请求体**（与 platform 契约
「服务端从已验证会话获取 role，不信任请求体自报」一致，见 M2 评审 PR #26 第 D 条）。

请求：

```json
{
  "isCorrect": false,
  "score": 6
}
```

响应 200：返回更新后的 Submission，`gradedBy` 由服务端写入（`teacher` 或 `auto`/`ai_assisted`）。
**批阅完成后触发错题自动收录**（见 [mistakes.md](mistakes.md)）。

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
8. **`gradedBy` 由服务端推导，不接受请求体传入。** 客户端自报判分来源会被服务端忽略并返回 422。
9. **`submissions` 表只存稳定 `studentId`。** 姓名学号不持久化，由 `StudentSummary` 响应组合。

## 学习事件

提交完成、批阅完成均发布学习事件，见 [learning-events.md](learning-events.md)。

| 事件 | 触发时机 | 关键 payload |
| --- | --- | --- |
| `assignment_submitted` | 学生提交成功（含幂等重试命中已有记录） | `submissionId`, `assignmentId`, `questionType`, `isCorrect?`, `score?` |
| `assignment_graded` | 教师批阅完成或自动判分完成 | `submissionId`, `isCorrect`, `score?` |

> `isCorrect` / `score` 在 `assignment_submitted` 中**可空**：客观题自动判分时填入，
> 主观题提交时为 null（待批阅后才确定）。见 [learning-events.md](learning-events.md)。

## 错误响应

| code | HTTP | 场景 |
| --- | --- | --- |
| `ASSIGNMENT_NOT_FOUND` | 404 | 作业不存在或无权访问 |
| `SUBMISSION_NOT_FOUND` | 404 | 越权查询他人提交（**自己尚未提交改为 200 null**，见上方） |
| `SUBMISSION_ALREADY_EXISTS` | 409 | 同一作业已有不同幂等键的提交 |
| `SUBMISSION_DRAFT_LOCKED` | 409 | 作业为草稿，不接受提交 |
| `VALIDATION_ERROR` | 422 | 请求体含禁止字段（如提交中的 `isCorrect`、批阅请求中的 `gradedBy`） |
| `FORBIDDEN_ROLE` | 403 | 学生调用教师端点 |

**越权访问私有 submission 返回 404**，与防枚举策略一致。
