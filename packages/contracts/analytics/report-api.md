# 成长报告契约（M6 · v2 S1：数据结构与快照语义冻结稿）

本文冻结 M6「学习成长」报告线的**数据结构与快照语义**：周/月成长报告的创建与读取、
任务状态，以及毒事件隔离区（管理端）的数据形状。六个端点的路由与 HTTP 封套在
#84 鉴权底座接入后的下一批实现；届时端点行为以本文冻结的形状为准，
本文相应补充「实现进度」一节。

- **提供方 / owner**：M6（`apps/api/app/domains/analytics`）。
- **消费方**：M2（学生端成长报告页）、M6（教师端），与老师接口文档
  「M6 → M2/M6」一致（api.md §3.87–3.92，R02–R07）。
- **表结构**：`analytics_report_snapshots`（表 5-38）与 `report_jobs`（表 5-39），
  严格按 PR #79 DDL（`origin/codex/docs/69-complete-database-design` head 8061f4b）；
  本域 ORM 见 `apps/api/app/domains/analytics/pg_models.py`。
- **与 [statistics-api.md](statistics-api.md)（S1 班级统计）的关系**：
  个人报告沿用其 `MetricNumber` 未知语义（**未知不用 0 冒充**，确认无活动才 known+0）
  与 `session_inference_v1` 时长口径；班级报告的 `sample_count` 对应 S1 `coverage`
  的学生维度。本文不复述其细节，两文冲突时以 statistics-api.md 为准并在此登记。

依据：`docs/code-standards.md:92` M6 → M2 需明确「时长、掌握度和统计周期、样本数、
未知状态」；老师接口文档 R02–R07 与类型定义 `Job` / `ReportCreate` /
`KnowledgeMastery` / `LearningReport` / `QuarantinedEvent` / `ReplayCreate`。

状态：**数据结构与快照语义冻结，路由未实现**。M2/M1 评审确认前，消费方按本文形状开发 Mock。

## 范围与边界

- 本文只冻结**数据结构与快照语义**；六个端点（R02–R07）的路由接入、鉴权封套、
  `Idempotency-Key` / 分页参数的 HTTP 解析在下一批实现（依赖 #84 鉴权底座）。
- **授权原则（本批最小实现，如实记录）**：student 仅本人报告；teacher/admin
  本批在服务层全部放行。真实 ACL——教师仅当前有效授课班级、admin 显式管理范围、
  「管理员也不能默认读取学生对话」——依赖 M1 #84 鉴权底座，接入后收窄并补反例测试。
- **错误策略**：401 未认证；403 角色禁止；404 不存在与越权统一（防枚举，
  api.md §2.2.1）；422 字段/区间/跨字段校验；409 幂等键换参。
  业务码沿用老师文档 §2.1 整数编码（见下「错误映射」）。
- **知识点的受控词表未定义**：本批 `knowledge_points` 恒为 `[]`
  （契约允许 0—100 项的空数组），`suggestions` 同理恒为 `[]`；
  词表与生成逻辑属 S2 增量，届时另行评审。

## 数据结构（wire camelCase / DB snake_case）

> 命名说明：老师接口文档的示例字段名以 snake_case 记载（如 `student_user_id`），
> 组内冻结的 wire 命名为 camelCase（`docs/code-standards.md`「命名统一表」，
> 与 statistics-api.md 一致），本文按组内命名书写，两套名字一一对应。

### ReportCreate（R02 请求体）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `studentUserId` | string | 分支 | 个人报告目标；与 `classId` **恰好一个**（422） |
| `classId` | string | 分支 | 班级报告目标；与 `studentUserId` **恰好一个**（422） |
| `periodStart` | string | Y | UTC ISO 8601；半开区间 `[periodStart, periodEnd)` |
| `periodEnd` | string | Y | UTC ISO 8601；必须晚于 `periodStart` |
| `timezone` | string | Y | IANA 时区名；**本批仅接受 `Asia/Shanghai`**（其余 422） |

