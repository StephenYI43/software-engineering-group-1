# 学习事件契约（M2 / M4 / M5 → M6）

M5 在学习业务关键节点发布事件，M6 消费后聚合统计（`docs/code-standards.md:92`、
`docs/team-plan.md:29`「M6 从学习事件聚合统计，不改动其他领域数据」）。

本契约定义 M5 发布侧的事件 schema。M2 / M4 的事件 schema 由各自负责人定义，
本契约只确保字段命名与 `eventId` / `eventType` / `userId` / `occurredAt` / `traceId` / `schemaVersion`
六个公共字段一致（code-standards.md:92 的硬要求）。

## 传输方式

S1 实现：M5 在 service 层事务提交后，向 `learning_events` 表追加一条记录
（与业务写入同事务，保证「业务成功必有事件」）。M6 通过**轮询**或**触发器视图**消费。

S2 视情况升级为消息队列。**当前不引入 MQ**，避免在 M1 脚手架未稳定前增加基础设施。

> 跨领域走事件而非直连表（code-standards.md:33）。M6 **不**直接 `SELECT * FROM learning_events`
> 之后做统计——它通过本契约的字段约束读取事件，聚合结果写入 `analytics` 域自己的表
> （`docs/team-plan.md:25` 把 `apps/api/app/domains/analytics` 划给 M6）。
> `learning_events` 表由 M5 写、M6 只读。

## 公共字段（所有事件必填）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `eventId` | string | 形如 `event_3f8a2c`，全局唯一 |
| `eventType` | string | 见下方枚举 |
| `userId` | string | 学生用户 ID（事件主体） |
| `courseId` | string \| null | 关联课程；非课程事件为 null |
| `occurredAt` | string | UTC ISO 8601，事件实际发生时间 |
| `traceId` | string | 关联 M1 requestId（code-standards.md:88），便于跨服务追踪 |
| `schemaVersion` | string | 事件 schema 版本，初版 `1.0` |
| `payload` | object | 事件特有字段，见下方 |

> `eventId` 是事件本身的唯一键，**不是业务实体的 ID**。
> 例如 `assignment_submitted` 事件的 `eventId` 与 `submissionId` 是两个不同的 ID。

## eventType 枚举（M5 发布侧）

| 值 | 触发时机 | payload 关键字段 |
| --- | --- | --- |
| `assignment_submitted` | 学生提交作业成功（含幂等重试命中已有记录——见下方幂等说明） | `submissionId`, `assignmentId`, `questionType` |
| `assignment_graded` | 自动判分或教师批阅完成 | `submissionId`, `isCorrect`, `score?` |
| `mistake_recorded` | 自动或手动收录成功（**首次**收录，幂等命中不发布） | `mistakeId`, `source`, `assignmentId?` |
| `mistake_resolved` | 错题 `status` 翻转到 `resolved` | `mistakeId` |
| `study_plan_saved` | 计划创建或修改 | `planId`, `source`, `itemsCount` |
| `plan_item_completed` | 计划项 `status` 翻转到 `done` | `planId`, `itemId` |
| `reminder_triggered` | 服务端扫描生成提醒 | `reminderId`, `type`, `dueAt` |
| `chapter_viewed` | 学生打开章节（M2 也可发布，schema 由 M2 定义） | `chapterId` |

> `chapter_viewed` 列在 M5 表中是因为它属于「学习行为事件」，但**实际由 M2 发布**
> （前端行为事件，不归 M5 业务后端）。本契约只列出 schema 共识，**M5 不实现**这条事件。
> M2 的发布 schema 由 M2 单独定义并交 M6 评审。

## 事件样例

### `assignment_submitted`

```json
{
  "eventId": "event_3f8a2c",
  "eventType": "assignment_submitted",
  "userId": "user_b8c1d2",
  "courseId": "course_b3f1c2d4",
  "occurredAt": "2026-09-15T14:32:00Z",
  "traceId": "req_8d1f0c33",
  "schemaVersion": "1.0",
  "payload": {
    "submissionId": "submission_7a3c1d",
    "assignmentId": "assignment_4d8e2b",
    "questionType": "single_choice",
    "isCorrect": true,
    "score": 10
  }
}
```

