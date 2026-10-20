# M6 学习数据与分析域（analytics）

本目录属于 M6 模块，负责 "教师后台 / 学习统计与成长报告"。

## 当前阶段

S1 事件消费与统计聚合**内核已实现**，但**尚未接 M5 的真实 `learning_events` 表**：
上游表与 M1 的鉴权/花名册接口都未落地，因此当前提供内存实现与合成事件，
可独立运行与验证（`docs/team-plan.md:70` 允许 M6 基于明确标记的 Mock 并行开发）。

本轮不包含：数据库表与迁移（等 M5 建表并协调迁移顺序）、
真实鉴权过滤、定时轮询的调度接入（M1 的 app factory 负责挂载）。

## 隔离限制（如实记录）

学习事件只携带 `courseId`，**不携带 `classId`**。因此当**同一学生同时处于同一课程的
两个班级**时，聚合无法区分，该生数据会同时计入这两个班级（按 `classId→courseId` 过滤
只能挡住跨课程串数据）。真实接表前必须由后续 Issue 决定补 `classId`，或冻结
「同一学生同一课程只属一个班级」这一业务不变量；在此之前**不得宣称已完成完整跨班隔离**。
（M1 复审 2026-10-01 要求，详见 `packages/contracts/analytics/statistics-api.md`
「班级与课程映射」。）

## 模块结构

| 文件 | 职责 |
| --- | --- |
| `events.py` | 学习事件输入模型与 payload 校验（六公共字段 + `payload`） |
| `cursor.py` | 消费位点 `(occurredAt, eventId)` |
| `state.py` | 聚合状态：提交去重、判分取最新、错题与活跃度 |
| `aggregation.py` | 读侧指标：会话推断时长、题型/章节薄弱点、样本量 |
| `period.py` | 统计周期与日界时区解析（`last7d` / `last30d` / `custom`） |
| `schemas.py` | 契约响应模型；`MetricNumber` 区分已知与未知 |
| `service.py` | `AnalyticsConsumer`（轮询消费）与 `AnalyticsService`（读侧组装） |
| `ports.py` | `EventSource` / `AnalyticsStore` / `ClassRoster` 端口 |
| `memory.py` | 端口的内存实现，测试与本地演示用 |
| `router.py` | `GET /api/v1/analytics/classes/{classId}/overview` 与错误处理器 |
| `errors.py` | 可映射为契约错误响应的异常 |

契约：消费侧 `packages/contracts/analytics/event-consumption.md`（PR #34）、
统计查询 `packages/contracts/analytics/statistics-api.md`。

## 运行与验证

```bash
cd apps/api
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

`tzdata` 是依赖项：Windows 与精简镜像里 `zoneinfo` 没有系统时区库，
缺少它会导致按日聚合的时区解析直接失败。

## Mock 与真实实现的区别（如实记录）

| 方面 | 当前（本轮） | 接入上游后 |
| --- | --- | --- |
| 事件来源 | `InMemoryEventSource`，读固定的 11 条合成事件 | 读 M5 的 `learning_events` 表（M6 只读） |
| 状态持久化 | `InMemoryAnalyticsStore`，进程重启即归零 | analytics 域自己的表 + 迁移（顺序由 M5 协调） |
| 班级与权限 | `StaticRoster` 固定花名册 | M1 的身份/权限接口；未授权与不存在统一 404 |
| 时长口径 | 会话推断 `session_inference_v1`（过渡） | M4 专注计时事件就绪后切 `focus_timer_v1` |
| 调度 | 手动调用 `poll_once()` | 由部署侧定时触发 |

聚合逻辑不受上述替换影响：替换的是 `ports.py` 的实现类。

## 迭代计划（对齐 docs/team-plan.md）

- S0：学习事件模型与教师端原型接口设计（已完成）
- S1：课件上传入口与基础统计（聚合内核已实现，页面待 `apps/web` 工程壳）
- S2：雷达图 / 周报展示