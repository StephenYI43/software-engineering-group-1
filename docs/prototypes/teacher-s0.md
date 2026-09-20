# 教师端原型设计（M6 / S0）

状态：**草案**。本文是 `docs/tasks/m6.md:19`「S0 教师原型、事件样例」的交付物，
为 S1 页面实现做设计准备。实现前置条件尚不具备（`apps/web` 工程壳未建，
见 ADR-0003「后续工作」#23），本文**不是**页面已实现的证据。

提出人：M6 / @xk1024。评审请求：M1（固定交叉评审）、M2（页面将挂载进 M2 维护的 `apps/web`，且 M2 负责根路由组合）。

## 范围与边界

- 本文只覆盖**教师端 S1 四个页面**的原型设计；S2 增量（雷达图、周报、月报、批阅辅助、风格设置）只列出占位，不展开。
- 本文不写代码。M6 依据 ADR-0003：**不初始化** `package.json` / lockfile，
  将来在 `apps/web/src/features/teacher/` 内实现页面并声明自己的路由配置，由 M2 维护的根 router 组合。
- 权限边界（`docs/tasks/m6.md:29` 验收）：**教师仅见授权班级**。授权判定由 M1 的鉴权层提供，
  页面不自行过滤权限，也不依赖客户端菜单隐藏来表达权限（`docs/code-standards.md:104`）。

## 页面清单（S1）

| 页面 | 路径（features/teacher/ 内部） | 目的 | 上游数据 | 状态 |
| --- | --- | --- | --- | --- |
| 班级概览 | `dashboard` | 查看授权班级的学习时长与答题薄弱点 | analytics 聚合接口（M6 自有，未设计） | S1 |
| 课程管理 | `courses` | 上传课件 PDF、查看解析进度、进入知识库管理入口 | M3 解析 API（异步 202 + jobId，`docs/code-standards.md:81`） | S1 |
| 作业发布 | `assignments` | 发布作业、查看提交与批阅状态 | M5 课程/作业契约（PR #26，未合并） | S1 |
| 学生报告 | `reports` | 单个学生的成长报告 | analytics 聚合接口 | **S2 占位**，S1 不实现 |

页面在 S1 的验收底线（`docs/team-plan.md:59` 集成链路）：教师上传 PDF → 查看解析状态 →
…… → 教师看到授权班级统计。四个页面中**课程管理与班级概览**是链路上的必需节点，
作业发布允许以最小可用（列表 + 发布表单）先行。

## 各页面区块与数据需求

### 班级概览（dashboard）

区块：

1. **班级选择器**：仅列出当前教师被授权的班级。班级列表来自 M1 身份/权限接口（未实现，先 Mock）。
2. **学习时长卡**：近 7 天班级总时长、活跃人数。数据来自 M6 聚合表。
3. **薄弱点排行**：按章节/题型聚合的错误率 Top N。
4. **学生明细表**：每生时长 / 提交数 / 薄弱章节，点击进入学生报告（S2 前为占位）。

数据语义约束（与 [analytics 消费契约](../contracts/analytics/event-consumption.md)一致，PR #34）：

- 统计周期、样本数、未知状态必须展示（`docs/code-standards.md:92` 对 M6 → M2 的要求反过来约束本页）；
- **无事件的学生显示「未知」，不显示 0**（`docs/tasks/m6.md:29`）；
- 薄弱点排行必须注明样本量（如「12 次提交」），避免 2 条错误率 100% 的章节置顶误导教师。

### 课程管理（courses）

区块：

1. **课程列表**：教师授课的课程（M5 `courses.md`，未合并，字段待冻结）。
2. **上传区**：选择 PDF → 上传。S1 只支持单门课 PDF（`docs/team-plan.md:53`）。
   上传成功返回 202 + jobId（`docs/code-standards.md:81`），页面进入「解析中」态。
3. **解析进度列表**：每份文档 queued / running / succeeded / failed 状态轮询。
   failed 时展示服务端返回的错误 `message`，不展示堆栈。
