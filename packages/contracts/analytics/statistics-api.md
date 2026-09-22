# 班级学习统计查询契约（M6 教师端 · S1）

本文定义教师端「班级概览」页读取的**统计展示接口**：数据形状与语义。
提供方与消费方均为 **M6**（班级概览页是 M6 的交付，见 `docs/tasks/m6.md:11`、`docs/team-plan.md:29`）；
数据来源于学习事件聚合（消费侧语义见 [event-consumption.md](event-consumption.md)，已随 PR #34 合并进 main）。

依据：`docs/code-standards.md:92` 要求 M6 → M2 明确「时长、掌握度和统计周期、样本数、未知状态」；
`docs/tasks/m6.md:29` 验收要求「无数据显示未知」；`docs/team-plan.md:29` 限定 M6 只做只读聚合。
字段口径按上述 M6 → M2 统计语义要求制定，**M2 预审本文**；M2 需评审的那条边是
S2 学生个人报告契约（另行出文件），届时须沿用本文的
`MetricNumber` / `unknown` / `insufficientSample` / `coverage` 语义，不另立一套。

状态：**草案**，未实现。M2/M1 评审确认前，教师端页面按本文的 Mock 开发（`docs/team-plan.md:70`）。

## 范围与边界

- 本文只覆盖 **S1 班级概览**一个端点。学生个人报告、知识点雷达图、周报属 S2 增量，
  另行出文件并请 M2 评审。
- **班级列表不在本文**：教师可见班级来自 M1 的身份/权限接口。本文的 `classId` 是入参。
- **权限不在聚合层**：教师仅见授权班级由 M1 鉴权层在 API 入口判定（`docs/tasks/m6.md:29`）；
  聚合层默认输入已按授权过滤，详见下方「权限与错误」。
- 本文只读，不产生副作用；不定义 M6 如何消费事件（那是 event-consumption.md 的范围）。

## 端点

### `GET /api/v1/analytics/classes/{classId}/overview`

查询参数：

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `period` | enum | 否 | `last7d` | 统计周期，取值 `last7d` / `last30d` / `custom` |
| `from` | string | 条件 | — | `period=custom` 时必填，UTC ISO 8601 |
| `to` | string | 条件 | — | `period=custom` 时必填，UTC ISO 8601 |
| `timezone` | string | 否 | `Asia/Shanghai` | IANA 时区名，决定「按日」聚合的日界 |

`last7d` / `last30d` 的定义：开区间端点 `to` 取生成时刻在 `timezone` 下所处**日**的**次日 00:00**，
向前取 7 / 30 个完整自然日（区间左闭右开）。例如生成于 2026-09-17（`Asia/Shanghai`）时，
`to = 2026-09-17T00:00+08:00`，`last7d` 覆盖 09-10 至 09-16。服务端**不得**依赖服务器本地时区
（`docs/code-standards.md:55`：API 用 UTC，UI 按用户时区显示）。

`days` 的语义是**区间覆盖的自然日数**（按 `timezone`）：由于 `to` 不含，
取区间内最后一个被包含的时刻定日。`last7d` 恰好是 7，`last30d` 恰好是 30；
`custom` 则按实际跨越的日数给出（如 `2026-09-15T00:00Z` 到 `2026-09-17T00:00Z`
在 `Asia/Shanghai` 下跨 3 个自然日）。

日界时区必须显式声明，因为「学生 × 日」是聚合维度（event-consumption.md 聚合边界）：
同一批事件在 `Asia/Shanghai` 与 `UTC` 下会落入不同的「日」。

响应恒为 200 + 结构化 JSON（无活动不是错误，见「权限与错误」）。

## `MetricNumber`：summary / student 级指标的统一形状

```json
{ "state": "known", "value": 1680, "algorithm": "session_inference_v1" }
{ "state": "unknown", "reason": "no_events_in_period" }
```

- **凡 summary / student 级可能出现 `unknown` 的指标（时长、提交数、活跃人数），一律用本形状，不允许裸数字。**
  这是 `docs/tasks/m6.md:29`「无数据显示未知」的落地点：周期内无事件的学生，
  其时长必须是 `unknown`，**不得返回 0**——0 是「学了但时长为零」的错误陈述。
- **薄弱点条目（`weakPoints`）不受本形状约束**：条目只在有样本时出现（无错题的章节不产生 0 行），
  其 `sampleSize` / `errorRate` / `mistakeCount` / `resolvedCount` 为裸数字。
- **「无活动」与「数据不可用」必须分开**：数据源查询成功且周期内确实无事件时，
  计数类指标（`activeStudentCount`、`submissionCount`）是**已知的 0**，不得写成 `unknown`；
  真正的数据源不可用由 503 表达（见「权限与错误」）。`unknown` 只表示缺乏判定依据
  （时长类指标）或数据源不可用。
