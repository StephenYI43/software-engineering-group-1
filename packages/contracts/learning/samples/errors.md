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
  "requestId": "req_8d1f0c33",
  "details": { "assignmentId": "assignment_4d8e2b" }
}
```

### `SUBMISSION_NOT_FOUND`

学生查询自身提交时无记录，或越权查他人提交。

```json
{
  "code": "SUBMISSION_NOT_FOUND",
  "message": "未找到提交记录",
  "requestId": "req_8d1f0c33",
  "details": { "assignmentId": "assignment_4d8e2b" }
}
```

### `MISTAKE_NOT_FOUND`

错题不存在或不属于当前用户。

```json
{
  "code": "MISTAKE_NOT_FOUND",
  "message": "错题不存在或无权访问",
  "requestId": "req_9e2b4d11",
  "details": { "mistakeId": "mistake_9c4b2e" }
}
```

### `PLAN_NOT_FOUND` / `PLAN_ITEM_NOT_FOUND` / `REMINDER_NOT_FOUND`

计划、计划项或提醒不存在或不属于当前用户。

```json
{
  "code": "PLAN_NOT_FOUND",
  "message": "计划不存在或无权访问",
  "requestId": "req_9e2b4d11",
  "details": { "planId": "plan_6d8a3c" }
}
```

```json
{
  "code": "REMINDER_NOT_FOUND",
  "message": "提醒不存在或无权访问",
  "requestId": "req_9e2b4d11",
  "details": { "reminderId": "reminder_5e8d2a" }
}
```

## 409 冲突

### `SUBMISSION_ALREADY_EXISTS`

同一作业已有不同幂等键的提交，引导客户端用 PATCH 修改。

```json
{
  "code": "SUBMISSION_ALREADY_EXISTS",
  "message": "该作业已提交，请使用 PATCH 修改",
  "requestId": "req_8d1f0c33",
  "details": {
    "assignmentId": "assignment_4d8e2b",
    "existingSubmissionId": "submission_7a3c1d"
  }
}
```

### `SUBMISSION_DRAFT_LOCKED`

作业为草稿（`publishedAt = null`），不接受提交。

```json
{
  "code": "SUBMISSION_DRAFT_LOCKED",
  "message": "作业未发布，暂不接受提交",
  "requestId": "req_8d1f0c33",
  "details": { "assignmentId": "assignment_4d8e2b" }
}
```

## 422 校验失败

### `PLAN_ITEMS_LIMIT_EXCEEDED`

计划项超过 20 条上限。

```json
{
  "code": "PLAN_ITEMS_LIMIT_EXCEEDED",
  "message": "单个计划最多 20 项，请拆分为多个计划",
  "requestId": "req_9e2b4d11",
  "details": { "itemsCount": 21, "max": 20 }
}
```

### `PLAN_DUE_IN_PAST`

`dueAt` 早于当前时间。

```json
{
  "code": "PLAN_DUE_IN_PAST",
  "message": "截止时间不能早于当前时间",
  "requestId": "req_9e2b4d11",
  "details": { "dueAt": "2026-09-10T23:59:00Z", "now": "2026-09-15T15:30:00Z" }
}
```

### `TUTORING_TURN_NOT_FOUND`

`source = "tutoring"` 但 `sourceTurnId` 经 M3 取用接口校验不通过
（不存在或不属于当前学生，M3 一律 404 防枚举）。

```json
{
  "code": "TUTORING_TURN_NOT_FOUND",
  "message": "导学建议来源不存在或无权访问",
  "requestId": "req_9e2b4d11",
  "details": { "sourceTurnId": "turn_7f3a9c21" }
}
```

### `VALIDATION_ERROR`

其他校验失败：客户端伪造 `source = "wrong_submission"`、提交请求体含禁止字段
（如 `isCorrect`）、`source = "tutoring"` 请求体包含 `items` 等。

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求体校验失败：source=wrong_submission 只能由服务端写入",
  "requestId": "req_8d1f0c33",
  "details": { "field": "source", "reason": "forbidden_client_value" }
}
```

`source = "tutoring"` 请求体包含 `items` 时：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "source=tutoring 时请求体不得包含 items，计划内容由 M3 提供",
  "requestId": "req_9e2b4d11",
  "details": { "field": "items", "reason": "forbidden_when_source_tutoring" }
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
  "requestId": "req_8d1f0c33",
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
