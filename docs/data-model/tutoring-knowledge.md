# 答疑与知识库数据字典（M3）

关联 [#71](https://github.com/StephenYI43/software-engineering-group-1/issues/71)、[#69](https://github.com/StephenYI43/software-engineering-group-1/issues/69)。
基线日期：2026-10-20。状态：**七列设计草案；未建表、未落迁移、未进行真实 PostgreSQL 验证。**

owner：M3 [@ljt2293977194-dotcom](https://github.com/ljt2293977194-dotcom)。
评审：M1（身份、授权与迁移可部署性）、M5（课程/班级与授权归一化、固定交叉评审）、M2/M6（答疑流与上传解析状态的消费者）。

本文只描述目标结构，不代表数据库已经存在。**不修改 JWT、API 或角色授权行为。**
九张表的业务覆盖与管理覆盖见 [#69 的模块清单](https://github.com/StephenYI43/software-engineering-group-1/issues/69)：
`tutoring_sessions`、`tutoring_turns`、`turn_citations`、`documents`、`document_chunks` 为业务表；
`document_grants`、`document_import_jobs`、`prompt_versions`、`model_config_versions` 为管理表。

`docs/data-model/` 的全域说明由 #73（PR）引入；在 #73 合并前，本文提到的
`docs/data-model/README.md`、`erd.md`、`platform.md` 可能还不在 main 上。

## 实际起点

S1 的答疑代码在 **PR #62（分支 `feat/59-tutoring-sse-api`，尚未合并）** 上已实现，
但 **main 上目前只有 `adapters/`（ADR-0002 第 1 块）**，没有答疑路由、服务与仓库。
PR #62 的状态保存在**进程内仓库** `repository.py` 的 `InMemoryTutoringRepository`，
重启即丢；`apps/api/migrations/` 不存在，`#48` 的 PostgreSQL 底座尚未落地。
因此本文的字段是从**已合并的契约**与 **PR #62 分支上（未合并）的实现**反推出来的目标结构，
而不是对现有表的描述，也不能把 PR #62 的代码当作已在 main 上存在。

事实来源（按优先级；标注「未合并」的只存在于 PR #62 分支）：

| 来源 | 决定了什么 |
| --- | --- |
| `packages/contracts/tutoring/tutoring-response.md` | `turnId`/`sessionId`/`stage`/`content`/`citations`/`hasEvidence`/`followUps`/`emotion`/`action`/`isMock`/`promptVersion` |
| `packages/contracts/tutoring/sse-events.md` | 终止事件、`stopped`/`error` 语义、断连只记内部状态、停止幂等 |
| `apps/api/app/domains/tutoring/repository.py`（未合并） | `active`/`completed`/`stopped`/`errored`/`disconnected` 五个轮次状态与「同会话至多一个进行中轮次」 |
| `apps/api/app/domains/tutoring/service.py`（未合并） | 错误码、停止优先级、token 用量与耗时日志、引用白名单 |
| `apps/api/app/domains/tutoring/retrieval.py`（未合并）、`adapters/base.py`（已合并） | `RetrievedChunk` 四字段（文档、标题、页码、正文） |
| `docs/adr/0004-rag-retrieval-boundary.md` | 授权先于检索、切片不跨页、无文字页显式报告、S1 不持久化 |
| `ai/prompts/README.md` | 提示词文件名即 `promptVersion`，已发布版本不得就地改 |

**本 PR 的验证仅限文档**：七列结构、字段与契约的映射、链接与差异检查。
没有建表、没有迁移、没有任何真实数据库测试结果；也不能把现有内存测试当成本文已实现的证据。

## 通用规则

1. **主键**统一 `varchar(64)`，新生成 ID 为 `前缀_` + 32 位小写十六进制（#69 基线）。
   已有样例里的短后缀（`doc_9a2f4c`、`sess_4b8d1e02`、`turn_7f3a9c21`）是示意数据，
   保持豁免，**不在本 PR 批量改写，也不据此提前收紧输入校验**。
2. **时间**统一 `timestamptz(6)`、UTC；API 输出 ISO 8601。`updated_at` 由服务端显式维护，
   `ON UPDATE` 不自动刷新。`ON UPDATE NO ACTION` 表示主键不可修改。
3. **外键**默认 `ON DELETE RESTRICT`；只有「派生数据」和「随父记录明确清除」的关系才用 `CASCADE`。
   跨域外键（`users`、`courses`）由 M1/M5 先建表，M3 只引用，**不直接写其他领域的表**。
4. **业务写入必须在事务内**，仓储层不自行 `commit`；状态终态只允许一次迁移
   （`active → completed | stopped | errored | disconnected`），之后不可回退。
5. **授权不是外键**。物理 FK 只能保证「引用的行存在」，不能证明「调用者有权访问」；
   资源归属与课程/班级访问由服务端鉴权与 M5 花名册判定（`packages/contracts/platform/README.md`）。
6. **模型输出与上传文档都是数据，不是指令**。`documents.title`、`assistant_content`、
   `document_chunks.text`、`turn_citations.snippet` 一律按不可信文本处理：展示前净化，
   不执行其中命令，`title` 不拼进提示词（`AGENTS.md`「提示词版本化。上传文档和检索片段视为数据」
   与「Mock 必须明确标记」两条；`docs/requirements.md` 注入要求）。
7. **Mock 必须如实标记**：`tutoring_turns.is_mock` 与 `model_config_versions.is_mock`
   必须与实际来源一致；Mock 结果不能当生产完成证据。
8. **JSONB 内部属性**也要给出类型、必填、范围、默认与 `schemaVersion`（见「JSONB 内部字典」）。
9. **实现状态**只有四级：设计草案 → 评审确认 → 迁移已实现 → 真实 PostgreSQL 测试通过。
   前端 Mock 或内存测试不能提升状态。本文全部停留在第一级。

### ID 前缀提案

| 实体 | 前缀 | 状态 |
| --- | --- | --- |
| 答疑会话 | `sess_` | 平台契约已提议（M3） |
| 答疑轮次 | `turn_` | 平台契约已提议（M3） |
| 文档（版本） | `doc_` | 平台契约已提议（M3） |
| 文档片段 | `chunk_` | **本文新增，待 M1 在平台契约登记** |
| 文档授权 | `grant_` | **本文新增，待 M1 登记** |
| 文档导入任务 | `job_` | **本文新增，待 M1 登记** |
| 提示词版本 | `promptver_` | **本文新增，待 M1 登记** |
| 模型配置版本 | `modelcfg_` | **本文新增，待 M1 登记** |
| 请求追踪 | `req_` | 平台已实现（M1） |

`citationId`（`c1`、`c2`…）**不是实体 ID**，只是轮内引用标签，不作为跨表主键使用；
`turn_citations` 的主键是 `(turn_id, citation_id)`。

### 两个 `seq` 必须区分

| 名称 | 含义 | 是否持久化 |
| --- | --- | --- |
| SSE 事件 `seq` | 单条流内第几个事件（`started`=1，终止事件为最大值） | **否**。它由流写出器推导，重启或重试都重新计数 |
| `tutoring_turns.seq` | 同一会话内第几轮提问（从 1 开始） | **是**。用于会话内排序，不保证与 `id` 字典序一致 |

两者同名不同义；实现和评审时不要互相替代。

## 关系与一致性

全域草图见 #73 的 `erd.md`。本文确认的跨表关系与删除规则：

| 关系 | 基数 | 删除/更新规则 |
| --- | --- | --- |
| `users` → `tutoring_sessions.student_user_id` | 1:N | `RESTRICT`：有会话的用户不物理删除，停用即可 |
| `courses` → `tutoring_sessions.course_id` | 1:N（可空） | `RESTRICT` |
| `tutoring_sessions` → `tutoring_turns` | 1:N | 仅显式清除会话时 `CASCADE`；常规不物理删除 |
| `tutoring_turns` → `turn_citations` | 1:N | `CASCADE`（引用快照随轮次） |
| `courses` → `documents.course_id` | 1:N | `RESTRICT` |
| `users` → `documents.uploader_user_id` | 1:N | `RESTRICT` |
| `documents` → `documents.previous_document_id` | 版本链 | `RESTRICT`；每个版本至多一个后继 |
| `documents` → `document_chunks` | 1:N | `CASCADE`（派生数据）；但被引用时受 `turn_citations` 的 `RESTRICT` 拦住 |
| `documents` → `document_grants` | 1:N | `CASCADE`（授权行不是审计记录，审计在 M1） |
| `documents` → `document_import_jobs` | 1:N | `CASCADE` |
| `documents` → `turn_citations.document_id` | 1:N | `RESTRICT`：**有引用就不允许硬删** |
| `document_chunks` → `turn_citations.chunk_id` | 1:N | `RESTRICT` |
| `prompt_versions` → `tutoring_turns` | 1:N | `RESTRICT`：用过就不删除，只退役 |
| `model_config_versions` → `tutoring_turns` | 1:N | `RESTRICT` |

关键一致性约束：

- 同一会话**至多一个进行中轮次**：`tutoring_turns` 上的
  `UNIQUE(session_id) WHERE status = 'active'`。这是 PR #62 内存实现里
  `active_turn_id`（未合并）的数据库兜底，409 的最终依据。
- `hasEvidence = false` ⟺ 该轮没有 `turn_citations`。跨表条件，由服务层保证并在测试中断言。
- 每条 citation 的 `document_id` 必须属于**本轮授权检索结果**；模型声称的标签在服务端白名单步骤后丢弃，
  见 `apps/api/app/domains/tutoring/service.py` 的 `_allowed_citations`（PR #62，未合并）。
- `turn_citations.document_version` 是引用时的版本快照；文档重新解析产生新 `documents` 行与新 chunks，
  **旧引用继续指向旧版本**，不得被新版本覆盖。

## 业务表

### tutoring_sessions

- 用途：一次多轮答疑会话，保存教学阶段与学生归属；业务类。
- owner：M3。评审：M1（归属与鉴权）、M5（`course_id` 引用）。
- 候选键：`id`；索引：主键；`(student_user_id, updated_at)`（学生会话列表）；`course_id`。
- 数据来源：答疑服务在首个轮次创建（PR #62 的实现首次访问即创建）；合成 seed 仅用于测试。
- 读写权限：仅会话所属学生本人与授权管理员可读；默认不向教师开放学生完整对话，
  教师只能按授权花名册读取必要摘要（具体边界待 M1/M5 确认）。
  会话归属取自服务端已验证凭证，**不信任请求体或路径里的自报身份**。
- 保留/删除：不随课程归档自动删除；学生申请删除时按学校/项目确认的保留期处理（见「待确认」）。
  默认软删或匿名化，不物理删除仍被其他域引用的记录。
- 状态：设计草案；PR #62 只有内存实现（未合并），未建表、未迁移。

| 物理字段名      | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值                                   | 取值范围/枚举/唯一/CHECK                                     | PK/FK/关联与删除/更新规则                                      |
| --------------- | --------------------------------- | -------------------------- | ---- | ---------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| id              | 会话标识；API `sessionId`         | varchar(64)                | 否   | 无；服务端新生成时发号                    | 新生成 `sess_`+32 位小写 hex；对调用方不透明，不据此判权；旧样例短 ID 兼容见下 | PK                                                             |
| student_user_id | 会话所属学生；API 身份映射 `sub`  | varchar(64)                | 否   | 无                                       | 必须存在且为 student；来自已验证凭证，不信客户端自报          | FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION           |
| course_id       | 本次会话限定的课程；可空          | varchar(64)                | 是   | NULL                                     | 非空时必须存在；请求里的 `courseId` 只能收窄已授权范围        | FK→courses.id；ON DELETE RESTRICT；ON UPDATE NO ACTION         |
| current_stage   | 会话当前教学阶段                  | varchar(16)                | 否   | `'thought'`                              | CHECK IN(`thought`,`hint`,`step`,`summary`)；只有 completed 轮推进 | 无（非键）                                                     |
| created_at      | 创建时刻                          | timestamptz(6)             | 否   | CURRENT_TIMESTAMP                        | UTC                                                          | 无（非键）                                                     |
| updated_at      | 最后活动时刻（轮次开始/结束）     | timestamptz(6)             | 否   | CURRENT_TIMESTAMP；由服务端显式更新      | UTC 且不早于 `created_at`                                    | 无（非键）                                                     |

**不冗余 `active_turn_id`**：PR #62 的内存仓库用它表示「会话忙」（未合并），持久化后该事实由
`tutoring_turns` 的部分唯一索引派生，避免出现两个真相来源。
**不设会话状态列**：S1 没有显式关闭接口，`updated_at` 足够表达空闲；若将来要分
`active/closed`，必须新增列并评审，不能靠布尔值暗示。

**一个必须先解决的语义缺口**：现在的契约由客户端在路径里提供 `sessionId`，服务端首次见到即创建
（PR #62 的 `repository.py` 中 `session()`，未合并）。持久化后，如果继续允许客户端自造 ID，就会产生
「谁能创建任意主键」和「旧样例短 ID（如 `sess_4b8d1e02`）是否可写库」两个问题。
`packages/contracts/platform/README.md` 明确要求「在 M3/M5 确认格式之前不能批量替换或收紧其输入验证」，
因此本文**不预设**
`sessionId` 一定符合 `sess_`+32hex。迁移前必须由 M1/M2 确认：新增「创建会话」端点并由服务端发号，
还是继续把路径 ID 当不透明查询键、仅在服务端创建时发号。在该问题确认前不写死输入校验。

### tutoring_turns

- 用途：一次提问—回答回合，保存阶段、状态、问答正文、错误元数据与用量；业务类。
- owner：M3。
- 候选键：`id`；`UNIQUE(session_id, seq)`；部分 `UNIQUE(session_id) WHERE status='active'`。
- 索引：`(session_id, seq)`；`prompt_version_id`；`model_config_version_id`；`(status, created_at)`（清理/排障）。
- 数据来源：答疑服务每个 `POST .../messages` 创建一个轮次；停止接口只改状态，不建新轮。
- 读写权限：答疑服务写；本人与授权管理员读；其他域只通过公开服务取标识，不直接写本表。
- 保留/删除：追加式记录，正文与学生问题**不得就地改写**；只允许一次终态迁移。
  常规不删除，随会话显式清除；跨域的播报记录（M4）引用 `turn_id` 时应使用 `RESTRICT`，
  本域不会在没有通知的情况下硬删历史。
- 状态：设计草案；PR #62 的内存实现已有同等状态机（未合并），未建表、未迁移。

| 物理字段名              | 中文名称/业务含义（需要时补别名）                | PostgreSQL 类型与长度/精度 | 可空 | 默认值                                             | 取值范围/枚举/唯一/CHECK                                                                 | PK/FK/关联与删除/更新规则                                          |
| ----------------------- | ------------------------------------------------ | -------------------------- | ---- | -------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| id                      | 轮次标识；API `turnId`                           | varchar(64)                | 否   | 无；服务端生成                                     | `turn_`+32 位小写 hex                                                                    | PK                                                                 |
| session_id              | 所属会话                                         | varchar(64)                | 否   | 无                                                 | 必须存在；同会话 `seq` 唯一                                                              | FK→tutoring_sessions.id；ON DELETE CASCADE（仅显式清除会话）；ON UPDATE NO ACTION |
| seq                     | 会话内第几轮提问（**不是** SSE 事件序号）        | integer                    | 否   | 无；服务端在会话行锁/事务内分配                    | `>0`；`UNIQUE(session_id, seq)` 兜底并发；不保证与 `id` 顺序一致                         | `UNIQUE(session_id, seq)` 之一                                     |
| request_id              | 创建本轮的请求追踪号                             | varchar(36)                | 否   | 无；服务端生成                                     | `req_`+32 位小写 hex；不采用外部自报的 `X-Request-ID`                                    | 无（非键）；日志追踪用                                             |
| student_content         | 学生本轮提问                                     | text                       | 否   | 无                                                 | 长度 1..2000 字符（契约请求上限）；敏感数据，不写日志、不进他人响应                      | 无（非键）                                                         |
| assistant_content       | 本轮已生成正文；未完成时可为部分文本             | text                       | 是   | NULL                                               | completed 时必须非空；必须与全部 `delta.textDelta` 拼接逐字节相等；可尾随 `\n`           | 无（非键）                                                         |
| stage                   | 本轮**冻结**的教学阶段                           | varchar(16)                | 否   | 无                                                 | CHECK IN(`thought`,`hint`,`step`,`summary`)；由服务端状态机在 claim 时确定，非模型输出   | 无（非键）                                                         |
| status                  | 轮次状态                                         | varchar(16)                | 否   | `'active'`                                         | CHECK IN(`active`,`completed`,`stopped`,`errored`,`disconnected`)；终态不可回退          | 无（非键）；见下方部分唯一索引                                     |
| is_complete             | 是否构成完整回答                                 | boolean                    | 否   | false                                              | 必须与 `status = 'completed'` 严格一致                                                   | 无（非键）                                                         |
| is_mock                 | 是否由离线假模型生成                             | boolean                    | 否   | 无                                                 | 如实反映来源；须与所用 `model_config_versions.is_mock` 一致                              | 无（非键）                                                         |
| has_evidence            | 本轮是否检索到依据                               | boolean                    | 否   | false                                              | false ⟺ 该轮 `turn_citations` 为空（跨表，服务层保证）                                   | 无（非键）                                                         |
| emotion                 | 数字人情绪快照；供 M4 播报                       | varchar(16)                | 是   | NULL                                               | completed 时必须非空；取值集合待 M4 冻结后加 CHECK，当前只校验长度                       | 无（非键）                                                         |
| action                  | 数字人动作快照；供 M4 播报                       | varchar(16)                | 是   | NULL                                               | 同上                                                                                     | 无（非键）                                                         |
| follow_ups              | 建议追问列表                                     | jsonb                      | 否   | `'{"schemaVersion":"1.0","items":[]}'`             | 必须是对象；内部字典见「JSONB 内部字典」；`items` 至多 3 条、每条 1..200 字符            | 无（非键）                                                         |
| prompt_version_id       | 产生本轮的提示词版本                             | varchar(64)                | 否   | 无                                                 | 必须是已登记版本；不得由客户端指定；API 的 `promptVersion` 由联表得到                    | FK→prompt_versions.id；ON DELETE RESTRICT；ON UPDATE NO ACTION     |
| model_config_version_id | 本轮使用的模型配置版本                           | varchar(64)                | 否   | 无                                                 | 必须是已登记版本                                                                         | FK→model_config_versions.id；ON DELETE RESTRICT；ON UPDATE NO ACTION |
| input_tokens            | 上游报告的输入 token 数                          | integer                    | 是   | NULL                                               | `>=0`；上游未报告时为 NULL，**不能填 0 冒充已知**                                        | 无（非键）                                                         |
| output_tokens           | 上游报告的输出 token 数                          | integer                    | 是   | NULL                                               | `>=0`；同上                                                                              | 无（非键）                                                         |
| duration_ms             | 本轮服务端耗时                                   | integer                    | 是   | NULL                                               | `>=0`；仅用于评测与排障，不作为计费依据                                                  | 无（非键）                                                         |
| error_code              | 流内错误码                                       | varchar(32)                | 是   | NULL                                               | CHECK IN(`MODEL_OUTPUT_INVALID`,`MODEL_REFUSED`,`MODEL_TIMEOUT`,`RETRIEVAL_UNAVAILABLE`,`TURN_ABORTED`)；非空 ⟺ `status='errored'` | 无（非键）                                                         |
| error_reason            | 错误内部原因码（如 `response_envelope_parse_failed`） | varchar(64)                | 是   | NULL                                               | 只允许登记的原因码；不得写入模型输出正文、堆栈或密钥                                     | 无（非键）                                                         |
| created_at              | 轮次创建（claim）时刻                            | timestamptz(6)             | 否   | CURRENT_TIMESTAMP                                  | UTC                                                                                      | 无（非键）                                                         |
| settled_at              | 进入终态的时刻                                   | timestamptz(6)             | 是   | NULL                                               | `active` 时必须为 NULL；终态时必须非空且 `>= created_at`                                 | 无（非键）                                                         |

**表级约束（目标，迁移时落地）**：

- `UNIQUE(session_id) WHERE status = 'active'`：同一会话至多一个进行中轮次。
- `CHECK ((status = 'completed') = is_complete)`。
- `CHECK ((status = 'active') = (settled_at IS NULL))`。
- `CHECK ((status = 'errored') = (error_code IS NOT NULL))`。
- `CHECK (status = 'errored' OR error_reason IS NULL)`。
- `CHECK (status <> 'completed' OR (assistant_content IS NOT NULL AND emotion IS NOT NULL AND action IS NOT NULL))`。
- `CHECK (input_tokens IS NULL OR input_tokens >= 0)`，`output_tokens`、`duration_ms` 同理。

**不设 `stop_reason` 列**：PR #62 的实现里能下发的原因只有 `client_stop`；
`client_disconnect` 是连接断开，直接体现为 `status='disconnected'`，不产生事件。
一个不可能取第二个值的列只会诱使调用方信任它，因此用 `status` 表达。

### turn_citations

- 用途：一轮回答引用的课件片段**快照**，支持「翻到该页能找到支持结论的原文」；业务类。
- owner：M3。消费者：M2 展示、M6 审核、评测与回溯。
- 候选键：`(turn_id, citation_id)`；`UNIQUE(turn_id, chunk_id)`（同一片段每轮至多一条）。
- 索引：`document_id`；`chunk_id`。
- 数据来源：服务端白名单步骤。模型只返回标签集合，服务端按本轮检索结果的顺序与范围组装，
  见 `service.py` 的 `_allowed_citations`（PR #62，未合并）。
- 读写权限：服务写；本人与授权教师读；模型与客户端都不能写。
- 保留/删除：随轮次保留。**课件下架不删除既有引用快照**（否则历史回答失去可追溯性）；
  下架后新轮次不得再引用该文档。只有会话/轮次的显式清除会级联删除引用。
- 状态：设计草案；未建表、未迁移。

| 物理字段名              | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值                      | 取值范围/枚举/唯一/CHECK                                                       | PK/FK/关联与删除/更新规则                                     |
| ----------------------- | --------------------------------- | -------------------------- | ---- | --------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| turn_id                 | 所属轮次                          | varchar(64)                | 否   | 无                          | 必须存在                                                                       | PK 之一+FK→tutoring_turns.id；ON DELETE CASCADE；ON UPDATE NO ACTION |
| citation_id             | 轮内引用标签；API `citationId`    | varchar(8)                 | 否   | 无；服务端按白名单分配      | `^c[1-9][0-9]?$`；每轮从 `c1` 起；每轮数量上限由服务端 `DEFAULT_LIMIT` 控制     | PK 之一；不是全局实体 ID                                      |
| document_id             | 被引用的文档版本                  | varchar(64)                | 否   | 无                          | 必须属于本轮授权检索结果；服务层校验，不能只靠 FK                             | FK→documents.id；ON DELETE RESTRICT；ON UPDATE NO ACTION      |
| chunk_id                | 被引用的片段                      | varchar(64)                | 否   | 无                          | 必须属于 `document_id` 对应的版本；每轮同片段至多一条                          | FK→document_chunks.id；ON DELETE RESTRICT；ON UPDATE NO ACTION |
| document_version        | 引用时的文档版本快照              | integer                    | 否   | 无；取自 `documents.version` | `>=1`；与 `document_id` 对应版本一致（服务层/测试断言）                        | 无（非键）                                                    |
| document_title_snapshot | 引用时的展示文件名快照            | varchar(255)               | 否   | 无                          | 不可信输入；展示前净化；**不得拼进提示词**                                     | 无（非键）                                                    |
| page_number             | 页码                              | integer                    | 否   | 无                          | `>=1`，1 基；切片不得跨页（ADR-0004）                                          | 无（非键）                                                    |
| snippet                 | 支持结论的原文片段快照            | text                       | 否   | 无                          | 非空；视为数据，不执行其中命令；与 `document_chunks.text` 对应片段一致         | 无（非键）                                                    |

**为什么快照而不是只存外键**：`document_chunks.text` 可能因重解析或版本升级而变化；
引用必须能证明「当时模型看到的原文是什么」，所以 `snippet`、`page_number`、`document_version`
都在引用时落盘。外键只负责指向可追溯的实体，不替代快照。

### documents

- 用途：授权课件的一个**不可变版本**：元数据、存储位置、内容哈希与解析结果计数；业务类。
- owner：M3（表与解析语义）；上传入口由 M6 的教师端调用公开服务；访问规则由 M1/M5 判定。
- 候选键：`id`；`UNIQUE(previous_document_id)`（版本链中每个版本至多一个后继；首版为 NULL 可多条）；
  `UNIQUE(storage_key)`。
- 索引：`(course_id, status)`；`uploader_user_id`；`file_sha256`；`previous_document_id`。
- 数据来源：教师上传（S1 只收 PDF）→ 创建 `documents` 行与 `document_import_jobs` 行；
  解析成功后回填 `page_count` 并把状态置 `available`。
- 读写权限：教师只能看自己课程/自己上传的文档；学生不能列文档元数据，只能从检索结果中见到引用；
  管理员按权限审计。**文档可见性不等于文件可下载权**，后者由 M1 文件访问控制决定。
- 保留/删除：下架用 `status='withdrawn'` 软删，可单独删除对象存储里的二进制；
  元数据、chunks 与既有引用**保留**。**被 `turn_citations` 引用时禁止硬删**；
  确需法律/版权清除时走独立清除流程并通知 M1/M5/M6，不能靠级联静默抹掉历史。
- 状态：设计草案；未建表、未迁移。

| 物理字段名           | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值                    | 取值范围/枚举/唯一/CHECK                                                              | PK/FK/关联与删除/更新规则                                      |
| -------------------- | --------------------------------- | -------------------------- | ---- | ------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| id                   | 文档版本标识；API `documentId`    | varchar(64)                | 否   | 无；服务端生成            | `doc_`+32 位小写 hex；一个版本一行，不就地覆盖                                        | PK                                                             |
| course_id            | 所属课程                          | varchar(64)                | 否   | 无                        | 必须存在；跨课程检索由授权集合限制，不靠本列判权                                      | FK→courses.id；ON DELETE RESTRICT；ON UPDATE NO ACTION         |
| uploader_user_id     | 上传者；上传者自动可访问          | varchar(64)                | 否   | 无                        | 必须存在且为 teacher/admin（按上传入口规则）                                          | FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION           |
| title                | 展示文件名；API `documentTitle`   | varchar(255)               | 否   | 无                        | 1..255 字符；不可信输入；展示前净化；**不得拼进提示词**                               | 无（非键）                                                     |
| version              | 同一文档的版本号                  | integer                    | 否   | 无；服务端在同一版本链内递增 | `>=1`；链内单调递增（服务层/测试保证）；`UNIQUE(previous_document_id)` 只保证每版至多一个后继 | 无（非键）                                                     |
| previous_document_id | 上一版本；首版为空                | varchar(64)                | 是   | NULL                      | 非空时必须同属一个课程且版本号更小；不得自引用                                        | FK→documents.id；ON DELETE RESTRICT；`UNIQUE(previous_document_id)` |
| file_sha256          | 原始文件内容哈希                  | char(64)                   | 否   | 无；服务端计算            | `^[0-9a-f]{64}$`；用于去重提示与完整性校验，不替代授权                                | 无（非键）；索引 `file_sha256`                                  |
| storage_key          | 对象存储键（不是 URL）            | varchar(255)               | 否   | 无；服务端生成            | 非空；不包含密钥、签名参数或可长期访问的 URL；`UNIQUE(storage_key)`                   | 无（非键）；`UNIQUE(storage_key)`                              |
| mime_type            | 文件 MIME 类型                    | varchar(100)               | 否   | `'application/pdf'`       | S1 CHECK `= 'application/pdf'`；PPTX 属 S2，放宽需新迁移并评审                         | 无（非键）                                                     |
| size_bytes           | 文件字节数                        | bigint                     | 否   | 无                        | `>0`；上传上限由 M1 的 `upload_limits` 在服务层校验，数据库不复制该配置               | 无（非键）                                                     |
| page_count           | 解析出的页数                      | integer                    | 是   | NULL                      | 非空时 `>=1`；成功解析后回填；无文字页不因此为 0                                      | 无（非键）                                                     |
| status               | 文档生命周期状态                  | varchar(16)                | 否   | `'uploaded'`              | CHECK IN(`uploaded`,`available`,`withdrawn`)；解析任务状态另见 `document_import_jobs` | 无（非键）；索引 `(course_id, status)`                         |
| created_at           | 上传记录创建时刻                  | timestamptz(6)             | 否   | CURRENT_TIMESTAMP         | UTC                                                                                   | 无（非键）                                                     |
| updated_at           | 最后修改时刻                      | timestamptz(6)             | 否   | CURRENT_TIMESTAMP；显式更新 | UTC 且不早于 `created_at`                                                             | 无（非键）                                                     |
| withdrawn_at         | 下架时刻                          | timestamptz(6)             | 是   | NULL                      | `status='withdrawn'` 时必须非空，否则必须为 NULL                                      | 无（非键）                                                     |

**版本链而不是覆盖**：重新解析或上传新版本时新建一行 `documents` 并指向上一版；
旧版本与其 chunks、引用全部保留。这样「文档版本 + 页码 + 原文定位」在引用侧才成立。

### document_chunks

- 用途：文档版本切分后的可检索片段；业务类，检索层与评测消费。
- owner：M3。消费者：`knowledge` 检索实现（#53）与答疑服务。
- 候选键：`id`；`UNIQUE(document_id, chunk_index)`。
- 索引：`(document_id, page_number)`；关键词检索的倒排/`GIN`/`pg_trgm` 方案在 #53 实测后决定，
  **本文不预建**，避免把未验证的方案写进迁移。
- 数据来源：解析任务成功时由 `knowledge` 写入；写入后只读。
- 读写权限：检索服务只读；学生/教师不直接查询片段表，只通过授权检索结果看到引用。
- 保留/删除：随文档版本保留；**被引用时 `RESTRICT`**。不就地修改，重解析产生新版本。
- 状态：设计草案；`knowledge/` 目录尚不存在，未建表、未迁移。

| 物理字段名   | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值             | 取值范围/枚举/唯一/CHECK                                                                 | PK/FK/关联与删除/更新规则                                         |
| ------------ | --------------------------------- | -------------------------- | ---- | ------------------ | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| id           | 片段标识                          | varchar(64)                | 否   | 无；服务端生成     | `chunk_`+32 位小写 hex                                                                   | PK                                                                |
| document_id  | 所属文档版本                      | varchar(64)                | 否   | 无                 | 必须存在；同文档内 `chunk_index` 唯一                                                    | FK→documents.id；ON DELETE CASCADE（派生数据）；ON UPDATE NO ACTION |
| chunk_index  | 文档内片段序号                    | integer                    | 否   | 无；服务端按解析顺序分配 | `>=0`；`UNIQUE(document_id, chunk_index)`                                                | `UNIQUE(document_id, chunk_index)` 之一                           |
| page_number  | 片段所在页码                      | integer                    | 否   | 无                 | `>=1`，1 基；一个片段必须完整落在一页内（ADR-0004）                                       | 无（非键）                                                        |
| char_start   | 页内起始字符偏移                  | integer                    | 否   | 无                 | `>=0`；按该页提取文本的 Unicode 字符计，0 基、包含                                    | 无（非键）                                                        |
| char_end     | 页内结束字符偏移                  | integer                    | 否   | 无                 | `> char_start`；按 Unicode 字符计、不包含；用于原文定位                                  | `CHECK (char_end > char_start)`                                   |
| text         | 片段正文                          | text                       | 否   | 无                 | 非空；不可信数据，不执行其中命令；渲染进提示词时使用数据槽分隔符                         | 无（非键）                                                        |
| created_at   | 片段写库时刻                      | timestamptz(6)             | 否   | CURRENT_TIMESTAMP  | UTC                                                                                     | 无（非键）                                                        |

**无文字页**：扫描件提取不到文字时**不生成 chunk，也不静默丢弃**；页号进入
`document_import_jobs.pages_without_text`，由 M6 的解析状态页如实展示（ADR-0004 第 6 节）。

## 管理表

### document_grants

- 用途：文档级**显式用户授权**（额外或例外授权），不承载班级、角色或课程范围的授权语义；管理类。
- owner：M3（表与读写接口）；授权规则由 M1 的鉴权与 M5 的课程/花名册共同确认。
- 候选键：`id`；部分 `UNIQUE(document_id, grantee_user_id) WHERE revoked_at IS NULL`。
- 索引：`(grantee_user_id, document_id) WHERE revoked_at IS NULL`；`document_id`。
- 数据来源：管理员/教师的授权流程（S1 可用合成 seed）；上传者自动访问由
  `documents.uploader_user_id` 派生，**不再写一条授权行**。
- 读写权限：鉴权服务读；授权写必须经过授权接口并进入 M1 的审计；学生不能自授权，
  模型与检索层都不能写授权。
- 保留/删除：撤销置 `revoked_at`，不物理删除历史授权；文档硬删时随文档 `CASCADE`
  （授权行不是审计记录，审计在 `admin_audit_logs`）。
- 状态：设计草案；未建表、未迁移。

| 物理字段名         | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK                                          | PK/FK/关联与删除/更新规则                                     |
| ------------------ | --------------------------------- | -------------------------- | ---- | ----------------- | ----------------------------------------------------------------- | ------------------------------------------------------------- |
| id                 | 授权记录标识                      | varchar(64)                | 否   | 无；服务端生成    | `grant_`+32 位小写 hex                                            | PK                                                            |
| document_id        | 被授权的文档版本                  | varchar(64)                | 否   | 无                | 必须存在                                                          | FK→documents.id；ON DELETE CASCADE；ON UPDATE NO ACTION       |
| grantee_user_id    | 被授权用户                        | varchar(64)                | 否   | 无                | 必须存在；不得等于上传者（服务层拒绝；上传者已自动可访问，重复行无意义） | FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION          |
| granted_by_user_id | 授予人；系统 seed 时为空          | varchar(64)                | 是   | NULL              | 非空时必须为有权限的管理员/教师；自授予按服务端规则拒绝           | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION          |
| granted_at         | 授予时刻                          | timestamptz(6)             | 否   | CURRENT_TIMESTAMP | UTC                                                               | 无（非键）                                                    |
| revoked_at         | 撤销时刻；非空即失效              | timestamptz(6)             | 是   | NULL              | 非空时必须 `>= granted_at`；撤销与重新授权在同一事务处理          | 无（非键）；部分唯一索引见上                                  |

**必须由 M1/M5 确认的边界**：

- 本表**先只表示用户级授权**。班级/课程范围的可见性由 M5 的选课与授课关系派生，
  由 M1 的鉴权服务合成「已授权文档集合」后交给检索层（ADR-0004 的
  `authorized_document_ids` 是唯一范围边界）。**M3 的检索层永不自算授权。**
- **不设 `target_type`/`target_id` 这类无约束多态列**。将来若确实需要班级级授权，
  必须等 M5 定义清楚班级/课程归一化，再新增受 FK 约束的 `grantee_class_id` 或独立表，
  并重新评审；不能用一个字符串列隐式装多种实体。
- 不允许用 `grantee_user_id = 0`、空串或通配值表示「所有人」。公开或课程级可见性必须走
  M5 的花名册，不在本表造特例。

### document_import_jobs

- 用途：PDF 解析、切分、索引的异步任务状态与失败原因；管理类。
- owner：M3（解析流水线）；调用方 M6（上传后查状态）、M3 检索层依赖 `succeeded`。
- 候选键：`id`；`UNIQUE(document_id, idempotency_key)`。
- 索引：`(status, created_at)`；`document_id`。
- 数据来源：上传成功后创建；重试沿用调用方幂等键，重复提交返回同一任务。
- 读写权限：M6 只能查自己课程/自己上传文档的任务；M3 worker 更新；
  学生不可见；失败原因不得包含文件正文、堆栈或密钥。
- 保留/删除：随文档清除；成功/失败记录保留用于审计与重试；不保存上传文件内容。
- 状态：设计草案；`knowledge/` 尚未实现，未建表、未迁移。

| 物理字段名         | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值                            | 取值范围/枚举/唯一/CHECK                                                                 | PK/FK/关联与删除/更新规则                                     |
| ------------------ | --------------------------------- | -------------------------- | ---- | --------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| id                 | 任务标识；API `jobId`             | varchar(64)                | 否   | 无；服务端生成                    | `job_`+32 位小写 hex                                                                      | PK                                                            |
| document_id        | 被解析的文档版本                  | varchar(64)                | 否   | 无                                | 必须存在                                                                                  | FK→documents.id；ON DELETE CASCADE；ON UPDATE NO ACTION       |
| requested_by_user_id | 发起人                          | varchar(64)                | 否   | 无                                | 必须存在；M6 只能查自己发起或自己课程的任务                                                | FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION          |
| status             | 任务状态                          | varchar(16)                | 否   | `'queued'`                        | CHECK IN(`queued`,`running`,`succeeded`,`failed`)；状态只前进不回退                        | 无（非键）；索引 `(status, created_at)`                       |
| idempotency_key    | 幂等键                            | varchar(64)                | 否   | 无；调用方提交，重复提交必须相同  | 非空；`UNIQUE(document_id, idempotency_key)`                                              | `UNIQUE(document_id, idempotency_key)` 之一                   |
| attempt_count      | 已尝试次数                        | integer                    | 否   | 0                                 | `>=0`；超过上限后保持 `failed`，不无限重试                                                | 无（非键）                                                    |
| failure_code       | 失败原因码                        | varchar(64)                | 是   | NULL                              | `status='failed'` 时必须非空，其余必须为 NULL；登记的原因码                                | 无（非键）                                                    |
| failure_message    | 脱敏失败说明                      | varchar(500)               | 是   | NULL                              | 最长 500；不含文件正文、堆栈、路径中的用户名或密钥                                        | 无（非键）                                                    |
| pages_without_text | 无可提取文字的页码列表            | jsonb                      | 否   | `'{"schemaVersion":"1.0","pages":[]}'` | 对象；内部字典见「JSONB 内部字典」；成功前为空数组，成功后如实列出 1 基页号              | 无（非键）                                                    |
| created_at         | 任务入队时刻                      | timestamptz(6)             | 否   | CURRENT_TIMESTAMP                 | UTC                                                                                       | 无（非键）                                                    |
| started_at         | 开始执行时刻                      | timestamptz(6)             | 是   | NULL                              | `running`/`succeeded`/`failed` 时必须非空且 `>= created_at`                               | 无（非键）                                                    |
| finished_at        | 结束时刻                          | timestamptz(6)             | 是   | NULL                              | `succeeded`/`failed` 时必须非空且 `>= started_at`；`queued`/`running` 时必须为 NULL       | 无（非键）                                                    |

**任务状态与文档状态不是同一件事**：`documents.status` 回答「这份文档能不能被检索」，
`document_import_jobs.status` 回答「这一次解析跑得怎么样」。一份文档可以有多次重试任务，
最后一次成功即可把文档置 `available`；失败任务保留供 M6 展示与重试。

### prompt_versions

- 用途：提示词版本的登记与可追溯；正文的唯一来源是 Git 中的 `ai/prompts/*.md` 文件；管理类。
- owner：M3。评审：M1、M5（提示词版本影响评测可比性，属公共接口变更）。
- 候选键：`id`；`UNIQUE(series, version_label)`；部分 `UNIQUE(series) WHERE status='active'`。
- 索引：`(series, status)`。
- 数据来源：发布流程从 `ai/prompts/` 登记；真实运行时**从版本号推导文件**，不硬编码字面量
  （`ai/prompts/README.md`）。
- 读写权限：M3 发布，服务只读；客户端不可改；已发布版本不得就地修改。
- 保留/删除：**永不物理删除**。退役置 `status='retired'`，历史轮次继续通过 FK 对得上版本。
- 状态：设计草案；PR #62 的 `prompt_renderer.py`（未合并）已从文件名推导版本，未建表、未迁移。

| 物理字段名         | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK                                            | PK/FK/关联与删除/更新规则                                     |
| ------------------ | --------------------------------- | -------------------------- | ---- | ----------------- | ------------------------------------------------------------------- | ------------------------------------------------------------- |
| id                 | 版本记录标识                      | varchar(64)                | 否   | 无；服务端生成    | `promptver_`+32 位小写 hex                                           | PK                                                            |
| series             | 提示词系列                        | varchar(64)                | 否   | 无                | 如 `guided-tutoring`；非空                                          | `UNIQUE(series, version_label)` 之一                          |
| version_label      | API `promptVersion`；文件主干     | varchar(64)                | 否   | 无                | 如 `guided-tutoring.v1`；必须等于模板文件名主干；发布后不可改        | `UNIQUE(series, version_label)` 之一                          |
| template_path      | 模板在仓库中的相对路径            | varchar(255)               | 否   | 无                | 只允许 `ai/prompts/` 下的仓库路径；不得来自用户输入或上传文件名       | 无（非键）                                                    |
| content_sha256     | 模板正文哈希                      | char(64)                   | 否   | 无；发布时计算    | `^[0-9a-f]{64}$`；用于发现文件被改动；**不把正文复制进数据库**       | 无（非键）                                                    |
| status             | 版本状态                          | varchar(16)                | 否   | `'draft'`         | CHECK IN(`draft`,`active`,`retired`)；同系列至多一个 active          | 无（非键）；部分唯一索引见上                                  |
| created_by_user_id | 登记人；系统 seed 时为空          | varchar(64)                | 是   | NULL              | 非空时必须存在                                                      | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION          |
| created_at         | 登记时刻                          | timestamptz(6)             | 否   | CURRENT_TIMESTAMP | UTC                                                                 | 无（非键）                                                    |
| activated_at       | 启用时刻                          | timestamptz(6)             | 是   | NULL              | `status='active'` 时必须非空，否则为 NULL                           | 无（非键）                                                    |
| retired_at         | 退役时刻                          | timestamptz(6)             | 是   | NULL              | `status='retired'` 时必须非空，否则为 NULL                          | 无（非键）                                                    |

**为什么不存提示词正文**：正文已在 Git 中版本化，复制进库会制造第二个真相来源；
`template_path` + `content_sha256` 足以证明「这一轮用的是哪一版、当时文件内容是什么」。
若文件缺失或哈希不符，服务应失败而不是回退到其他版本。

### model_config_versions

- 用途：模型调用配置版本（供应商、模型名、采样参数、超时），用于复现与审计；管理类。
- owner：M3。评审：M1（供应商/部署与密钥边界）。
- 候选键：`id`；`UNIQUE(config_key, version)`；部分 `UNIQUE(config_key) WHERE status='active'`。
- 索引：`(config_key, status)`。
- 数据来源：发布流程/合成 seed；配置版本与提示词版本分离，便于分别归因。
- 读写权限：服务只读；发布/退役由 M3 执行并按需通知 M1；客户端不可改模型权限。
- 保留/删除：不删除已被轮次使用的版本；退役置 `retired`。
- 状态：设计草案；PR #62 的 `service.py`（未合并）把配置写成常量，未建表、未迁移。

| 物理字段名         | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值                     | 取值范围/枚举/唯一/CHECK                                                       | PK/FK/关联与删除/更新规则                                     |
| ------------------ | --------------------------------- | -------------------------- | ---- | -------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| id                 | 配置版本标识                      | varchar(64)                | 否   | 无；服务端生成             | `modelcfg_`+32 位小写 hex                                                       | PK                                                            |
| config_key         | 配置用途键                        | varchar(64)                | 否   | `'tutoring_default'`       | 非空；同键至多一个 active                                                       | `UNIQUE(config_key, version)` 之一                            |
| version            | 递增版本号                        | integer                    | 否   | 无；服务端在事务内生成     | `>0`；`UNIQUE(config_key, version)`；不得并发 `MAX+1` 无锁生成                  | `UNIQUE(config_key, version)` 之一                            |
| provider           | 模型供应商代码                    | varchar(32)                | 否   | 无                         | 必须来自服务端登记的适配器列表（S1 为 `mock`）；不得是任意 URL 或 SDK 类名      | 无（非键）                                                    |
| model_name         | 模型名称                          | varchar(100)               | 否   | 无                         | 1..100 字符；与 provider 的可用模型清单一致                                     | 无（非键）                                                    |
| is_mock            | 是否离线假模型                    | boolean                    | 否   | 无                         | 必须与 `provider = 'mock'` 一致；与 `tutoring_turns.is_mock` 同步                | 无（非键）                                                    |
| temperature        | 采样温度                          | numeric(3,2)               | 否   | 无                         | `0 <= temperature <= 2`                                                         | 无（非键）                                                    |
| max_output_tokens  | 单轮最大输出 token                | integer                    | 否   | 无                         | `>0`；上界由具体模型决定，数据库不写死                                         | 无（非键）                                                    |
| timeout_seconds    | 单轮总超时秒数                    | numeric(6,2)               | 否   | 无                         | `>0`；连接/首 token/总时长的三 deadline 属客户端内部行为，不在此表             | 无（非键）                                                    |
| status             | 版本状态                          | varchar(16)                | 否   | `'draft'`                  | CHECK IN(`draft`,`active`,`retired`)；同 `config_key` 至多一个 active           | 无（非键）；部分唯一索引见上                                  |
| created_by_user_id | 登记人；系统 seed 时为空          | varchar(64)                | 是   | NULL                       | 非空时必须存在                                                                  | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION          |
| created_at         | 登记时刻                          | timestamptz(6)             | 否   | CURRENT_TIMESTAMP          | UTC                                                                             | 无（非键）                                                    |
| activated_at       | 启用时刻                          | timestamptz(6)             | 是   | NULL                       | `status='active'` 时必须非空，否则为 NULL                                        | 无（非键）                                                    |
| retired_at         | 退役时刻                          | timestamptz(6)             | 是   | NULL                       | `status='retired'` 时必须非空，否则为 NULL                                       | 无（非键）                                                    |

**不存密钥**：本表没有 API key、token、secret 或可执行参数列。密钥只存在于部署环境的 Secret，
表中最多出现 provider 代码；若将来需要引用，只允许存受控的 `secretRef` 与版本，
且需 M1 单独评审，不能把密钥值写进数据库或日志。

## JSONB 内部字典

JSONB 不是自由正文容器。下列属性必须由版本化 schema 严格校验；数据库层尽量加可表达的结构 CHECK，
其余由服务层与测试保证。

### tutoring_turns.follow_ups

| 物理字段名                  | 中文名称/业务含义     | PostgreSQL 类型与长度/精度        | 可空      | 默认值                | 取值范围/枚举/唯一/CHECK                                   | PK/FK/关联与删除/更新规则 |
| --------------------------- | -------------------- | --------------------------------- | --------- | --------------------- | ---------------------------------------------------------- | ------------------------- |
| follow_ups                  | 建议追问对象         | jsonb 对象                        | 否        | `{"schemaVersion":"1.0","items":[]}` | `jsonb_typeof(follow_ups) = 'object'`             | 无（非键）                |
| follow_ups.schemaVersion    | 结构版本             | jsonb 内 string，最长 16 字符     | 否        | 显式赋 `"1.0"`        | 必须为 `"1.0"`                                             | 无（非键）                |
| follow_ups.items            | 追问文本数组         | jsonb 内 string 数组              | 否        | `[]`                  | 数组长度 `<= 3`；元素为 string；**每条 1..200 字符**（服务层/测试） | 无（非键）                |

### document_import_jobs.pages_without_text

| 物理字段名                     | 中文名称/业务含义       | PostgreSQL 类型与长度/精度      | 可空 | 默认值                    | 取值范围/枚举/唯一/CHECK                                                    | PK/FK/关联与删除/更新规则 |
| ------------------------------ | ---------------------- | ------------------------------- | ---- | ------------------------- | --------------------------------------------------------------------------- | ------------------------- |
| pages_without_text             | 无文字页报告对象       | jsonb 对象                      | 否   | `{"schemaVersion":"1.0","pages":[]}` | `jsonb_typeof(pages_without_text) = 'object'`                     | 无（非键）                |
| pages_without_text.schemaVersion | 结构版本             | jsonb 内 string，最长 16 字符   | 否   | 显式赋 `"1.0"`            | 必须为 `"1.0"`                                                              | 无（非键）                |
| pages_without_text.pages       | 无文字页页码列表       | jsonb 内 integer 数组           | 否   | `[]`                      | 元素为 `>=1` 的整数、升序去重；页号 1 基；成功前为空数组（服务层/测试）     | 无（非键）                |

**为什么用对象而不是裸数组**：`schemaVersion` 需要一个稳定位置；裸数组无法在不破坏读取方的前提下
演进结构。空值用默认对象表示「没有」，不能写成 `null`。

## 数据库到 API 的映射

| API / 契约字段 | 来源 | 说明 |
| --- | --- | --- |
| `sessionId` | `tutoring_sessions.id` | 不透明字符串 |
| `turnId` | `tutoring_turns.id` | 不透明字符串 |
| `stage` | `tutoring_turns.stage`（本轮）、`tutoring_sessions.current_stage`（下一次） | 响应里是本轮冻结值 |
| `content` | `tutoring_turns.assistant_content` | 与 delta 拼接逐字节一致；可尾随 `\n` |
| `citations[].citationId` | `turn_citations.citation_id` | 轮内标签，不跨轮稳定 |
| `citations[].documentId` | `turn_citations.document_id` | 文档**版本** ID |
| `citations[].documentTitle` | `turn_citations.document_title_snapshot` | 展示用；不回读当前 `documents.title`，避免历史被改名影响 |
| `citations[].pageNumber` | `turn_citations.page_number` | 1 基 |
| `citations[].snippet` | `turn_citations.snippet` | 引用时快照 |
| `hasEvidence` | `tutoring_turns.has_evidence` | 与 citation 是否为空一致 |
| `followUps` | `tutoring_turns.follow_ups.items` | 至多 3 条 |
| `emotion` / `action` | `tutoring_turns.emotion` / `action` | 取值待 M4 冻结 |
| `isMock` | `tutoring_turns.is_mock` | 与模型配置一致 |
| `promptVersion` | `prompt_versions.version_label`（联表） | 不直接暴露内部 `id` |
| `createdAt` | `tutoring_turns.settled_at` | PR #62 对完成响应取装配时刻；持久化后取终态时刻，语义一致 |
| SSE 事件 `seq` | 不持久化 | 流内计数，每次请求重新从 1 开始 |
| SSE `error.code` | `tutoring_turns.error_code` | 仅 `errored` 轮次有值 |
| SSE `error.details.reason` | `tutoring_turns.error_reason` | 内部原因码 |
| SSE `error.requestId` | `tutoring_turns.request_id` | 创建轮次的请求号 |

**API 不暴露**：`student_user_id`（以及其他学生的任何标识）、`storage_key`、`file_sha256`、
内部版本 `id`、`updated_at`、`model_config_version_id` 的原始值。
`request_id` 仅按契约出现在错误事件与响应头中。
错误与日志按 `docs/code-standards.md` 记录标识与计数，不记录完整对话正文（`student_content`、
`assistant_content` 都不进日志）。

## 授权与检索边界

这段是本域最容易被误解的地方，单独写清楚：

1. **鉴权先于检索。** 收到提问后，服务端先用已验证身份（PR #62 中为合成的 `Principal`，未合并；
   待 #16 的 `require_user` 替换）确定 `student_user_id`；再确定「该用户能访问哪些文档」。
2. **授权集合只由授权方产生。** 来源包括：M1 的角色与文件访问规则、M5 的选课/授课关系、
   `document_grants` 的显式用户授权、`documents.uploader_user_id` 的上传者访问。
   **检索层只接收结果，永不自算授权**（ADR-0004）。
3. **`courseId` 只能收窄。** 请求里的 `courseId` 与已授权集合求交；交集为空就是
   `hasEvidence=false`，不能因为传了 `courseId` 就放宽到该课程全部文档。
4. **引用白名单在服务端。** 模型返回的 `citationId` 只是标签；服务端遍历本轮检索结果，
   丢弃不在白名单内的标签，按服务端顺序组装 `turn_citations`。
   检索候选只来自 `documents.status='available'` 的版本；`uploaded`（尚未解析成功）与
   `withdrawn`（已下架）都不进入新轮次的候选集。
5. **Mock 与真实模型走同一授权路径。** Mock 不能因为「是假模型」就跳过授权；
   `isMock` 只标记来源，不改变权限判定。
6. **文件下载权与检索引用权分开。** 学生能看到引用不代表能下载原始 PDF；
   下载走 M1 的文件访问控制，需要单独授权与审计。

## 必须保留的验收反例

以下行为应在迁移与集成测试中被拦截，而不是靠人工记得：

1. 学生 A 读取学生 B 的会话或轮次：查询返回 404 或 0 行；不能通过修改路径参数绕过归属检查。
2. 同一会话并发发起两个提问：第二个因 `UNIQUE(session_id) WHERE status='active'` 失败并返回 409；
   实际只有一轮 `completed`，阶段只推进一级。
3. `stopped` / `errored` / `disconnected` 轮次不推进 `tutoring_sessions.current_stage`
   （`status <> 'completed'`，服务层断言）。
4. `hasEvidence=false` 的轮次没有 citation 行；`hasEvidence=true` 的轮次至少一条 citation，
   且每条 `document_id` 都在本轮授权检索结果内。
5. 对已撤销授权或未授权文档的引用无法落库：服务层白名单丢弃标签；伪造的 `documentId`
   即使通过外键也不能证明访问权，必须以授权集合为准。
6. 仍有 `turn_citations` 引用的文档执行硬删：`RESTRICT` 拒绝；下架（`withdrawn`）后
   历史引用仍能读到页码与 `snippet`。
7. 重新解析同一份课件：新建 `documents` 版本与新 chunks，旧引用仍指向旧 `document_version`，
   页码与片段不被新版本覆盖。
8. 同一 `(document_id, idempotency_key)` 重复提交解析任务：返回同一 `jobId`，不产生第二个运行中任务。
9. 同一 `series` 或 `config_key` 出现两个 `active` 版本：部分唯一索引拒绝。
10. Mock 轮次的 `is_mock` 为 true 且对应 `model_config_versions.provider='mock'`；
    不能把 Mock 结果标成真实模型。
11. `documents.title` 或 `document_chunks.text` 中含指令式文本：只作为数据进入提示词数据槽，
    不执行、不改变系统指令；`title` 不进入提示词。
12. 学生修改请求体或路径里的 `student_user_id`：服务端忽略，归属仍取自已验证凭证。

## 待确认事项

- [ ] **M5**：班级/课程可见性如何归一化为「已授权文档集合」；`document_grants` 是否需要在
      M5 定义后新增受 FK 约束的班级列，还是继续只做用户级例外授权。
- [ ] **M1**：`chunk_`、`grant_`、`job_`、`promptver_`、`modelcfg_` 五个新前缀是否登记到平台契约；
      `users`/`courses` 迁移必须先于本域，迁移顺序由 M5 协调、M1 检查可部署性。
- [ ] **M4**：`emotion`/`action` 正式枚举冻结后，为 `tutoring_turns` 增加 CHECK 并升级提示词到 v2；
      本 PR 不预写未冻结的取值。
- [ ] **M2/M6**：`documents.status` 与 `document_import_jobs.status` 是否都需要对外展示；
      解析状态接口的响应结构由 M6 的契约决定，本表只提供事实。
- [ ] **M6/M3**：上传者自动访问用 `documents.uploader_user_id` 派生、不写授权行，是否被接受。
- [ ] **全员**：学生会话、问答正文与上传文档的保留期限需要学校/项目给出实际要求；
      本文不编造天数，保留策略在得到要求前只写「按确认后的期限执行」。
- [ ] **M1/M2**：`sessionId` 由客户端路径提供、服务端首次见到即创建的现有语义，持久化后如何调整
      （服务端发号 vs 客户端不透明查询键）；旧短 ID 样例的兼容边界也需一并确认。
- [ ] **M1**：`tutoring_sessions.course_id` 可空是否符合 S1 的会话创建方式（PR #62 中首个提问即建会话，
      可能没有课程上下文）。
- [ ] **M1/M3**：`input_tokens`/`output_tokens`/`duration_ms` 这类评测字段是否留在业务表，
      还是迁到评测结果存储；保留在表里会扩大学生数据的存储面。
- [ ] **M1/M5/M6**：版权或授权撤回导致必须删除课件时，既有引用快照如何处理；
      需要一条明确的数据清除流程，不能靠 `CASCADE` 静默抹掉历史。

## 本文的验证与证据

本 PR 为**纯文档**，没有改代码、没有建表、没有迁移。实际执行的检查：

- `git diff --check`：无空白错误。
- 用脚本核对每张 markdown 表内列数一致，并确认 11 张七要素表（9 张表 + 2 张 JSONB 字典）
  每行恰好 7 列、表头与 #69 的七要素模板一致。
- 逐条核对字段与 `packages/contracts/tutoring/`（已合并）及
  `apps/api/app/domains/tutoring/`（PR #62 分支，未合并）的现有取值；
  没有新增未在契约中出现的 API 字段。
- 链接与路径检查：本文引用的是仓库相对路径；`docs/data-model/` 下三份基线文件由 #73 引入，
  两份 PR 都合并后才会在 main 上同时存在。issue 链接指向公开仓库。

**没有运行**：pytest、ruff、mypy、真实 PostgreSQL。它们与纯文档改动无关；
一旦进入 B 批迁移，必须另行提供 `upgrade head`、约束/索引核对与真实 PostgreSQL 测试证据。
