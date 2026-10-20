"""M6 学习数据与分析域（analytics）。

S1 提供两件事：消费学习事件的聚合内核（本包 service/state/aggregation），
以及交付给 M2 的班级统计查询接口（本包 router/schemas）。
消费侧语义见 `packages/contracts/analytics/event-consumption.md`，
统计查询契约见 `packages/contracts/analytics/statistics-api.md`。

边界：只读学习事件，聚合结果留在本域；不改动其他领域的数据
（`docs/team-plan.md:29`）。
"""
