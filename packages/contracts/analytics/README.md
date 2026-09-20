# Analytics 契约（M6 消费侧）

本目录是「学习数据与分析」领域的契约，由 M6 维护。M6 作为学习事件的**消费方**，
从 `learning_events` 聚合出班级统计与成长报告（`docs/team-plan.md:29`
「M6 从学习事件聚合统计，不改动其他领域数据」）。

状态：**草案**。消费侧语义（游标、去重）已经 M1 于 2026-09-15 在
[Issue #7 评论](https://github.com/StephenYI43/software-engineering-group-1/issues/7#issuecomment-5677225000) 中确认方向；
**仍待 M5 / M1 对本文按条评审确认**。确认前不编写生产代码。

## 文件

| 文件 | 内容 |
| --- | --- |
| [event-consumption.md](event-consumption.md) | 学习事件的消费方式、消费位点（游标）、幂等去重、聚合边界 |
| [samples/](samples/) | 游标状态等样例，供评审与实现对照 |

## 上下游

| 方向 | 对端 | 内容 | 依据 |
| --- | --- | --- | --- |
| 上游（M6 消费） | M2 / M4 / M5 | 学习事件，六公共字段 | `docs/code-standards.md:91`、M5 的 [learning-events.md](../learning/learning-events.md)（PR #26，未合并） |
| 下游（M2 消费） | M2 | 时长、掌握度、统计周期、样本数、未知状态 | `docs/code-standards.md:92` |

M6 → M2 的**统计展示契约**（掌握度雷达、周报等）不在本目录当前文件内，
将在 S2 之前另出文件并请 M2 评审；本目录现阶段只落 S1 的事件消费契约。

## 依赖现状（如实记录）

- 上游契约 `packages/contracts/learning/learning-events.md` 尚在 PR #26 评审中，
  未合并进 main。本草案基于其 2026-09-15 版本（M6 已在该 Issue 评审并获 M1 答复），
  其两处待修订（`payload.isCorrect` / `score` 标注可空、`eventId` 改为 `event_` + UUIDv4）
  落地后本契约才能冻结。
- `learning_events` 表由 M5 建表和写入，M6 只读。表结构与契约字段的具体映射
  待 PR #26 合并后核对。

## 待确认事项

- [ ] M5 确认轮询消费方式、`learning_events` 表的读取授权与列名映射
- [ ] M1 确认游标排序键（`occurredAt` 主序、`eventId` 同时间戳 tie-breaker）与 analytics 域建表迁移顺序
- [ ] M2 确认 `chapter_viewed` 事件由 M2 发布时的 schema（M5 契约中已列为待 M2 定义）
- [ ] learning-events.md 两处修订（payload 可空标注、eventId 格式）合并后，本契约转冻结

此清单未勾选即未确认，不以 AI 自评代替成员评审。

## 变更流程

本目录涉及跨领域读取（M5 的表）与跨模块消费（M2 的展示），修改前先通知 M5 与 M1；
涉及 M6 → M2 统计字段的变更还需 M2 评审。