- `reason` 枚举（S1，仅时长类指标）：
  - `no_events_in_period`：该对象在周期内没有任何事件，时长缺乏观测依据，无法判定；
  - `duration_source_unavailable`：时长来源不可用（预留，见「时长口径」）。
- `algorithm` 仅出现在时长类指标上，取值见「时长口径」；教师端页面需把它展示给教师，
  避免把所有时长当作同一种测量口径。

## 样例

| 样例 | 覆盖场景 |
| --- | --- |
| [samples/01-class-overview-ok.json](samples/01-class-overview-ok.json) | 正常返回：含已知学生、无事件学生（时长 `unknown`、提交数已知 0）、样本不足标记 |
| [samples/02-class-overview-no-data.json](samples/02-class-overview-no-data.json) | 全班无活动：`dataThrough` 为 null，计数类指标为已知 0，时长因缺乏观测为 `unknown` |
| [samples/03-error-class-not-found.json](samples/03-error-class-not-found.json) | 404：班级不存在或未授权 |
| [samples/04-error-validation-failed.json](samples/04-error-validation-failed.json) | 422：周期参数不合法 |
| [samples/05-error-source-unavailable.json](samples/05-error-source-unavailable.json) | 503：数据源不可用，不返回部分数字 |

样例 01 / 02 的数字可由固定合成事件集推导
（[docs/prototypes/samples/learning-events-synthetic.jsonl](../../../docs/prototypes/samples/learning-events-synthetic.jsonl)，
M6 教师端 S0 交付物，已随 PR #35 合并进 main）：
`user_mock_s01` 提交 2 次（同 `submissionId` 的重复事件不重复计）、
`user_mock_s02` 提交 1 次、`user_mock_s03` 无事件（时长 `unknown`、提交数已知 0）。
样例只用于契约评审与页面 Mock，**不是**已实现接口的响应证据。

## 响应结构

结构以样例为准，字段说明如下。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `classId` | string | 回显入参 |
| `courseId` | string \| null | `classId` 关联的课程 ID（映射见「班级与课程映射」），供页面经 M5 章节接口解析章节标题；映射缺失时为 null |
| `period` | object | `from` / `to`（UTC）/ `timezone` / `days`，服务端解析后的实际区间 |
| `dataThrough` | string \| null | 本响应纳入的**最新事件发生时间**（`occurredAt`，限定于本查询周期内）；null 表示本周期未纳入任何事件。**不是**可恢复的消费位点——同一时刻可能有多条事件，完整游标见 event-consumption.md 的 `(occurredAt, eventId)` |
| `consumption` | object | 消费完整度声明，见「消费完整度（`consumption`）」 |
| `generatedAt` | string | 响应生成时刻，UTC |
| `summary` | object | 班级汇总，见下 |
| `summary.totalDurationSeconds` | `MetricNumber` | 汇总时长，**只累加有数据的学生**，覆盖率由 `coverage` 交代 |
| `summary.activeStudentCount` | `MetricNumber` | 周期内有事件的去重学生数 |
| `summary.submissionCount` | `MetricNumber` | 去重后的提交数（去重键 `submissionId`，见「聚合口径」） |
| `summary.coverage` | object | `studentCount`（班级学生总数）/ `studentsWithData` / `studentsWithoutData` |
| `weakPoints.byQuestionType` | array | 题型薄弱点，见下 |
| `weakPoints.byChapter` | array | 章节薄弱点，见下 |
| `students` | object | 分页学生明细：`page` / `pageSize` / `items` / `total`，条目见下 |

`summary.totalDurationSeconds.value` 的语义是「**有数据的学生**的时长之和」，
不是全班总量。存在无数据学生时 `coverage.studentsWithoutData > 0`，
教师端页面必须把覆盖率显示出来，否则教师会把部分数据误读为全班数据。

### 消费完整度（`consumption`）