`timezone` 限制的原因（如实记录）：B 批日统计按 `Asia/Shanghai` 日界快照落库
（`analytics_daily_metrics.timezone` 列），其余时区的日界口径须随消费者版本扩展，
属 S2 增量。`timezone` 不入库（表 5-38/39 无对应列），本批又为常量，
故**不参与幂等换参比较**（见「幂等」）。

目标存在性由 FK（`users.id` / `classes.id`，RESTRICT）保证；路由批接入后把
FK 冲突统一映射为 404/422（防枚举），服务层不代查 M1/M5 身份表。

### Job（任务公开最小状态，沿用老师文档形状）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `jobId` | string | `job_` + 32 位小写 hex（组内冻结 ID 格式） |
| `status` | enum | `queued` / `running` / `succeeded` / `failed` / `cancelled` |
| `isMock` | boolean | 本服务为真实 PG 聚合，恒 `false` |
| `resultId` | string \| null | 成功时为报告 ID（`report_` 前缀）；否则 null |
| `errorCode` | string \| null | 失败码；本批同步生成不产生失败，恒 null |
| `createdAt` / `startedAt` / `finishedAt` | string \| null | UTC ISO 8601 |

任务状态约束由表 5-39 的 CHECK 强制：**终态（succeeded/failed/cancelled）必有
`finished_at`；succeeded 必有 `report_id`**。本批无 worker 队列，任务在创建事务内
同步生成快照：`queued → succeeded` 瞬时完成，`startedAt` **恒为 null**
（不伪造 running 阶段；表 5-39 亦无 started_at 列）。202 只表示受理，
不能当处理完成——本批同步完成后直接返回 succeeded 状态的 Job。

### LearningReport（R04 响应；快照的 wire 形状）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | `report_` + 32 位小写 hex |
| `studentUserId` / `classId` | string \| null | 报告目标，与 ReportCreate 对应，恰好一个非 null |
| `periodStart` / `periodEnd` | string | 快照周期，UTC |
| `dataThrough` | string \| null | 纳入数据的最新事件发生时间；无纳入数据为 null（语义同 statistics-api.md 的 `dataThrough`） |
| `durationSeconds` | MetricNumber | 见下 |
| `knowledgePoints` | KnowledgeMastery[] | 0—100 项；**本批恒 `[]`**（受控词表未定义，S2 增量） |
| `suggestions` | string[] | 0—10 项；**本批恒 `[]`**（建议生成属 S2 增量） |
| `generatedAt` | string | 快照生成时刻，UTC |

`sample_count` 不出现在 wire 形状（老师文档 LearningReport 无此字段），
仅落库于快照行，语义见「快照生成语义」。

### MetricNumber（沿用 statistics-api.md，不复述细节）

```json
{ "state": "known", "value": 1680, "algorithm": "session_inference_v1" }
{ "state": "unknown", "reason": "no_events_in_period" }
```

本报告线时长指标使用 `no_events_in_period`（窗口内无任何已知观测）；
`algorithm` 固定 `session_inference_v1`（口径见 statistics-api.md「时长口径」）。

### KnowledgeMastery（形状冻结，本批不出数据）

`{ key, mastery (0—1 或 null), sampleCount, dataState (known|unknown|partial) }`。
雷达维度必须带样本与未知状态；受控词表确定前恒不返回条目。

### QuarantinedEvent（R06 列表项）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | `quarantine_` + 32 hex |
| `eventId` / `consumerId` | string | 源事件与消费者引用（只返回引用，不返回事件正文——脱敏） |
| `errorCode` | string | 失败码（如 `schema_violation`） |
| `status` | enum | `open` / `retry_ready` / `resolved` |
| `attempts` | integer | 尝试数，≥1 |
| `firstFailedAt` / `lastFailedAt` | string | UTC |

### ReplayCreate（R07 请求体）

