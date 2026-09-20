# 复习计划与提醒契约（M5 → M2 / M3）

学生保存、编辑复习计划；M3 答疑产生导学建议后由 M5 校验保存；站内截止提醒。
S1 不实现间隔复习、抽背默写（`docs/tasks/m5.md:15` 把这些划到 S2）。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。ID 形态为 `<前缀>_<32 位小写 hex>`
（见 [README.md](README.md)「ID 形态」）。

## 与 M3 的边界

`docs/team-plan.md:29`：「M3 生成计划建议，M5 校验后保存」。
M3 已确认（见 Issue #17）在 `TutoringResponse` 新增 `planSuggestion` 字段（可选，无建议时为 `null`），
并提供服务端取用接口。**前端不参与转存**，避免客户端改写计划内容与单独校验 `turnId` 归属两个衍生问题
（`docs/code-standards.md:95`：客户端不能自行推进教学状态绕过后端校验）。

M5 保存路径：
- 学生在 M2 答疑界面看到 `planSuggestion` 后点击「保存为计划」，前端只发 `sourceTurnId` 给 M5；
- **M5 service 层按 `sourceTurnId` 调用 M3 取用接口拉取 `planSuggestion`**，校验 `turnId` 存在且属于当前学生
  与取内容合并为同一次调用（M3 对不存在或不归属的 `turnId` 一律 404，防枚举，沿用 `tutoring-response.md:194` 约定）；
- M5 校验建议合理性（截止日期、计划项数等）、持久化、发布学习事件。
- M5 保存时**按 `knowledgePoint` 或学生当前课程/章节匹配填入 `chapterId`**（见下方映射）。

> 此路径依赖 M3 在 `tutoring-response.md` 落地 `planSuggestion` 字段与取用接口（M3 待开 Issue）。
> M3 落地前，M5 service 层对 `source = "tutoring"` 的请求 stub 返回拒绝写入并在 PR 说明中标注 Mock 行为
> （`AGENTS.md:4`、`docs/code-standards.md:69`）。

### M3 `planSuggestion` 的字段形状（M3 提供，M5 消费）

M5 期望从 M3 取用接口拿到的 `planSuggestion` 形状如下（M5 持久化层字段 `id` / `studentId` / `status`
由 M5 自行生成，不在 `planSuggestion` 内）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 1—100 字符 |
| `items` | array | 是 | 计划项，1—20 项 |
| `items[].content` | string | 是 | 1—500 字符 |
| `items[].chapterId` | string \| null | 否 | **M3 传 null**（章节是 M5 实体，M3 不生成 M5 域 ID） |
| `items[].knowledgePoint` | string \| null | 否 | 知识点标注（自由文本，属 M3 域） |
| `items[].suggestedDueAt` | string \| null | 否 | M3 建议的单项截止 UTC ISO 8601 |
| `suggestedPlanDueAt` | string \| null | 否 | M3 建议的计划整体截止 UTC ISO 8601 |

> `mistakeId` / `studentId` / `id` / `status` 等**持久化层字段**不在 `planSuggestion` 中
> （由 M5 保存时生成）。`items[].relatedMistakeId` 在 M3 建议中不出现，
> M5 保存时若需关联错题由 M5 自行解析或留空。

> **`chapterId` 归属（M3 在 PR #26 评审确认方案 A）**：章节是 M5 的实体（[courses.md](courses.md)），
> M3 不拥有也不应生成 M5 域 ID。M3 在 `planSuggestion.items[].chapterId` 一律传 `null`；
> **M5 保存时**按 `items[].knowledgePoint` 或学生当前课程/章节匹配填入 PlanItem 的 `chapterId`。
> 这样「答疑出建议」链路不依赖 M5 服务在线（M3 不反向调 M5 课程接口）。

**M5 的职责边界**：校验建议合理性（如截止日期不早于今天、计划项不超过上限）、
持久化、提供编辑与提醒、按 `knowledgePoint` 解析 `chapterId`。**不**承担建议生成职责。

## 资源：StudyPlan

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `plan_6d8a3c4d5e6f7a8b9c0d1e2f3a4b5c6d` |
| `studentId` | string | 是 | 计划归属学生 |
| `title` | string | 是 | 1—100 字符 |
| `courseId` | string \| null | 否 | 关联课程；通用计划为 null |
| `chapterId` | string \| null | 否 | 关联章节 |
| `source` | string | 是 | 见下方枚举 |
| `sourceTurnId` | string \| null | 否 | 来自 M3 答疑时填，关联 turnId |
| `status` | string | 是 | 见下方枚举 |
| `items` | array | 是 | 计划项列表，1—20 项 |
| `dueAt` | string \| null | 否 | 计划整体截止时间 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

### source 枚举

| 值 | 含义 |
| --- | --- |
| `tutoring` | 来自 M3 答疑导学建议 |
| `manual` | 学生手动创建 |
| `imported` | 从模板/历史计划导入（S2 扩展） |

