# 错误响应样例

所有错误响应遵循 `docs/code-standards.md:74-80` 的统一结构：

```json
{
  "code": "ERROR_CODE",
  "message": "人类可读说明",
  "requestId": "req_xxx",
  "details": {}
}
```

> `requestId` 关联 M1 的请求追踪（`docs/code-standards.md:88`）。
> 越权访问一律返回 404，不区分「不存在」与「不属于你」（防枚举，`docs/code-standards.md:82`）。

## 404 防枚举（越权与不存在统一返回）

### `ASSIGNMENT_NOT_FOUND`

作业不存在，或学生访问草稿作业，或越权访问他人课程作业。

```json
{
  "code": "ASSIGNMENT_NOT_FOUND",
  "message": "作业不存在或无权访问",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": { "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c" }
}
```

### `SUBMISSION_NOT_FOUND`

越权访问他人提交（防枚举）；**自己尚未提交改为 200 + `null`**（见 [homework.md](../homework.md) 的 `GET /api/v1/assignments/{assignmentId}/submissions/me`）。

> 上一版用 404 `SUBMISSION_NOT_FOUND` 同时表达「自己尚未提交」与「越权查他人」，被 M2 评审（PR #26 第 C 条）指出与 M1 的 HTTP 语义映射冲突
> （404 统一表述「未找到」会让正常状态被渲染成错误）。本版改为：本错误码只用于越权查询他人提交，自己尚未提交返回 200 + `null`。

```json
{
  "code": "SUBMISSION_NOT_FOUND",
  "message": "越权访问他人提交：未找到或无权访问",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": { "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c" }
}
```

### `MISTAKE_NOT_FOUND`

错题不存在或不属于当前用户。

```json
{
  "code": "MISTAKE_NOT_FOUND",
  "message": "错题不存在或无权访问",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "mistakeId": "mistake_9c4b2e5f6a7b8c9d0e1f2a3b4c5d6e7f" }
}
```

### `PLAN_NOT_FOUND` / `PLAN_ITEM_NOT_FOUND` / `REMINDER_NOT_FOUND`

计划、计划项或提醒不存在或不属于当前用户。

```json
{
  "code": "PLAN_NOT_FOUND",
  "message": "计划不存在或无权访问",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "planId": "plan_6d8a3c4d5e6f7a8b9c0d1e2f3a4b5c6d" }
}
```

```json
{
  "code": "REMINDER_NOT_FOUND",
  "message": "提醒不存在或无权访问",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "reminderId": "reminder_5e8d2a4b5c6d7e8f9a0b1c2d3e4f5a6b" }
}
```

### `TUTORING_TURN_NOT_FOUND`

`source = "tutoring"` 但 `sourceTurnId` 经 M3 取用接口校验不通过
（不存在或不属于当前学生，M3 一律 404 防枚举）。

> 本错误码是 **404 防枚举**（不是 422 校验失败）：来源 turnId 不存在或不归属当前学生，
> M3 取用接口统一返回 404（防枚举），M5 透传为 404 而非 422，避免让客户端用 422/404 差异枚举 turnId 存在性。

```json
{
  "code": "TUTORING_TURN_NOT_FOUND",
  "message": "导学建议来源不存在或无权访问",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "sourceTurnId": "turn_7f3a9c214d5e6f7a8b9c0d1e2f3a4b5c" }
}
```

## 409 冲突

### `SUBMISSION_ALREADY_EXISTS`

同一作业已有不同幂等键的提交，引导客户端用 PATCH 修改。

```json
{
  "code": "SUBMISSION_ALREADY_EXISTS",
  "message": "该作业已提交，请使用 PATCH 修改",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": {
    "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c",
    "existingSubmissionId": "submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e"
  }
}
```

### `SUBMISSION_DRAFT_LOCKED`

作业为草稿（`publishedAt = null`），不接受提交。

```json
{
  "code": "SUBMISSION_DRAFT_LOCKED",
  "message": "作业未发布，暂不接受提交",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": { "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c" }
}
```

## 422 校验失败

### `PLAN_ITEMS_LIMIT_EXCEEDED`

计划项超过 20 条上限。

```json
{
  "code": "PLAN_ITEMS_LIMIT_EXCEEDED",
  "message": "单个计划最多 20 项，请拆分为多个计划",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "itemsCount": 21, "max": 20 }
}
```

### `PLAN_DUE_IN_PAST`

`dueAt` 早于当前时间。

```json
{
  "code": "PLAN_DUE_IN_PAST",
  "message": "截止时间不能早于当前时间",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "dueAt": "2026-09-10T23:59:00Z", "now": "2026-09-15T15:30:00Z" }
}
```

### `VALIDATION_ERROR`

其他校验失败：客户端伪造 `source = "wrong_submission"`、提交请求体含禁止字段
（如 `isCorrect`）、批阅请求体含禁止字段（如 `gradedBy`）、`source = "tutoring"` 请求体包含 `items` 等。

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求体校验失败：source=wrong_submission 只能由服务端写入",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": { "field": "source", "reason": "forbidden_client_value" }
}
```

`source = "tutoring"` 请求体包含 `items` 时：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "source=tutoring 时请求体不得包含 items，计划内容由 M3 提供",
  "requestId": "req_9e2b4d116f7a8b9c0d1e2f3a4b5c6d7e",
  "details": { "field": "items", "reason": "forbidden_when_source_tutoring" }
}
```

批阅请求体含 `gradedBy` 时（`gradedBy` 由服务端推导，不接受请求体传入）：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "批阅请求体不得包含 gradedBy，判分来源由服务端推导",
  "requestId": "req_a1b2c3d47b8c9d0e1f2a3b4c5d6e7f8a",
  "details": { "field": "gradedBy", "reason": "forbidden_server_derived" }
}
```

## 403 角色越权

### `FORBIDDEN_ROLE`

学生角色调用教师端点（如发布作业、批阅），或教师角色调用学生端点
（如读写学生错题本、学生计划）。

```json
{
  "code": "FORBIDDEN_ROLE",
  "message": "当前角色无权调用此端点",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": { "role": "student", "endpoint": "POST /api/v1/courses/{courseId}/assignments" }
}
```

> 注意：学生访问**他人**的计划/错题/提交不返回 403，而是 404（防枚举）。
> 403 仅用于角色级别不匹配（如学生调用教师端点）。

## 200 非错误（幂等命中已有记录）

### `MISTAKE_DUPLICATE`

重复收录命中已有 `active` 记录，**非错误**，HTTP 200 返回已有对象，
不写入新行也不发布 `mistake_recorded` 事件。

响应体即已有的 Mistake 对象（与首次 201 返回的结构一致），
不带错误结构。详见 [05-mistake-manual.json](05-mistake-manual.json) 的 `response_200_duplicate`。