`{ reason: string }`，长度 1—300，审计理由、禁止敏感正文。
`reason` 本批**不落库**（见「隔离区重放」）；`Idempotency-Key` 头格式要求同 R02
（`^[A-Za-z0-9._:-]{1,128}$`），其登记与冲突检测随 #84 审计域落地，
本批仅做格式校验。

### 分页（R05 / R06）

统一分页结构 `items / total / page / pageSize`（老师文档 §2.2.3）：
`page` 1—1000、`pageSize` 1—100、`sort` 白名单 `created_at` / `-created_at`
（默认 `-created_at`），以 `id` 作稳定次序。白名单键的 ORM 映射：
报告列表 `created_at` → 快照 `generated_at`；隔离区列表 `created_at` →
`first_failed_at`。未知筛选参数 422。

## 快照生成语义

- **不可变**：快照生成后不更新（审计事实）。`(consumer_id, student_user_id,
  class_id, period_start, period_end)` 唯一（UNIQUE NULLS NOT DISTINCT，表 5-38）；
  重复请求同目标同周期**复用既有快照**（任务链接到它，不生成第二行）。
  需要新数据的刷新策略属 S2 增量。
- **数据源**：consumer `teacher-overview/v1` 的 `analytics_daily_metrics` known 行
  （日界 `Asia/Shanghai`）。周期覆盖的本地日 = `[periodStart, periodEnd)` 在
  `Asia/Shanghai` 日历下覆盖的自然日（半开区间：`periodEnd` 恰为某日零点时该日不计入）。
- **durationSeconds**：窗口内纳入行的 `study_seconds` 求和（known）；
  窗口内无任何已知观测 → `unknown(no_events_in_period)`，**不用 0 冒充**。
- **个人报告**：纳入该学生的全部 known 行（跨课程/班级求和，含课程级无班行）；
  `sample_count = 1`。
- **班级报告**：仅纳入 `class_id` 匹配的 known 行（课程级无班行不计入任何班级，
  与 statistics-api.md S1 班级口径一致）；`sample_count` = 窗口内有 known 行的
  **去重学生数**（无数据为 0）。无班级花名册依赖，无数据学生不虚计样本。
- **dataThrough**：纳入行的最新 `data_through`（= 最新事件发生时间）；
  无纳入行 → null。
- **metrics jsonb**：`{"schemaVersion":"1.0","durationSeconds":…,
  "knowledgePoints":[],"suggestions":[]}`；表 5-38 的 CHECK 强制
  `metrics->>'schemaVersion' = '1.0'`。

## 幂等（R02）

- `Idempotency-Key`：1—128 字符，`^[A-Za-z0-9._:-]{1,128}$`；
  按 **actor + 操作**隔离——`report_jobs` 唯一约束
  `(requested_by_user_id, idempotency_key)`。
- 同键同参：返回既有 Job（不重复写业务）。
- 同键换参：409（业务码 20002）。换参比较限于**持久化字段**
  （目标 student/class + 周期起止）；`timeZone` 本批为常量不参与比较（见上）。
- 幂等检查、任务创建、快照生成在同一事务内完成（repository 不自行 commit，
  失败整批回滚）。

## 隔离区管理（R06 / R07，admin）

- R06 列表：`status` 白名单筛选（`open` / `retry_ready` / `resolved`）；
  只返回引用与脱敏原因，不返回事件正文。
- R07 重放：不改源事件；把隔离行置 `retry_ready`（`open`/`retry_ready`/`resolved`
  均可置位，语义等价 `AnalyticsPgWorker.retry_quarantined`），由 worker 下一轮
  轮询重放——重放成功时 ledger + 聚合 + resolved 同事务（B 批已实现）。
- **审计边界（如实记录）**：`reason` 与操作者审计的持久化在 M1 #84 审计域接入；
  本批不造新表。B 批 worker 的 `resolved_by_user_id` 为 worker 实例内存
  （`_last_resolver`），跨实例「重放成功」路径依赖 #84 落地持久审计后修复。

## 端点（路由在后续批次接入）