### status 枚举

| 值 | 含义 |
| --- | --- |
| `active` | 进行中 |
| `completed` | 学生标记完成 |
| `archived` | 归档 |

### 计划项：PlanItem

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `plan_item_3a1b2c4d5e6f7a8b9c0d1e2f3a4b5c6d` |
| `planId` | string | 是 | 所属计划 |
| `content` | string | 是 | 计划项内容，1—500 字符 |
| `order` | integer | 是 | 计划内排序，≥ 1 |
| `status` | string | 是 | `pending` / `done` |
| `dueAt` | string \| null | 否 | 单项截止时间 |
| `chapterId` | string \| null | 否 | 关联章节（M5 保存时按 knowledgePoint 解析填入） |
| `knowledgePoint` | string \| null | 否 | 知识点标注（来自 M3 建议时保留） |
| `relatedMistakeId` | string \| null | 否 | 关联错题，用于「复习这条错题」类计划项 |
| `relatedAssignmentId` | string \| null | 否 | 关联作业 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

## 端点

### `POST /api/v1/study-plans`

学生保存计划。两种 `source` 的请求体不同：

- `source = "tutoring"`：前端只传 `sourceTurnId`（可选覆盖 `title` / `dueAt`），**不传 `items`**。
  M5 service 层按 `sourceTurnId` 调用 M3 取用接口拉取 `planSuggestion` 后写入（见上方「与 M3 的边界」）。
- `source = "manual"`：学生自建计划，传完整结构。

请求（`source = "manual"`，学生自建）：

```json
{
  "title": "极限与连续 复习计划",
  "courseId": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "chapterId": "chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b",
  "source": "manual",
  "dueAt": "2026-09-22T23:59:00Z",
  "items": [
    {
      "content": "重做错题：求 lim(x→0) sin(x)/x",
      "order": 1,
      "relatedMistakeId": "mistake_9c4b2e5f6a7b8c9d0e1f2a3b4c5d6e7f",
      "dueAt": "2026-09-18T23:59:00Z"
    },
    {
      "content": "复习 ε-δ 定义并整理笔记",
      "order": 2,
      "dueAt": "2026-09-20T23:59:00Z"
    }
  ]
}
```

请求（`source = "tutoring"`，从 M3 建议保存——前端只发 turnId）：

```json
{
  "source": "tutoring",
  "sourceTurnId": "turn_7f3a9c214d5e6f7a8b9c0d1e2f3a4b5c",
  "courseId": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "dueAt": "2026-09-22T23:59:00Z"
}
```

> `source = "tutoring"` 时 `title` / `items` 由 M3 `planSuggestion` 提供，前端**不得**在请求体中传 `items`
> （防止客户端改写建议内容）。`courseId` / `dueAt` 可由学生覆盖。M5 从 M3 取到的 `planSuggestion.items`
> 映射为 PlanItem：
> - `content` → PlanItem.`content`
> - `suggestedDueAt` → PlanItem.`dueAt`
> - `knowledgePoint` → PlanItem.`knowledgePoint`
> - `chapterId`：M3 传 null，**M5 保存时**按 `knowledgePoint` 或学生当前课程/章节匹配填入 PlanItem.`chapterId`
>   （与计划级 `chapterId` 就高取非空值）。

响应 201：返回完整 StudyPlan 对象（含 `items`）。

**M5 的校验职责**（写入前）：

1. `items` 长度 1—20
2. `dueAt` 不早于当前时间（如设置）
3. `source = "tutoring"` 时 `sourceTurnId` 必填，**且请求体不得包含 `items`**
   （防止客户端改写 M3 建议内容）。M5 service 层按 `sourceTurnId` 调用 M3 取用接口，
   一次调用完成校验与取内容（M3 对不归属 turnId 返回 404，见上方「与 M3 的边界」）。
   M3 接口未落地前 stub 返回 404 拒绝写入。
4. `relatedMistakeId` 必须属于当前学生
5. `relatedAssignmentId` 必须属于学生已选课程
6. `order` 在同一计划内唯一且 ≥ 1

### `GET /api/v1/study-plans`

学生列出自己的计划。

查询参数：`page` / `pageSize` / `courseId?` / `status?`（默认 `active`）。

### `GET /api/v1/study-plans/{planId}`

计划详情（含 `items`）。越权返回 404。

### `PATCH /api/v1/study-plans/{planId}`

学生修改计划（`title` / `dueAt` / `status`）。

### `POST /api/v1/study-plans/{planId}/items`

向计划添加新项。`order` 由服务端续编。

### `PATCH /api/v1/study-plans/{planId}/items/{itemId}`

修改计划项（`content` / `status` / `dueAt` / `order`）。

### `DELETE /api/v1/study-plans/{planId}/items/{itemId}`

