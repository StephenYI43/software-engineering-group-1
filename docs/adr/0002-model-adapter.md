# ADR-0002：模型 adapter 接口与离线 Mock 规范

状态：提议（M1 已答复文末待确认事项第 1—3 条，其余仍待确认）
日期：2026-09-15
提出人：M3 / @ljt2293977194-dotcom
评审人：M1 @StephenYI43、M5 @Jiege123-CMYK
（M1 已认定本 ADR 属于公共接口，按 `CONTRIBUTING.md:37` 需至少 2 名评审人）
关联 Issue：[#15](https://github.com/StephenYI43/software-engineering-group-1/issues/15)

## 问题与约束

`docs/tasks/m3.md:11` 要求「定义 tutoring schema、SSE 事件和模型 adapter，支持离线 Mock」。
其中 schema 与 SSE 事件已由 PR #9 合并，本 ADR 处理剩下的 adapter。

> **引用约定**：本文中带 `docs/` 前缀的为仓库根相对路径；
> 单独出现的 `tutoring-response.md` 与 `sse-events.md` 均指
> `packages/contracts/tutoring/` 下的同名文件。所有行号以 `main` = `12e344c`（PR #12 合并后）为准，
> 后续改动可能使其偏移。

adapter（适配器）位于答疑逻辑与模型供应商之间：上层只依赖一个统一接口，接口下有两个实现——
`MockModelClient`（不联网、不花钱、输出可预测，供开发与 CI）与真实供应商客户端。
依据：`docs/code-standards.md:65`「模型供应商经统一 adapter 调用，支持 Mock；禁止页面中硬编码供应商 SDK 调用」。

它同时是契约中 `isMock` / `promptVersion` 两个必填字段（`tutoring-response.md:77-78`）在代码里落地的那一层。

**本文件的范围是规范，不含实现。** 这一条在 PR #12 合并前后理由不同，如实说明：

- PR #12 合并前，`apps/api/` 在 main 上只有 M6 的
  `apps/api/app/domains/analytics/README.md`，没有 `pyproject.toml`、没有 `app/main.py`，**写不了代码**。
- PR #12（`12e344c`）已合并，骨架现已存在（`apps/api/app/main.py:18` 的 `create_app()`），
  **这个阻塞已消失**。选择先出规范、后写实现，依据是 `CONTRIBUTING.md:8`「先确认接口样例，再实现和测试」
  与 `AGENTS.md:4`「公共接口先出 schema 和样例」，而不是因为做不了。

因此本 ADR 的接口**尚未有实现**，其正确性只能靠评审确认，不能靠测试证明。

### 职责边界：adapter 只做三件事

| 事项 | 归属 | 依据 |
| --- | --- | --- |
| 文本增量流、上游超时与取消、供应商密钥 | **adapter（本 ADR）** | 本文档 |
| `stage` 的计算与推进 | 服务端状态机 | `tutoring-response.md:70,130` |
| `citations` 白名单校验、越界引用丢弃 | 服务端 | `tutoring-response.md:121-122` |
| `hasEvidence` 判定 | 检索层 | `tutoring-response.md:119` |
| 输出结构校验失败后的重试 | **服务端，不是 adapter** | `sse-events.md:126` |
| `isMock` 取值 | 装配层注入 | `tutoring-response.md:127-129` |
| `promptVersion` 取值 | 调用方传入，adapter 原样回传 | `tutoring-response.md:78` |
| 授权文档集合 | 检索层输入，adapter 只接收 | `docs/requirements.md:26` |

一句话：**adapter 只把「提示词 + 检索片段」变成无结构的增量文本流，并如实报告来源与用量；
一切教学语义由服务端决定。**

## 候选方案与选择理由

### 1. 本规范放在哪里

选择 **`docs/adr/`**，不放 `packages/contracts/`。

- `docs/code-standards.md:84-93` 是仓库自己那份「首批需明确的边界」清单，**没有模型 adapter**。
  仓库已经认定什么算跨角色契约，这个不算。
- `docs/code-standards.md:26` 定义 `packages/contracts/` 为「OpenAPI 快照、事件 schema、示例」；
  adapter 的 chunk 是**进程内 Python 类型**，三者都不是。
- `packages/contracts/tutoring/README.md:2-4` 写明该目录的读者是 M2/M4/M5，**他们都不调用 adapter**；
  且该目录有 4 名共同 owner（`.github/CODEOWNERS`），会让三人评审一份与自己无关的文档。
- **决定性依据**：`docs/adr/0000-template.md:18` 写明「首个技术栈 ADR 由 M1 提交，记录运行时/依赖版本、
  包管理器、数据库、**模型 adapter**、测试命令」——仓库已把模型 adapter 划归 ADR。
- **PR #12 合并后新增的依据**：`docs/code-standards.md:3` 改为「具体前端/数据库版本、**模型供应商**
  和部署平台在相应任务的 ADR 中锁定」。模型供应商的选型归属被明确写成 ADR 的职责，
  而 adapter 正是隔离供应商的那一层。

**编号取 0002**：ADR-0001 已在 PR #12 合并时落地（`docs/adr/0001-platform-bootstrap.md`）。
M1 已确认本文件用 0002，并规定了合并顺序（见「验证、迁移与回滚」）。

### 2. adapter 的目录归属

**决策：采用方案 B —— `apps/api/app/domains/tutoring/adapters/`（M1 于 2026-09-15 在 Issue #15 答复）。**

| 方案 | 路径 | 取舍 |
| --- | --- | --- |
| A 共享 | `apps/api/app/core/llm/` | 符合 `docs/code-standards.md:65`「**统一** adapter」的字面；M4 的 ASR/TTS 将来可复用。代价是 M1 成为永久共同 owner，M3 每次改动都要他评审 |
| **B 领域内（已采用）** | `apps/api/app/domains/tutoring/adapters/` | 与 `docs/team-plan.md:22` 的 M3 负责目录一致，改动自主。代价是与 M4 可能重复实现供应商客户端 |

起草时本文曾倾向 A，理由是重复的供应商客户端是更大的长期风险。
M1 选择 B，**本 ADR 记录该决策，不代其补充理由**。B 的已知代价如实保留：
若 M4 的 ASR/TTS 需要同类适配器，双方需各自实现，或日后再提取共享层，本 ADR 不预留该层。

`adapters/` 是 `docs/code-standards.md:33`（router / schemas / service / repository）
之外的**第五层**。是否把它写进那份目录规范需另开一个小 PR，不在本 ADR 中顺手改
（`CONTRIBUTING.md:39`「每个 PR 一个目标」）。

**一条需要留意的后果**：方案 B 使该目录的 CODEOWNERS 规则是
`/apps/api/app/domains/tutoring/ @ljt2293977194-dotcom`（单人），而 M1 又认定本接口是公共接口。
`CONTRIBUTING.md:43` 明确 CODEOWNERS **不等于**分支保护、不强制评审人数，
因此「公共接口需 2 名评审人」这条**只能靠约定执行**：接口变更时须在 PR 中显式 @ 评审人。

### 3. 不给 chunk 配 JSON Schema

仓库唯一的 schema 文件描述的是 **HTTP 线上响应**（`packages/contracts/platform/`）。
adapter 的 chunk 是**进程内类型**，唯一消费者是 Python 代码；而**公开契约本身（tutoring）
就没有配 schema，用的是文字 + `samples/`**。给一个更窄、非公开的类型配 schema，比公开契约还严，说不通。

改为在本文中给出：接口草图（作为规范字段清单，不是代码）、chunk 变体表、一段走查。

## 决策、影响与接口变化

### 接口

```python
async def generate(request: ModelRequest) -> AsyncIterator[ModelChunk]: ...
```

异步：路由层是 async，且取消必须能沿调用链传播。

`ModelRequest` 字段固定为：`requestId`、`promptVersion`、`modelName`、渲染好的 `systemPrompt`、
`turns`、`retrievedChunks`（标注为**不可信数据**）、`maxOutputTokens`、`temperature`、`timeoutSeconds`。

**明确不含**：`stage`、工具定义、引用白名单。

### chunk 变体（封闭联合）

| 变体 | 载荷 | 说明 |
| --- | --- | --- |
| `TextDelta` | `text` | 增量正文，服务端按序拼接即为 `content` |
| `Usage` | `inputTokens`、`outputTokens` | 供日志记录 token 用量 |
| `Finished` | `stopReason` | 正常结束 |

- 错误**抛异常，不作为 chunk yield**。
- **不存在 `ThinkingDelta`，将来也不会有。** 依据 `tutoring-response.md:92-95`：
  「实现上模型适配器**不得转发** `thinking_delta` 一类的内部推理增量」。
  规范化为可测要求：供应商若输出推理通道，adapter 内部丢弃；
  最终 chunk 序列必须与「供应商未输出推理」时**逐字节一致**。

### 错误映射

| 失败 | 由谁产生 | code |
| --- | --- | --- |
| 连接 / 首 token / 总时长超时 | adapter | `MODEL_TIMEOUT` |
| 供应商显式拒答 | adapter | `MODEL_REFUSED` |
| 输出无法解析或未通过结构校验（含重试后仍失败） | **服务端** | `MODEL_OUTPUT_INVALID` |
| 检索不可用 | 检索层（此时不应调用 adapter） | `RETRIEVAL_UNAVAILABLE` |

**必须记录的缺口：** `sse-events.md:126-130` 现有的五个错误码中，
**没有「供应商 5xx / 密钥无效 / 配额耗尽」的位置**。补一个码（如 `MODEL_UNAVAILABLE`）
需要修改 `sse-events.md`——那是 4 名共同 owner 的公共契约，
必须另开 Issue、另开 PR（`AGENTS.md:7` 不擅自改公共接口）。列入「后续工作」。

另两条规范性结论：

- `RETRIEVAL_UNAVAILABLE` **不是 adapter 的错误**；它发生时，流中不应已有任何 `delta`。
- `MODEL_OUTPUT_INVALID` 由服务端产生，因此 **adapter 对结构校验是单次尝试、不重试**。
  这一条正是 Mock 能保持确定性的前提。

### 超时、重试与取消

- 三个 deadline 分开命名并给默认值（具体秒数待确认）：**连接**、**首 token**、**总时长**。
  依据 `docs/code-standards.md:63`「外部请求设置超时，重试有上限且考虑幂等」。
- **重试只允许发生在第一个 `TextDelta` 之前。** 其后重试会重复已显示的文本，
  并破坏 `sse-events.md:26`「`seq` 不跳号、不重复」的契约——此为硬规则。
- **取消**：用户停止时，服务端必须关闭上游模型流（`sse-events.md:140`「不继续计费」）。
  adapter 规范：在 `finally` 中关闭上游连接；**不吞 `asyncio.CancelledError`**
  （`docs/code-standards.md:63`「不吞异常」）；`aclose()` 必须可被重复调用，
  因为 `sse-events.md:139` 要求停止操作幂等。
- **断连**：`sse-events.md:145-149` 规定不重试、不续传。adapter 不得自行恢复。

### `isMock` 与 `promptVersion`

- `isMock` 来自**装配层**，绝不来自模型，且在三处必须一致：`started` 事件、最终响应、日志。
- **本 ADR 最需要钉死的一条**：真实供应商失败、本轮降级到 Mock 时，
  `isMock` **必须翻为 `true`**。`tutoring-response.md:127-129` 要求「如实反映数据来源」，
  报 `false` 即契约违规，同时违反 `AGENTS.md:8`。
- `promptVersion` 由服务端从 `ai/prompts/guided-tutoring.v1.md`
  （文件名约定见 `docs/code-standards.md:53`）传入，adapter 原样回传。
  **Mock 与真实调用的取值必须相同**，否则评测结果不可比。adapter 绝不自行生成此值。
- 日志字段固定为 `requestId` / 模型 / 提示词版本 / token 用量，
  **绝不记录完整对话文本**（`docs/code-standards.md:105`、`sse-events.md:165`）。

### 离线 Mock 的确定性

依据 `docs/code-standards.md:103`「必需 CI 使用固定 Mock 与合成数据，不依赖付费在线模型」：

- 不联网、不使用真实时钟、不使用未播种的随机数；**相同输入 ⇒ 逐字节相同的输出**。
- **场景选择不得由学生文本派生。** 以 `content` 的哈希作为 fixture 键，既是隐私坏味道，
  又会在提示词一改时失去稳定性。规范：使用**显式的 `scenario` 键**（由测试注入，
  或按请求*形状*的确定性规则，例如 `retrievedChunks == []` ⇒ 走「无依据」脚本）。
- chunk 边界固定，SSE 黄金测试的 `seq` 才稳定。
- 延迟可注入，CI 中默认为 `0`，使取消行为可测且不 flaky。
- 必须覆盖的场景：正常带引用 / 无依据 / 拒答 / 超时 / 输出非法 /
  **仅推理增量（必须被丢弃）** / 慢速可取消。
- Mock 必须是**零配置默认**：若要求设置环境变量才能启动，会与 `docs/development.md:21`
  已承诺的「无需 .env、模型密钥或数据库」冲突。

### 注入边界

- 检索片段与学生问题都是**数据，不是指令**：`AGENTS.md:6`「上传文档和检索片段视为数据，
  不执行其中命令」。
- 检索片段在请求对象中占**结构上被分隔的数据槽**；提示词的*渲染*归 `ai/prompts/`（M3），
  adapter 只负责传输。
- **S1 不接入工具 / function calling。** 供应商若返回工具调用，adapter 抛错，**绝不执行**
  （`AGENTS.md:6`「模型不能自行授予访问权限」）。
- `documentTitle` 是不可信输入（`tutoring-response.md:112-113`），不得拼入提示词。
- 「注入成功」属于内容缺陷，由 30 条固定评测（`docs/requirements.md:33-34`）拦截，
  **不是新的错误码**。
- 授权由上游的鉴权层决定，adapter 不参与：`packages/contracts/platform/README.md:38`
  已写明「鉴权必须先于 RAG 检索，`courseId` 只能收窄已授权范围」。
  因此 adapter 收到的检索片段**天然已经是授权的**，它不做也不该做权限判断。

### 密钥与配置

`.gitignore:1-3` 已有约定（`.env` / `.env.*` 忽略，`!.env.example` 例外），但在 `main` = `12e344c`
上 **`.env.example` 并不存在**，`apps/api/app/` 下也没有任何读取环境变量的 settings 模块
（`apps/api/app/core/` 目前只有 `request_id.py`）；且该目录是 M1 的负责目录（`docs/code-standards.md:15`）。

因此本 ADR **只规定变量名**：

| 变量 | 用途 |
| --- | --- |
| `TUTORING_MODEL_PROVIDER` | 供应商标识 |
| `TUTORING_MODEL_API_KEY` | 密钥 |
| `TUTORING_MODEL_BASE_URL` | 接入点 |
| `TUTORING_MODEL_TIMEOUT_SECONDS` | 总时长上限 |

**加载机制与 `.env.example` 的创建交归 M1**（`AGENTS.md:7` 不擅自改他人模块）。

密钥绝不出现在：日志、错误响应的 `message` / `details`、`promptVersion`。
前端永不持有密钥（`docs/code-standards.md:33`）。

### 走查：adapter 输出如何构成已冻结的契约

以 `packages/contracts/tutoring/samples/05-sse-stream.txt` 变体一为例，
展示 adapter 的 chunk 序列如何映射到已冻结的 SSE 事件，**全程不需要修改契约**：

| adapter chunk | 服务端动作 | 产生的 SSE 事件 |
| --- | --- | --- |
| （调用前） | 状态机算出 `stage`，装配层确定 `isMock` | `started`，`seq=1` |
| `TextDelta("我们先不急着算结果。")` | 编号 `seq=2` 下发 | `delta` |
| `TextDelta("你想想…")` | `seq=3` | `delta` |
| `Usage(inputTokens, outputTokens)` | 记日志，不下发 | — |
| `Finished(stopReason)` | 校验引用白名单、组装 `TutoringResponse` | `completed`，`seq` 为最大值 |

要点：`stage` 从未经过 adapter；`citations` 由服务端从白名单重建；
`Usage` 只进日志。这证明 adapter 的窄接口足以产出已冻结的契约。

## 验证、迁移与回滚

**本 ADR 无可执行代码，所以没有测试可验证它。** 这一点与 PR #12 合并前不同，如实说明：

- 本 PR 只新增一个 markdown 文件。`ruff` / `mypy` / `pytest` **不会读到本文件的任何内容**，
  跑了也不构成对本 ADR 的验证。
- 因此本 ADR 唯一的验证方式是评审：接口字段是否够用、职责边界是否划错、错误映射是否与既有契约自洽。
- 本文档**不是** Mock 已存在的证据（`AGENTS.md:4`）。

**附带实测（测的是 M1 的骨架，不是本 ADR）。** 为确认本 ADR 依赖的那套质量门槛真实可用，
按 `docs/development.md:33-38` 的命令在 `apps/api/` 下实跑了一遍：

| 命令 | 实际结果 |
| --- | --- |
| `uv sync --locked` | 按 `uv.lock` 安装成功 |
| `uv run --locked ruff format --check .` | `6 files already formatted` |
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked mypy` | `Success: no issues found in 4 source files` |
| `uv run --locked pytest` | `3 passed`，覆盖率 **100%**（26 statements），2 条警告 |

结论：`strict = true` 的 mypy 与 80% 覆盖率门槛（`docs/development.md:40`）**确实被执行**，
将来 `adapters/` 的实现在这套门槛下必须完整标注类型。

**实测环境与仓库基线存在偏差，必须说明**：本机为 Python 3.12.10 + uv 0.11.14，
而仓库锁定 Python 3.12.14 + uv 0.12.13（`docs/development.md:7`、`docs/adr/0001-platform-bootstrap.md:13`）。
因此上表**不能替代 CI**；`.github/workflows/api-ci.yml` 会在本 PR 上触发
（该工作流在 `pull_request` 上触发、未设路径过滤，但 `working-directory` 固定为 `apps/api`），
其运行结果以 PR 页面为准，本文不预判。它检验的仍是 M1 的骨架——
**通过不代表本 ADR 被验证**，也不代表 CI 已设为 main 必需检查（`CONTRIBUTING.md:43`）。
那 2 条警告与 `docs/adr/0001-platform-bootstrap.md:31` 记载的 httpx / anyio 上游弃用警告一致。

评审依据按 `CONTRIBUTING.md:39`「提供实际运行的命令和证据」写在 PR 说明中。

**回滚**：本文档只新增一个文件，回滚即 `git revert` 该提交，无迁移、无数据影响。

**合并顺序（M1 于 Issue #15 规定，现已执行）**：

1. ~~PR #12（ADR-0001）先合并~~ —— 已完成，合并提交 `12e344c`
2. ~~本分支 rebase 最新 `main`~~ —— 已完成，本分支基点已是 `12e344c`
3. 本 ADR 再合并 —— **待办**

实现阶段的门槛现已明确（`apps/api/pyproject.toml`）：`strict = true`（`:32`）且
`files = ["app"]`（`:33`），意味着将来 `app/domains/tutoring/adapters/` 下的代码**必须完整标注类型**；
`line-length = 100`（`:25`）、lint 规则 `E F I B UP`（`:28`）、覆盖率下限 80%（`:38`）。
这些约束的是实现代码，与本文件无关，此处列出只为说明本文的接口草图在实现时必须补全类型标注。

## 后续工作

以下均需**另开 Issue**，不在本 ADR 中实施：

1. adapter 的 Python 实现与 Mock。**前置阻塞已解除**（PR #12 已合并，`apps/api/` 骨架可用），
   目录已定为 `apps/api/app/domains/tutoring/adapters/`；实现须满足 mypy `strict` 与覆盖率下限。
2. 为「供应商 5xx / 密钥无效 / 配额耗尽」补错误码，需修改 `sse-events.md` 并请 4 名 owner 评审。
3. `adapters/` 作为第五层是否写入 `docs/code-standards.md:33` 的目录契约，需另开小 PR 决定。
4. 提示词文件 `ai/prompts/guided-tutoring.v1.md` 的建立与版本化（`docs/tasks/m3.md:13`）。

## 待确认事项

- [x] M1 确认 adapter 目录 —— 方案 B（`apps/api/app/domains/tutoring/adapters/`）
- [x] M1 确认 ADR 编号安排 —— 用 0002，并规定合并顺序（见「验证、迁移与回滚」）
- [x] M1 确认本 ADR 属于「公共接口」—— 是，故按 `CONTRIBUTING.md:37` 需至少 2 名评审人
- [ ] M5 确认接口形状与错误映射
- [ ] M4 确认是否需在媒体域另建适配器（方案 B 的已知代价，见「候选方案」第 2 节）
- [ ] 三个超时默认秒数

**此清单未勾选即未确认，不以 AI 自评代替成员评审。**

## 相关依赖（均未冻结）

- `packages/contracts/tutoring/README.md:6` 声明契约「待 M2 / M4 / M5 评审确认，确认前不应据此编写生产代码」。
- `tutoring-response.md:145-168` 的 ID 形态待确认。M1 的平台契约已给出候选前缀
  （`packages/contracts/platform/README.md:24-25`：`doc_` / `sess_` / `turn_` 归 M3），
  并把「M3/M5 确认 ID 格式和数据库到 API 映射」列为待办（同文件 `:48`）。
  **本 ADR 不重复定义 ID 形态**，只依赖该约定落定。
  另注：M1 已采纳本契约的 `citationId` 约定（同文件 `:32`「citationId=c1/c2 是轮内标签，
  保持原约定，不作为实体主键」）。
- `sse-events.md:9-12` 的 fetch / EventSource 选择待 M2 确认。
- `tutoring-response.md:132-143` 的 `emotion` / `action` 定义权在
  `docs/tasks/m3.md:23` 与 `docs/tasks/m4.md:23` 之间相互矛盾，仍是占位值。
  M1 的平台契约表述为「M4 …另在其模块冻结 emotion/action 枚举」
  （`packages/contracts/platform/README.md:50`），即倾向于 M4 定义，但**仍未拍板**。
- 引用不变量（`tutoring-response.md:121`）依赖「文档级授权表」，该表目前无人认领。
  本 ADR 的立场是结构性的：**adapter 只接收已授权的文档白名单，自身永不计算授权。**
  这一立场与 `packages/contracts/platform/README.md:38` 一致（鉴权先于检索）。