### `mistake_recorded`

```json
{
  "eventId": "event_5b9c1e",
  "eventType": "mistake_recorded",
  "userId": "user_b8c1d2",
  "courseId": "course_b3f1c2d4",
  "occurredAt": "2026-09-15T14:32:00Z",
  "traceId": "req_8d1f0c33",
  "schemaVersion": "1.0",
  "payload": {
    "mistakeId": "mistake_9c4b2e",
    "source": "wrong_submission",
    "assignmentId": "assignment_4d8e2b",
    "chapterId": "chapter_2c9e1a"
  }
}
```

### `study_plan_saved`

```json
{
  "eventId": "event_7d3a1f",
  "eventType": "study_plan_saved",
  "userId": "user_b8c1d2",
  "courseId": "course_b3f1c2d4",
  "occurredAt": "2026-09-15T15:00:00Z",
  "traceId": "req_9e2b4d11",
  "schemaVersion": "1.0",
  "payload": {
    "planId": "plan_6d8a3c",
    "source": "tutoring",
    "itemsCount": 2
  }
}
```

## 不变量

1. **事件只追加，不修改不删除。** `learning_events` 表是 append-only。
   M6 的统计如果出错，通过更正事件或反向事件修正，不删原始记录。
2. **业务事务提交后才写事件。** M5 service 层在事务内同时写业务表与 `learning_events`，
   保证「业务成功必有事件，业务失败无事件」。这是事务一致性要求，不是性能优化。
3. **`eventId` 全局唯一。** 由 M5 服务端生成，**不接受客户端传入**。
4. **幂等命中已有记录时不重复发布事件。** 见下方。
5. **`schemaVersion` 变更需向后兼容或显式迁移。** 新增字段不破坏旧消费者；
   破坏性变更需升 `schemaVersion` 并由 M6 同步迁移消费逻辑。

## 幂等与事件去重

部分业务有幂等键（如作业提交的 `idempotencyKey`）。**幂等命中已有记录时**：

- 业务上返回 200 与已有记录（见 [homework.md](homework.md)）
- **不重复发布 `assignment_submitted` 事件**——避免 M6 统计重复计数

判断规则：事件发布在 service 层事务内，**只在首次 INSERT 成功时发布**。
重复请求命中已有行时 service 层跳过事件发布。

这一规则同样适用于：

- `mistake_recorded`：[mistakes.md](mistakes.md) 的去重键命中已有 `active` 记录时不发布
- `study_plan_saved`：PATCH 修改计划时**重新发布**（视为新事件，因 `payload` 不同）
- `plan_item_completed`：`status` 从 `done` 翻回 `pending` 再翻到 `done` 时**重新发布**
  （同一 itemId 多次完成视为多次学习行为，M6 可自行聚合去重）

## M6 消费建议

- 聚合时按 `(userId, eventType, occurredAt)` 分组，不按 `eventId` 单条统计
- 对幂等事件（如 `assignment_submitted`）按 `submissionId` 去重
- 对状态翻转事件（如 `mistake_resolved`）按 `mistakeId` 关联时间序列
- 对 `reminder_triggered` 只计提醒生成次数，不重复计学生已读行为

**M6 的具体聚合算法不在本契约范围内**，由 M6 在 [packages/contracts/analytics/](../analytics/)
中定义（M6 自己的契约目录）。

## 错误处理

事件发布失败时，M5 service 层**回滚业务事务**（保证一致性）。
重试由客户端发起（如学生重新点提交）。服务端**不**异步重试事件发布——
因为业务已失败，不应留下「业务成功但事件丢失」的状态。

> 这条与 code-standards.md:63「外部请求设置超时，重试有上限且考虑幂等」一致。
> 事件表是本服务内写入，不算外部请求，失败回滚即可。
