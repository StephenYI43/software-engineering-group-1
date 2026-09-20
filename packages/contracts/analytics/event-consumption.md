# 学习事件消费契约（M6 消费侧，S1）

本文定义 M6 如何从 `learning_events` 表消费事件并聚合统计。
发布侧 schema 由 M5 的 [learning-events.md](../learning/learning-events.md)（PR #26，未合并）定义，
本文不重复定义事件字段，只定义**消费侧语义**。

引用约定：`learning-events.md` 指 PR #26 分支上的
`packages/contracts/learning/learning-events.md`（M6 已于 2026-09-15 在 Issue #7 评审），
其行号以合并时的版本为准，故本文不引用其行号；
带 `docs/` 前缀的为仓库根相对路径。

## 目标与边界

- M6 **只读** `learning_events`；聚合结果写入 analytics 域自己的表
  （`docs/team-plan.md:25` 把 `apps/api/app/domains/analytics` 划给 M6）。
- M6 不改动其他领域的数据；修正统计不通过删改事件，而是重放聚合
  （上游表本身 append-only，见 learning-events.md 不变量第 1 条）。
- 权限不在本契约内：教师仅见授权班级由 M1 鉴权层与 API 层保证
  （`packages/contracts/platform/README.md:38`「鉴权必须先于检索」），
  聚合层默认输入已按授权过滤。

## 消费方式（S1）

- **轮询**：M6 定时读取游标之后的批次，处理完再读下一批。
  依据 learning-events.md「传输方式」：S1 为表追加 + 轮询/触发器视图，不引入 MQ。
- 轮询间隔与批大小是实现参数，不属于本契约；但**一批内必须按
  `(occurredAt, eventId)` 升序处理**，游标语义依赖该顺序（见下节）。
- S2 若事件量超出轮询承载，升级方案（MQ 或触发器）另开 ADR，游标语义不变。

## 消费位点（游标）

M6 维护**单一全局游标**（M6 是 `learning_events` 的唯一消费方），
持久化在 analytics 域自己的表中，形状见 [samples/cursor-state.json](samples/cursor-state.json)。

### 排序键

以 **`(occurredAt, eventId)`** 为排序键：

- `occurredAt` 是主排序键，UTC ISO 8601；
- `eventId` 只在同一时间戳下做**稳定的确定性 tie-breaker**（字典序）。
  M1 已确认（Issue #7，2026-09-15）：eventId 是不透明字符串，
  **不能从其内容推断发生顺序**，因此不能单独用 eventId 排序。

### 读取条件

```text
occurredAt >  lastOccurredAt
OR (occurredAt = lastOccurredAt AND eventId > lastEventId)
```

按 `(occurredAt, eventId)` 升序读取。等值事件不会因 tie-breaker 漏读：
字典序保证同时间戳内 eventId 大于游标值的事件全部被读到。

### 推进规则

- 一批事件**全部聚合落库成功后**才推进游标到本批最大 `(occurredAt, eventId)`；
- 处理失败不推进、不跳过，下一轮从头重读本批——安全性由下节去重保证；
- **游标只前进**（S1）。发生漏消费（如修数后需回填）时，做法是**显式重置游标到更早位置
  并重放**，重放的安全性同样由去重保证，而不是在正常路径引入回看窗口。

## 幂等与去重

验收要求（`docs/tasks/m6.md:29`）：**重复事件不重复计时**。
本契约用双保险满足：

1. **正常路径**：游标单调前进，每条事件恰好被读取一次；
2. **防御路径**：聚合写入时以源事件 `eventId` 作为幂等键（聚合表唯一约束）。
   游标回拨、重放、并发轮询等异常情况下，同一 `eventId` 的事件仍只计一次。

**「重复」的定义：`eventId` 相同才是重复。** 以下情形是多次合法事件，分别计数：

- `plan_item_completed` 同一 `itemId` 多次完成（learning-events.md 已声明重新发布，
  M6 可自行聚合去重——那是展示层选择，不是消费层丢弃）；
- `study_plan_saved` 计划每次修改重新发布（`payload` 不同）。

上游已保证「幂等命中已有记录不重发事件」（learning-events.md 幂等节），
但 M6 消费侧**不依赖该保证**：即使 M5 未来重发，去重规则也保证统计正确。

业务级去重（如按 `submissionId` 对提交事件去重）属于**聚合算法层**的选择，
在实现聚合时注明（`docs/tasks/m6.md:13`「注明样本/周期/算法」），不写死在本契约。

## 聚合与展示边界（S1 最小集）

- 聚合维度：学习时长按「学生 × 日」聚合；答题薄弱点按「学生 × 章节/题型」聚合；
  具体算法在实现时注明样本来源、周期与算法（`docs/tasks/m6.md:13`）。
- **无数据显示「未知」，不用 0 冒充**（`docs/tasks/m6.md:29` 验收）：
  某学生在统计周期内无事件时，其时长/薄弱点展示为未知状态，而不是 0。
- analytics 域聚合表的迁移由 M6 编写，顺序由 M5 协调、M1 检查可部署性
  （`docs/team-plan.md:27`）。

## 走查：一轮消费如何推进

以下示例展示游标与去重在正常与异常路径下的行为。
`eventId` 采用 M1 冻结的 `event_` + UUIDv4 格式
（learning-events.md 样例中的 6 位短串是待修订的文档占位，实现不得照抄）。

| 步骤 | 读取到 | 游标（处理前 → 处理后） | 说明 |
| --- | --- | --- | --- |
| 1 | `event_a…@10:00`、`event_b…@10:00` | `(null, null)` → `(@10:00, event_b…)` | 同时间戳按 eventId 字典序，全部落库后推进 |
| 2 | `event_c…@10:05` | → `(@10:05, event_c…)` | 正常前进 |
| 3 | 第 2 步聚合写入失败 | 不推进，仍 `(@10:00, event_b…)` | 下一轮重读 `event_c…` |
| 4 | 重读 `event_c…` | 唯一约束命中，跳过写入；游标 → `(@10:05, event_c…)` | 防御路径：同 eventId 只计一次，统计不变 |