删除计划项。**剩余 `items` 不重排 `order`**（避免并发改写）。

## 资源：Reminder（站内提醒）

> S1 只实现**站内截止提醒**（`docs/tasks/m5.md:14`、`docs/requirements.md` F04「截止提醒」）。
> 不实现推送、邮件、外部通知。提醒由服务端在截止前 N 小时扫描并生成。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `reminder_5e8d2a4b5c6d7e8f9a0b1c2d3e4f5a6b` |
| `studentId` | string | 是 | 提醒归属学生 |
| `planId` | string \| null | 否 | 关联计划项；非计划提醒为 null |
| `assignmentId` | string \| null | 否 | 关联作业 |
| `type` | string | 是 | 见下方枚举 |
| `title` | string | 是 | 1—100 字符 |
| `body` | string \| null | 否 | 提醒正文，≤ 500 字符 |
| `dueAt` | string | 是 | 关联截止时间 UTC ISO 8601 |
| `isRead` | boolean | 是 | 是否已读 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `readAt` | string \| null | 否 | UTC ISO 8601 |

### type 枚举

| 值 | 含义 |
| --- | --- |
| `plan_due` | 计划或计划项即将到期 |
| `assignment_due` | 作业即将到期 |
| `mistake_review_due` | 间隔复习提醒（S2，S1 不实现） |

## 提醒端点

### `GET /api/v1/reminders`

学生列出自己的提醒。默认按 `dueAt` 升序。

查询参数：`page` / `pageSize` / `isRead?` / `type?`。

### `PATCH /api/v1/reminders/{reminderId}`

标记已读或未读。

```json
{
  "isRead": true
}
```

## 不变量

1. **学生只能读写自己的计划与提醒。** 越权返回 404。
2. **`items` 长度 1—20。** 超过 20 需拆为多个计划。这是防止单计划过长导致学生无法执行。
3. **`order` ≥ 1，同一计划内唯一。** 删除项不重排，前端按 `order` 升序展示。
4. **`dueAt` 不早于当前时间。** 校验在 service 层，写入前拒绝。
5. **`source = "tutoring"` 时 `sourceTurnId` 必填，且请求体不得包含 `items`。**
   M5 service 层按 `sourceTurnId` 调用 M3 取用接口（校验+取内容合并为一次调用，
   M3 对不归属 turnId 返回 404 防枚举）。M3 接口未落地前 stub 返回 404 拒绝写入，
   PR 说明中标注 Mock 行为（`AGENTS.md:4`）。
6. **`chapterId` 由 M5 保存时填入，M3 在建议中传 null。** 见上方映射。
7. **站内提醒只由服务端生成。** 学生不能 `POST /api/v1/reminders` 自建提醒，
   只能调整计划/作业的 `dueAt`，由服务端扫描时生成对应提醒。
8. **提醒 `isRead = true` 后 `readAt` 必填。** 标记未读时 `readAt` 清空为 null。
9. **已删除计划项的关联提醒一并删除。** 不悬空引用。

## 学习事件

计划保存、计划项完成均发布学习事件，见 [learning-events.md](learning-events.md)。

| 事件 | 触发时机 | 关键 payload |
| --- | --- | --- |
| `study_plan_saved` | 计划创建或修改 | `planId`, `source`, `itemsCount` |
| `plan_item_completed` | 计划项 `status` 翻转到 `done` | `planId`, `itemId` |
| `reminder_triggered` | 服务端扫描生成提醒 | `reminderId`, `type`, `dueAt` |

## 错误响应

| code | HTTP | 场景 |
| --- | --- | --- |
| `PLAN_NOT_FOUND` | 404 | 计划不存在或不属于当前用户 |
| `PLAN_ITEM_NOT_FOUND` | 404 | 计划项不存在或不属于该计划 |
| `REMINDER_NOT_FOUND` | 404 | 提醒不存在或不属于当前用户 |
| `PLAN_ITEMS_LIMIT_EXCEEDED` | 422 | 计划项超过 20 条 |
| `PLAN_DUE_IN_PAST` | 422 | `dueAt` 早于当前时间 |
| `TUTORING_TURN_NOT_FOUND` | 404 | `source = "tutoring"` 但 `sourceTurnId` 校验失败（M3 对不归属 turnId 一律 404，本契约与之一致） |
| `VALIDATION_ERROR` | 422 | 其他校验失败 |
| `FORBIDDEN_ROLE` | 403 | 教师角色调用学生计划端点 |

> `TUTORING_TURN_NOT_FOUND` 用 404（M2 在 PR #26 第 E 条要求与 M3 的 404 防枚举一致）：
> 学生点「保存为计划」时若该轮已失效或不属于他，正确文案是「这条回答已失效，请重新提问」，
> 而非 422 的「输入有误」。状态码与 M3 侧的 404 保持一致。