响应必须显式声明本次统计的消费完整度；页面不得把部分数据当作完整统计展示。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dataState` | enum | `complete` / `partial` / `unknown` |
| `upstreamWatermark` | string \| null | 响应生成时上游事件源已知的最新事件位置（按写入顺序）；null 表示上游尚无任何事件**或**本次未能取得水位 |

判定规则：

- `complete`：周期内全部可得事件已纳入本响应（上游尚无事件时视为已到尽头）；
- `partial`：消费滞后于 `min(period.to, upstreamWatermark)`，本响应只含部分数据；
- `unknown`：水位不可得，无法判断。

`dataState = partial` / `unknown` 时，页面须显示「数据仍在同步」的显式文案
（不能只用颜色或省略），且不得把该响应当作完整统计。

### 薄弱点条目

两个维度**分开返回**，不混在同一个排行里——`errorRate`（错误率）与 `mistakeCount`（错题数）
不是同一量纲，混排会误导教师。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | string | 题型枚举值（如 `single_choice`）或 `chapterId` |
| `label` | string \| null | 展示名，服务端有则给。`byQuestionType` 的 `key` 为题型枚举值，页面可本地映射；`byChapter` 的 `key` 是 `chapterId`，标题经响应中的 `courseId` 调 M5 章节接口（`GET /api/v1/courses/{courseId}/chapters`）解析，页面不得直接向教师展示 `chapterId` |
| `errorRate` | number | 仅 `byQuestionType`：错误题数 / 参与判分题数，取值 `[0,1]` |
| `mistakeCount` | number | 仅 `byChapter`：错题收录数 |
| `resolvedCount` | number | 仅 `byChapter`：其中已解决数 |
| `sampleSize` | number | 样本量（题型=参与判分的题数；章节=错题数） |
| `insufficientSample` | boolean | `sampleSize < 5`（`MIN_SAMPLE_SIZE`）时为 true |

排序规则（同一维度内，服务端保证确定性）：

1. `insufficientSample` 升序——**样本充足的条目排在样本不足的条目之前**；
2. `sampleSize` 降序；
3. 错误率（`byQuestionType`）/ 错题数（`byChapter`）降序；
4. `key` 字典序。

排序**不按错误率单独排序**：样本量 1、错误率 100% 的条目霸榜会误导教师（本文随附样例即为此场景）。
`sampleSize` 与 `insufficientSample` 必须展示，教师端页面对样本不足条目需给出显式提示
（不能只用颜色或省略）。

### 学生明细条目

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `userId` | string | 学生 ID（合成账号；真实学生资料不入公开仓库，`AGENTS.md:7`） |
| `displayName` | string \| null | 展示名，由 M1 身份接口提供；无则 null |
| `dataState` | enum | `known` / `unknown`，与 `durationSeconds.state` 一致（显式冗余，防止页面只读时长而忽略未知） |
| `durationSeconds` | `MetricNumber` | 周期内学习时长，口径见「时长口径」 |
| `submissionCount` | `MetricNumber` | 去重后的提交数 |
| `weakestChapter` | object \| null | 该生错题最多的章节，字段同 `byChapter` 条目；`null` 表示**本周期无错题记录**（已知事实，不是未知） |

`weakestChapter` 为 `null` 与 `dataState=unknown` 是两件事：前者是「没有错题」，
后者是「没有任何数据」。页面展示文案必须区分（如「本周期无错题」vs「暂无数据」）。

## 聚合口径（S1 最小集）

算法参数是实现中的命名常量，此处固化语义，实现须一致（`docs/tasks/m6.md:13`「注明样本/周期/算法」）。

### 时长口径（`algorithm`）

S1 没有上报时长的学习事件（M4 的专注计时事件尚未定义），时长由**会话推断**得出，
`algorithm` 标记为 `session_inference_v1`：

- 同一学生的事件按 `occurredAt` 升序，相邻事件间隔 ≤ `15 分钟` 视为同一会话；
- 单个会话时长 = 会话内首末事件间隔，最低 `60 秒`（单事件会话按最低计），
  上限 `3600 秒`（防止长间隔挂机虚增）；
- 学生周期时长 = 其各会话时长之和，按 `timezone` 日界切分为「学生 × 日」。

两个参数的关系需要留意：相邻间隔一旦超过 15 分钟就切成新会话，
因此 3600 秒上限只在「同一会话内高频事件跨 1 小时以上」时生效
（如每 10 分钟一条、连续 70 分钟 → 计 3600 秒）。

**这是过渡口径，不是测量值。** 待 M4 的专注计时事件就绪后，切换为累加上报时长，
`algorithm` 变为 `focus_timer_v1`，M2 可据此区分口径；切换只改聚合实现的一处，
响应结构不变。

### 薄弱点口径

- **题型**：每个 `submissionId` 取「`occurredAt` 最新且 `isCorrect` 非 null 的事件」判定对错。
  `assignment_submitted` 与 `assignment_graded` 都可用于判定（客观题提交即判分场景只发前者）；
  主观题未判分（`isCorrect` 为 null）**不计入分母**——未判分不是错误。
  题型本身取自**提交事件**：`assignment_graded` 的 payload 不含 `questionType`
  （M5 契约），故同一 `submissionId` 的判分沿用该提交已登记的题型，
  避免题型维度被丢成 `unknown`（后者只表示提交事件确实没给题型）。
- **章节**：来自 `mistake_recorded` 计数，`resolvedCount` 来自 `mistake_resolved`。
  本周期无错题的章节**不出现在结果里**，不返回 0 行。
- **提交数**：按 `submissionId` 去重。即使消费侧收到同一 `submissionId` 的重复事件
  （契约外情形，见 event-consumption.md），提交数也不得重复计数。

## 班级与课程映射

聚合按「班级 → 课程」过滤事件，避免同一学生跨班级/跨课程时数据串班
（PR #38 评审结论，requirements.md:31 的隔离要求）：

- `classId` ↔ `courseId` 映射来自 **M5 课程域**（`classes.course_id`），经 M5 公开 service 函数获取；
  M1 只在 API 入口做身份鉴权，不提供该映射。
- 聚合只纳入 `courseId` 与该班级映射一致的事件；`courseId = null` 的事件（如答疑产生的错题）
  S1 **不聚合进任何班级**，视为来源未知并在实现日志注明，待与 M5 确认后续归属口径。
- 映射关系同时通过响应中的 `courseId` 返回，供页面解析章节标题。

## 权限与错误

错误结构遵循 `docs/code-standards.md:73`：`{ code, message, requestId, details }`。

| 状态 | code | 场景 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 未认证 |
| 404 | `CLASS_NOT_FOUND` | 班级不存在，**或**不在教师授权范围内 |
| 422 | `VALIDATION_FAILED` | `period` 取值非法、`custom` 缺 `from`/`to`、`from >= to`、`timezone` 非法 |
| 503 | `ANALYTICS_SOURCE_UNAVAILABLE` | 聚合数据源不可用 |

- 「不存在」与「无权限」统一返回 404，避免通过状态码枚举他人班级
  （`docs/code-standards.md:82` 私有资源统一策略）。此约定需 M1 确认，因为判定发生在鉴权层。
- 503 时**不得**返回部分或伪造数字；`message` 不暴露堆栈（`docs/code-standards.md:63`）。
- **无活动不是错误**：周期内无事件仍返回 200——计数类指标为已知 0、时长类指标为 `unknown`，
  不能 404 或 5xx。

## 幂等、缓存与路由

- 本端点为只读 GET，天然幂等；重复请求不产生副作用。
- 响应头 `Cache-Control: no-store`（统计随事件消费持续变化，不能缓存给教师看旧数）。
- M6 提供 `APIRouter`；**挂载进 app factory 由 M1 协调**（`docs/team-plan.md:27`，`apps/api/app/main.py` 属 M1）。
  M6 不直接改公共入口文件。

## 实现进度（2026-09-22）

S1 聚合内核与本文端点已在分支 `feat/analytics-aggregation` 实现
（`apps/api/app/domains/analytics`）：事件模型、`(occurredAt, eventId)` 游标、
`eventId` 幂等去重、会话推断时长、题型/章节薄弱点、契约错误码与 `MetricNumber`。
本地跑通 `ruff format --check` / `ruff check` / `mypy` / `pytest`
（95 例，覆盖率 100%，CI 门槛 80%），并把接口响应与本文样例 01 逐字段比对一致。

该实现跑在**固定合成事件与内存状态**上，尚未接 M5 的真实 `learning_events` 表，
因此**不是**本契约已验收的证据，也不代表 S1 完成。

本文本轮评审修订（计数 known 0 口径、`MetricNumber` 规则收窄、`dataThrough` 语义、
`consumption` 三态、`students` 分页、`courseId` 返回与班级映射）由 PR #38 rebase 后同步实现。

与已合并的上游契约（`learning-events.md`）逐条核对过：`eventId` 校验用其冻结格式
（`event_` + 32 位小写 hex）；`isCorrect` / `score` 可空按「`null` 不等同 `false`」处理，
未判分不入错误率分母；题型从提交事件取值（判分事件不带 `questionType`）。

## 待确认事项

- [ ] M2 确认消费方归属修订（消费方为 M6 教师端；S2 学生报告契约沿用本文语义并请 M2 评审）
- [ ] M2 确认字段与未知/样本不足的展示约定（尤其是 `MetricNumber`、`coverage`、`weakestChapter` 的三态区分）
- [ ] M2 确认 `consumption` 三态与 `students` 分页结构（M2 在 PR #38 提出的问题，随本文一并收口）
- [ ] M1 确认：404 统一策略、`dataThrough` 口径、router 挂载方式
- [ ] M5 确认：`submissionId` 去重与主观题判分口径与 learning 契约一致
      （该契约已合并进 main，其「M6 消费建议」新增了「`null` 不等同 `false`」的要求，
      本文「未判分不入分母」与之对齐）
- [ ] M5 确认：`classId` ↔ `courseId` 映射（`classes.course_id`，经 M5 公开 service 函数）
      与 `courseId = null` 事件的归属口径
- [ ] 确认后本文转为冻结版；实现见 `apps/api/app/domains/analytics`

此清单未勾选即未确认，不以 AI 自评代替成员评审。

## 变更流程

本契约的消费方是 M6 教师端；S2 学生个人报告契约沿用本文语义，那条边由 M2 评审。
数据来源方是 M5/M1。修改字段、状态码或聚合口径前先通知 M2 与 M5，
变更同时更新样例与调用方。