| 编号 | 路由 | 方法 | 角色 | 语义 |
| --- | --- | --- | --- | --- |
| R02 | `/api/v2/report-jobs` | POST | student/teacher/admin | 创建本人或本班报告任务，202 + Job；同键换参 409 |
| R03 | `/api/v2/report-jobs/{job_id}` | GET | student/teacher/admin | 查询授权报告任务 |
| R04 | `/api/v2/learning-reports/{report_id}` | GET | student/teacher/admin | 读取本人或授权班级报告 |
| R05 | `/api/v2/learning-reports` | GET | student/teacher/admin | 授权成长报告列表（分页 + sort 白名单） |
| R06 | `/api/v2/admin/analytics/quarantined-events` | GET | admin | 查询脱敏隔离事件（status 筛选） |
| R07 | `/api/v2/admin/analytics/quarantined-events/{quarantine_id}/replays` | POST | admin | 授权重放隔离事件，202 + Job |

路由接入时遵循：私有资源越权统一 404 防枚举；私有数据
`Cache-Control: no-store`；响应封套 `{code, message, data, trace_id}`
（§2.1 整数业务码）。

## 错误映射（服务层异常 → HTTP / 业务码）

| 服务层错误 | HTTP | 业务码 | 场景 |
| --- | --- | --- | --- |
| `InvalidQueryError` | 422 | 10001 | 目标恰好一个、周期、时区、幂等键格式、分页/sort/status 白名单 |
| `ReportIdempotencyConflictError` | 409 | 20002 | 同 actor 幂等键换参 |
| `ReportForbiddenError` | 403 | 20011 | student 请求他人/班级报告；非 admin 访问隔离区 |
| `ReportNotFoundError` | 404 | 20001 | 报告不存在或越权（统一 404） |
| `ReportJobNotFoundError` | 404 | 20001 | 任务不存在或越权（统一 404） |
| `QuarantinedEventNotFoundError` | 404 | 20001 | 隔离行不存在或范围外 |

## 实现进度（2026-11-10，C 批第一批）

已交付（分支 `feat/65-analytics-report-snapshots`）：

- ORM 两表 `AnalyticsReportSnapshot` / `ReportJob`（严格按 #79 DDL，
  含 CHECK、UNIQUE NULLS NOT DISTINCT、FK；`apps/api/app/domains/analytics/pg_models.py`）。
- 服务层 `ReportPgService`（`apps/api/app/domains/analytics/report_service.py`）：
  幂等建任务 + 同事务快照生成、报告/任务查询、报告列表、隔离区列表与重放；
  事务边界由服务层 `session.begin()` 控制，repository 不自行 commit。
- PG 集成测试 `apps/api/tests/analytics/test_pg_reports.py`（复用
  `pg_test_support` 夹具，TEST_DATABASE_URL 门控）。

**路由未接入**（下一批接 #84 鉴权底座后实现 R02–R07 的 HTTP 层）；
本文「端点」表中的行为届时以集成测试核对。

## 待确认事项

- [ ] M2 确认消费方字段需求（个人报告页对 `MetricNumber` / `knowledgePoints=[]` /
      `sampleCount` 不外显的处理）
- [ ] M1 确认 #84 审计域接入点：`ReplayCreate.reason` 与重放操作者的持久化，
      以及 R07 的 202 Job 形状（隔离重放任务是否复用 `report_jobs`）
- [ ] M1 确认教师「当前有效授课班级」ACL 收窄时机（服务层已预留按角色过滤）
- [ ] S2 增量：知识点受控词表、建议生成、其余 IANA 时区支持、快照刷新策略
- [ ] 确认后本文端点行为随路由实现转为冻结版

此清单未勾选即未确认，不以 AI 自评代替成员评审。

## 变更流程

本文消费方是 M2/M6，owner M6，数据来源依赖 M5 事件与 M1 身份底座。
修改字段、错误码或快照语义前先通知 M2 与 M1，变更同时更新实现与测试。