4. **入口按钮**：知识库管理（M3 域，S1 仅跳转占位）。

Mock 约定：解析进度在 Mock 下固定走「running → succeeded」剧本，
不模拟随机失败；失败场景由专门 Mock 场景键触发（对齐 ADR-0002 的 Mock 场景思路）。

### 作业发布（assignments）

区块：

1. **作业列表**：按课程分组，含提交数 / 已批阅数。
2. **发布表单**：标题、截止时间、题目列表（S1 支持客观题；主观题批阅是 S2 增量）。
3. **提交明细**：学生提交状态。字段以 M5 契约冻结版为准（PR #26 未合并，
   `payload.isCorrect` / `score` 的可空口径已由 M1 在 Issue #7 裁定，此处按其实现）。

## Mock 数据策略

- 所有 Mock 数据为**合成学生账号**（如 `user_mock_s01`），不使用真实学生资料（`AGENTS.md:7`）；
- 页面数据源统一走接口层，Mock 与真实接口可切换，切换开关不得进入生产构建；
- 每个 Mock 响应带 `isMock: true` 标记或等价机制，演示时能如实区分（`AGENTS.md:4`、`docs/tasks/m6.md:32`）；
- Mock 样例与 [合成事件样例](samples/learning-events-synthetic.jsonl) 同源，
  保证「概览页看到的数字」可由样例事件推导（走查见下）。

## 合成事件样例与页面走查

[samples/learning-events-synthetic.jsonl](samples/learning-events-synthetic.jsonl)
是供 S1 聚合算法与页面开发使用的**固定合成事件集**：

- 字段结构与 M5 `learning-events.md`（PR #26，未合并）一致，六公共字段 +
  `payload`；`eventId` 使用 M1 冻结的 `event_` + UUIDv4 32 位小写十六进制格式；
- 覆盖 `assignment_submitted`（含客观题带分、主观题 null 分两种）、
  `assignment_graded`、`mistake_recorded`、`mistake_resolved`、
  `study_plan_saved`、`plan_item_completed` 各至少一条；
- **含一条防御性去重用例**：与样例 1 的 `submissionId` 相同但 `eventId` 不同的事件。
  按 M5 契约该事件**不应发生**（幂等命中不重发）；若消费侧收到（契约外情形），
  聚合必须按业务键 `submissionId` 去重（learning-events.md「M6 消费建议」），
  提交数不得变为 2。`eventId` 级去重（游标重放）另由消费契约的走查表覆盖（PR #34）。

**页面走查**（证明样例 → 页面数字可推导）：

| 样例事件 | 概览页呈现 |
| --- | --- |
| `user_mock_s01` / `user_mock_s02` 各 1 条 `assignment_submitted` | 学生明细表提交数各 +1 |
| `user_mock_s03` 全程无事件 | 该生时长显示「未知」而非 0 |
| 防御用例（同 `submissionId` 的新事件） | 提交数仍为 1，不重复计数 |

## 依赖与阻塞

| 依赖 | 状态 | 影响 |
| --- | --- | --- |
| `apps/web` 工程壳（ADR-0003 后续 #23，M2） | 未开始 | 页面代码无法落地，本文先行 |
| M5 学习契约（PR #26） | 评审中 | 页面字段待冻结，先按草案 + Mock 开发 |
| M1 班级授权接口 | 未实现 | 班级选择器先 Mock |
| M3 解析 API | 未实现 | 解析进度先 Mock |
| analytics 消费契约（PR #34） | 评审中 | 概览页数据语义依据，冻结前数字仅用于原型演示 |

## 验收自查（S0 阶段）

- [x] 页面清单与 S1 链路对齐，S2 增量明确占位
- [x] 权限边界写明：教师仅见授权班级，页面不做权限判定
- [x] Mock 策略含合成账号与 isMock 标记，不冒充真实实现
- [x] 合成事件样例可推导页面数字，含幂等去重用例
- [ ] M1 / M2 评审通过后，本文转为「已确认」并作为 S1 实现依据
