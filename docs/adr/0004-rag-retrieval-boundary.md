# ADR-0004：RAG 文档解析与检索层边界

状态：提议（**尚无实现**，仅规范；待 M1 / M5 评审，不代表全员已批准）
日期：2026-09-20
提出人：M3 / @ljt2293977194-dotcom
评审人：M1 @StephenYI43（架构与依赖锁文件）、M5 @Jiege123-CMYK（M3 的固定交叉评审人）
关联 Issue：#53（本 ADR 的实施载体）；提示词与评测那一半在 #40，两者互不阻塞
相关基础：ADR-0002 已合并（PR #20）；tutoring 契约状态见 `packages/contracts/tutoring/README.md:6-8`。

> **引用约定**：带 `docs/` 前缀的为仓库根相对路径；单独出现的 `tutoring-response.md` / `sse-events.md`
> 指 `packages/contracts/tutoring/` 下同名文件；`platform/README.md` 指 `packages/contracts/platform/README.md`。
> 行号以 `main` = `dd16171`（PR #34 合并后，2026-09-20 逐条核对）为准，后续改动可能使其偏移。
> 该基准核对时已确认：本文引用的全部文件（`AGENTS.md`、`CONTRIBUTING.md`、
> `docs/code-standards.md`、`docs/development.md`、`docs/requirements.md`、`docs/team-plan.md`、
> `docs/tasks/m3.md`、`docs/tasks/m5.md`、`docs/adr/0002-model-adapter.md`、
> `packages/contracts/tutoring/`、`packages/contracts/platform/README.md`、`apps/api/`）
> 在此前两次 main 前进中都**未被修改**，行号继续成立。
> 本文中所有第三方库的版本、许可证与依赖项均于 2026-09-20 **实际下载 wheel 并读取元数据核对**，
> 核对方式与被否掉的理由写在「候选方案」第 2 节，不是凭印象。
>
> **一处已存在的引用偏移，顺手记下**：`AGENTS.md` 的编号规律是「第 N 条在第 N+4 行」
> （第 1 条在第 5 行），但仓库里有多处把**条号当成行号**：
> `docs/adr/0002-model-adapter.md:195,200` 与
> `apps/api/app/domains/tutoring/adapters/base.py:37` 把「上传文档和检索片段视为数据」
> 引作 `AGENTS.md:6`（该行实际是第 2 条），**正确是 `AGENTS.md:10`**；
> 同一份 ADR 的 `:34,251` 把「Mock 必须明确标记」引作 `AGENTS.md:4`，**正确是 `AGENTS.md:8`**。
> 本文按**实际行号**引用。上面几处旧引用是否修正由各自 owner 决定，本 ADR 不改他人文件。

## 问题与约束

`docs/tasks/m3.md:12` 要求「实现授权课程 PDF 解析、切分、检索及页码引用」，
这是 S1 的主体（`docs/tasks/m3.md:19`「S1 一门高数课 PDF 和文字答疑」）。

### 已经冻结的两件事（本 ADR 不重新设计）

1. **检索层的输出形状已存在**：`apps/api/app/domains/tutoring/adapters/base.py:31-48` 的
   `RetrievedChunk`（`document_id` / `document_title` / `page_number` / `text`）。
2. **「无依据」的行为已存在**：`apps/api/app/domains/tutoring/adapters/mock.py:100-103` ——
   `retrieved_chunks` 为空序列时，Mock 自动走 `no_evidence` 脚本。

因此本 ADR 处理的是 `RetrievedChunk` 的**上游**：从「一份 PDF」到「若干 `RetrievedChunk`」
之间的那一段。它不修改上面两者，也不重新讨论答疑流程本身。

### 约束

| # | 约束 | 出处 |
| --- | --- | --- |
| C1 | 引用必须来自该用户**有权访问**的课件，显示文件名和页码/片段 | `docs/requirements.md:26` |
| C2 | **鉴权必须先于 RAG 检索**，`courseId` 只能收窄已授权范围 | `platform/README.md:38` |
| C3 | `pageNumber` 从 1 开始，不允许 0 或负数 | `tutoring-response.md:107,110` |
| C4 | `hasEvidence = false` ⟺ `citations` 为空数组 | `tutoring-response.md:119` |
| C5 | 每条 citation 的 `documentId` 必须属于本轮授权检索结果 | `tutoring-response.md:121-122` |
| C6 | **公开仓库禁止真实学生信息和课件原文**；测试资料用合成或已获许可材料 | `docs/code-standards.md:107` |
| C7 | 依赖经 `uv.lock` 锁定并保留哈希，禁止合并时隐式更新；**依赖升级必须单独评审锁文件变化** | `docs/adr/0001-platform-bootstrap.md:13,15` |
| C8 | 新增框架、模型服务或数据库需说明理由并由受影响负责人评审 | `docs/code-standards.md:5` |
| C9 | 异步解析返回 **202 与 jobId**，任务状态查 `queued/running/succeeded/failed`，重复提交需幂等 | `docs/code-standards.md:82` |
| C10 | 上传文档和检索片段视为**数据，不是指令**，不执行其中命令 | `AGENTS.md:10` |
| C11 | 首版只做 **PDF**；PPTX / OCR 属 S2 | `docs/requirements.md:14`、`docs/tasks/m3.md:14` |
| C12 | 不擅自引入新框架、改**公共接口**或改写他人模块 | `AGENTS.md:7` |
| C13 | 每个 PR 一个目标，推荐不超过 400 行有效业务代码 | `CONTRIBUTING.md:39` |

### 两个空位（本 ADR 存在的直接原因）

**空位一：`apps/api/app/domains/knowledge/` 目录不存在。**
`docs/code-standards.md:17-18` 与 `docs/team-plan.md:22` 都把 `knowledge/` 划给 M3，
`.github/CODEOWNERS` 也已有 `/apps/api/app/domains/knowledge/ @ljt2293977194-dotcom` 一行，
但该目录**一个文件都没有**。解析、切分、索引、检索没有落点。

**空位二：「授权文档表」无人认领。** ADR-0002 结尾已如实记载这一点
（`docs/adr/0002-model-adapter.md:329`「引用不变量依赖『文档级授权表』，该表目前无人认领」）。
`docs/tasks/m3.md:23` 把「权限与文件访问」列为 M1 的依赖，`platform/README.md:34-40` 的身份与权限
一节也**尚未实现**。也就是说：C2 要求鉴权先于检索，但**产出「已授权文档集合」的那一方今天不存在**。

本 ADR 对空位二的立场是**结构性的、与 ADR-0002 一致**：检索层**只接收**已授权的文档集合，
**自身永不计算授权**。这不是绕过 C2，而是把 C2 的落点固定在检索层之外。
代价如实说明：**在 M1 交付授权表之前，S1 只能靠调用方传参跑通，无法端到端演示 C1。**

## 候选方案与选择理由

### 1. 解析、切分、检索放在哪个域

**决策：方案 A —— 全部落在 `apps/api/app/domains/knowledge/`，`tutoring` 通过公开服务函数调用。**

| 方案 | 落点 | 取舍 |
| --- | --- | --- |
| **A 独立域（已采用）** | `app/domains/knowledge/` | 符合 `docs/code-standards.md:17-18` 的两个目录划分；`tutoring` 只消费结果 |
| B 并入答疑 | `app/domains/tutoring/` | 文件更少、少一层间接。但把「文档」这一概念塞进只该关心「教学」的域 |
| C 折中 | 解析/索引在 `knowledge/`，检索在 `tutoring/` | 看似省事，实际让 ADR-0002 的「检索层」失去单一归属 |

**决定性依据：解析流水线有第二个消费者，而且不是 M3。**
`docs/team-plan.md:53` 把「课件上传」列为 **M6** 的 S1 交付，
`docs/team-plan.md:59` 的首版验收写「教师上传 PDF → **查看解析状态**」。
`docs/code-standards.md:82` 又要求解析走 202 + jobId 的异步任务形态。
也就是说，除了 M3 的检索，**M6 还要调用「解析并返回状态」**。

一个被两个域调用的流水线如果放在调用方之一里面，会让另一方产生反向依赖，
并违反 `docs/code-standards.md:33`「跨领域走公开服务函数或事件，不直接写其他模块的表」。
方案 A 让这条公开函数有明确的归属方（M3），与方案 B 相比只多一层目录。

**已知代价（如实保留）**：M3 同时是 `tutoring/` 与 `knowledge/` 的 owner，
所以在本项目里这条「跨领域」界限**不产生任何评审分离**——两个域都由 M3 一个人负责，
`docs/adr/0002-model-adapter.md:92-95` 记过同类问题（方案 B 使 CODEOWNERS 归单人）。
本 ADR 不假装这层划分带来了治理收益，它的收益是**职责与依赖方向**，不是评审人数。

### 2. PDF 解析库：`pypdf`

**决策：`pypdf`，兼容范围 `pypdf>=6.19,<7`。**

2026-09-20 实际下载 `pypdf-6.19.0-py3-none-any.whl` 并读取其 `METADATA`：

| 核对项 | 实际值 |
| --- | --- |
| 版本 | `6.19.0` |
| 许可证 | `License-Expression: BSD-3-Clause` |
| Python 要求 | `Requires-Python: >=3.9`（本项目 3.12，满足） |
| 必装传递依赖 | **无**。唯一的 `Requires-Dist` 是 `typing_extensions`，条件为 `python_version < '3.11'`，本项目不触发 |
| wheel 形态 | `py3-none-any`（纯 Python，CI 无需编译） |

`cryptography` / `Pillow` 等只出现在 `extra` 中（处理加密件、图片），本项目不需要，不安装。

被否掉的两个方案（同样实际下载元数据核对）：

| 方案 | 实际元数据 | 否掉的理由 |
| --- | --- | --- |
| `pdfplumber` 0.11.10 | 必装依赖 `pdfminer.six==20260107`（**精确钉死**）、`Pillow>=12.2.0`、`pypdfium2>=5.9.0`；元数据中**没有**机器可读的 `License` 字段 | 为 S1 引入 3 个必装传递依赖，其中 2 个是二进制扩展；且 `pdfminer.six` 精确钉死会与 C7 的锁文件评审叠加复杂度。取字质量更好，但 S1 的语料是自撰讲义（见第 7 节），版式简单，用不上这个优势 |
| `PyMuPDF` 1.28.2 | `License: Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`；wheel 为 `cp310-abi3-win_amd64` | **AGPL-3.0 是 copyleft**，公开仓库使用会牵扯开源义务，对课程项目是实打实的许可风险；且是平台相关二进制 wheel |

**一条更正**：本文起草时曾口头把 `pypdf` 的许可证说成 MIT，**实际是 BSD-3-Clause**。
两者都是宽松许可、都无 copyleft 义务，结论不变，但以本节实测值为准。

**依赖变更的流程归属（C7/C8）**：把 `pypdf` 写进 `apps/api/pyproject.toml` 会改动**共享锁文件**
`apps/api/uv.lock`，而 `docs/adr/0001-platform-bootstrap.md:15` 要求依赖升级单独评审锁文件变化、
`docs/team-plan.md:27` 要求锁文件变更先通知负责人。因此**本 ADR 只提出选型，不改任何依赖**；
实际的 `uv add` 与 `uv.lock` 变更放在实施 PR 中，并在 PR 说明里显式 @ M1。

### 3. 检索结果用哪个类型返回

**决策：`knowledge` 返回自己的 `RetrievedPassage`（含检索得分），由 `tutoring` 的服务层映射成 `RetrievedChunk`。**

| 方案 | 依赖方向 | 取舍 |
| --- | --- | --- |
| i `knowledge` import `tutoring` 的 `RetrievedChunk` | 生产者 → 消费者（**反向**） | 检索层反过来依赖答疑层，与方案 A 的划分矛盾 |
| ii 把 `RetrievedChunk` 搬到 `knowledge` | 消费者 → 生产者（正确） | 要改动**已合并**的 `base.py` 与 ADR-0002 的接口章节，属 C12 范围的公共接口变更 |
| **iii 各自持有，服务层映射（已采用）** | 消费者 → 生产者（正确） | 多一个类型；但映射本身有语义（见下） |

选 iii 而不是 ii，理由不只是「少动合并代码」：**两者的字段本来就不同**。
检索命中需要携带**得分**用于排序、阈值与调试；而 `ModelRequest.retrievedChunks` 的字段清单由
ADR-0002 固定，**不含得分**——把检索得分传给模型是噪音，也违反「adapter 只接收」的窄接口立场。
因此 `RetrievedPassage → RetrievedChunk` 是一次**有意义的裁剪**（丢掉得分、只留模型需要的四字段），
是一个真实的边界，而非为了解耦而解耦。

**副作用（正向）**：本 ADR **不需要**修改 `base.py` 或 ADR-0002 已合并的任何内容，
因此不触发 C12 描述的公共接口变更流程。

### 4. 中文检索的切分单位

**决策：CJK 按字符二元组（bigram），拉丁字母与数字按小写整体切词；不引入分词依赖。**

理由：`docs/code-standards.md:103` 要求必需 CI 使用固定数据，
`docs/adr/0002-model-adapter.md:182` 已为 Mock 立下「相同输入 ⇒ 逐字节相同输出」的确定性规则，
检索层沿用同一标准。bigram 完全确定性、零下载、零依赖，而 `jieba` 要额外依赖 + 词典包，
且其分词结果随词典版本变化，会让「同一次查询在不同环境返回不同结果」。
`docs/tasks/m3.md` 与既有讨论把本项定为**关键词检索**（非向量检索），bigram 与之相符。

**如实说明代价**：bigram 对英文术语、公式符号、跨词长距离匹配的效果弱于向量检索或分词器。
若 S1 的 30 条评测（`docs/requirements.md:33`）显示召回不足，升级路径是明确的：
先换分词器，再考虑 pgvector（`docs/code-standards.md:3` 已预留该选项）。
**本 ADR 不预先为 S2 的升级做抽象**，避免为未验证的需求增加层次。

### 5. 切片是否允许跨页

**决策：不允许。一个切片必须完整落在一页之内。**

`tutoring-response.md:107` 要求 `pageNumber ≥ 1` 且可定位。若一个切片横跨第 3、4 页，
它的 `pageNumber` 只能二选一，而**无论选哪个，都会出现「用户翻到该页却找不到支持该结论的原文」**，
直接违反 `docs/tasks/m3.md:29` 的验收证据「授权引用**可追溯**」。

代价：切片边界受页边界约束，可能把一句话切开，略微影响召回。
这是**正确性优先于召回**的取舍，且可通过页内重叠缓解（见「接口」，重叠量由评测调参）。

### 6. 无文字页必须显式报告

扫描件提取不出文字时，`pypdf` 会返回空字符串——**这本身不是错误**，
若静默丢弃，整份扫描课件会表现为「没有依据」，看起来像检索坏了。

**决策：解析结果按页返回「有无文字」标记，并给出统计；空页不静默丢弃。**
OCR 属 S2（C11），S1 的职责是**如实报告「这一页没有可提取文字」**，
不得把它伪装成「这一页不存在」或「检索无结果」。

### 7. S1 不做持久化

`apps/api/migrations/` **不存在**，`docs/adr/0001-platform-bootstrap.md:11` 记明数据库「尚未安装或启动」，
`docs/team-plan.md:24` 把迁移划给 M5。因此 S1 **不使用数据库**，索引驻留内存，
在启动时从一份固定语料构建。

**这条决定带来一个必须上报的缺口，如实写明**：
`docs/team-plan.md:59` 的 S1 验收流程是「教师上传 PDF → 查看解析状态 → 学生选章节并提问」，
其中**「上传」这一半需要存储**。M3 的 S1 交付物是**解析/切分/检索这条函数链**，
它可被验证（用测试 + 启动时从磁盘读入的固定语料），
但**「教师上传后能被学生检索到」无法在 S1 端到端演示**，
除非 M1/M5 先落地存储与授权表。**这需要与 M1、M5、M6 在 Issue 中明确，不能默认由 M3 补上。**

### 8. 语料从哪来

C6 禁止把真实教材提交进仓库，`docs/requirements.md:34` 要求「真实模型评测在受控环境执行」、
`docs/code-standards.md:107` 要求测试资料为合成或已获许可材料。因此：

- **测试与 CI 语料**：由测试辅助代码**生成** PDF（`pypdf` 同时具备写入能力，
  见第 2 节的纯 Python 特性），不往仓库提交任何 PDF 二进制文件。
  好处：无许可问题、无二进制 diff、内容随测试用例可读可审。
  （`.gitattributes` 已把 `*.pdf` 标为 `binary`——仓库已预料到 PDF 的存在，
  但它只保证「万一提交了不可 diff」，不解决许可问题，所以仍以生成为准。）
- **演示语料**：需要一份自撰或已获许可的高数讲义。`.gitignore` 已有 `uploads/` 一行，
  说明本地素材不入库的约定已存在。**谁负责产出这份演示讲义尚未认领**，
  它与「授权文档表」（空位二）一起列入「待确认事项」。

## 决策、影响与接口变化

### 接口草图（规范字段清单，**不是代码**）

沿用 ADR-0002 的做法：不给进程内类型配 JSON Schema
（理由同 `docs/adr/0002-model-adapter.md:97-103`，此处不重复）。

```python
# knowledge —— 解析与索引（写入侧）
def build_index(source: SourceDocument) -> IngestReport: ...

# knowledge —— 检索（读取侧）
def search(request: SearchRequest) -> Sequence[RetrievedPassage]: ...
```

| 类型 | 字段 | 说明 |
| --- | --- | --- |
| `SourceDocument` | `document_id`、`title`、`content: bytes` | `document_id` 前缀 `doc_`（`platform/README.md:24`）；`title` 是**不可信输入**（C10） |
| `IngestReport` | `document_id`、`page_count`、`pages_without_text: Sequence[int]`、`passage_count` | `pages_without_text` 即第 6 节的显式报告；页码为 1 基 |
| `SearchRequest` | `query`、`authorized_document_ids`、`top_k` | `authorized_document_ids` 是**唯一的范围边界**（C2），检索层不校验它怎么来的 |
| `RetrievedPassage` | `document_id`、`document_title`、`page_number`、`text`、`score` | 比 `RetrievedChunk` 多一个 `score`，第 3 节说明为何不合并两者 |

### 规范性不变量（应由测试拦截）

1. `page_number ≥ 1`，且切片不跨页（第 5 节）。
2. 相同 `SourceDocument` ⇒ 逐字节相同的 `IngestReport` 与切片序列。
3. 相同 `SearchRequest` ⇒ 相同顺序的 `RetrievedPassage` 序列；
   并列得分按 `(document_id, page_number, 页内序号)` 稳定排序，不依赖字典/集合遍历顺序。
4. `search` 返回的每一条，其 `document_id` 必属于 `request.authorized_document_ids`。
   **空集入参 ⇒ 空序列出参**，绝不返回未授权文档，也绝不「兜底」返回全库。
5. 不产生空文本切片。
6. `search` 无命中时返回**空序列**（不是 `None`，不抛异常）——
   这正是 `mock.py:100-103` 走「无依据」脚本的触发条件，也是 C4 的落点。

### 职责边界（与 ADR-0002 的表对齐，不重叠）

| 事项 | 归属 | 依据 |
| --- | --- | --- |
| 解析、切分、索引、检索、`hasEvidence` 的**判定依据** | **knowledge（本 ADR）** | `docs/adr/0002-model-adapter.md:45,49` |
| 「已授权文档集合」的**产出** | **未认领**（空位二） | `docs/adr/0002-model-adapter.md:329` |
| `RetrievedPassage` → `RetrievedChunk` 映射 | tutoring 服务层 | 第 3 节 |
| `citations` 白名单校验、越界引用丢弃 | tutoring 服务层 | `docs/adr/0002-model-adapter.md:44` |
| `hasEvidence` 写进响应与 C4 不变量的**强制** | tutoring 的 Pydantic validator | `tutoring-response.md:117-119` |
| 上传端点的 202 + jobId 形态（C9） | **上传方**（`docs/team-plan.md:53` 指向 M6） | `docs/code-standards.md:82` |
| OCR、PPTX | S2 | C11 |

**两条要特别点明，因为它们最容易在实现时被悄悄合并**：

- **检索层的过滤与 tutoring 的白名单校验是两道不同的闸门，都要保留。**
  前者过滤「模型看到了什么」，后者过滤「模型声称引用了什么」。
  只留前者会漏掉模型凭空编造 `c1` 的情况；只留后者会把未授权文本喂给模型。
- **`hasEvidence` 的「判定」在检索层，「强制」在 tutoring。**
  检索层给出「有没有命中」这一事实，由 tutoring 的 validator 保证 C4 在响应上成立。

### 依赖与配置

- 唯一新增运行依赖：`pypdf`（第 2 节）。**本 ADR 不改 `pyproject.toml` 与 `uv.lock`**，
  实施 PR 中变更并单独说明锁文件 diff（C7）。
- 无新增环境变量、无新增密钥、无数据库、无外部网络调用。
- 检索不联网：CI 中检索路径与真实模型路径完全分离，符合 `docs/code-standards.md:103`。

## 验证、迁移与回滚

**本 ADR 无可执行代码，因此没有测试能验证它。** 这一点与 ADR-0002 等同：
`ruff` / `mypy` / `pytest` 不会读到本文件的任何内容，跑了也不构成对本 ADR 的验证。
唯一的验证方式是评审：目录归属、依赖选型、不变量是否够用、职责边界是否与 ADR-0002 自洽。

**本文件不是「解析已实现」的证据**（`AGENTS.md:8`）。截至 2026-09-20，
`apps/api/app/domains/knowledge/` 仍为空目录，仓库内**没有任何** PDF 解析代码。

**迁移**：无。不涉及数据库、不涉及已有数据结构。
**回滚**：本文件只新增一个 markdown，回滚即 `git revert` 该提交。

**合并后仍需注意**：ADR-0002 与 tutoring 契约都处于「提议 / 草案」状态
（`packages/contracts/tutoring/README.md:6-8` 写明「仍待 M4 / M5 评审确认。确认前不应据此编写生产代码」）。
PR #29 已合并的 adapter 实现事实上越过了这句话。**本 ADR 不重复该越线**，
但也不假装问题不存在：实施本 ADR 前，建议先推动 M4 / M5 对 tutoring 契约给出评审结论。

## 后续工作

以下均需**另开 Issue**，每个 Issue 一个 PR，每片建议 0.5—2 天（`CONTRIBUTING.md:11,39`）。
**本 ADR 不实施其中任何一项。**

| # | 切片 | 依赖 | 说明 |
| --- | --- | --- | --- |
| 1 | 解析：PDF → 每页文字（含 `pages_without_text`） | 无 | **最小、最独立，建议首片**。用生成的合成 PDF 做测试语料 |
| 2 | 切分：页文字 → 不跨页切片 | 1 | 纯计算，无 IO |
| 3 | 检索：`SearchRequest` → `RetrievedPassage`（bigram） | 2 | 含不变量 3、4、6 的测试 |
| 4 | 映射 + C4/C5 不变量：`RetrievedPassage` → `citations` | 3 | 接上 tutoring 已有的 `RetrievedChunk` 与 schema |
| 5 | 装配：把检索接进答疑链路，用 `MockModelClient` 跑通 | 4 | 端到端跑通「有依据 / 无依据」两条路径 |
| 6 | `ai/prompts/guided-tutoring.v1.md` 与提示词版本化 | 无 | `docs/tasks/m3.md:13`、`docs/adr/0002-model-adapter.md:298` |
| 7 | 30 条固定评测集（`ai/evaluations/`） | 5、6 | `docs/requirements.md:33`、`docs/tasks/m3.md:15` |
| — | `apps/api/app/domains/knowledge/README.md` | 无 | 可在第 1 片内顺带建立，参照 `analytics/README.md` 的占位写法 |

## 待确认事项

- [ ] M1 确认 `knowledge/` 的分层与「解析流水线有两个消费者（tutoring、M6 上传）」这一判断
- [ ] M1 确认 `pypdf` 选型与 `uv.lock` 变更的流程（C7/C8）
- [ ] M1 / M5 / M6 确认**授权文档表的归属方与产出时点**（空位二）——
      在此之前 C1 无法端到端演示
- [ ] M5 确认 `knowledge` 与 M5 的课程/章节（`docs/tasks/m3.md:23`）如何关联：
      `courseId` 是检索的收窄条件，其数据来源在 M5
- [ ] M6 确认上传端点（202 + jobId，C9）与 M3 的 `build_index` 之间的调用形态
- [ ] 团队确认 S1 **演示讲义 PDF** 的来源与许可（第 8 节）
- [ ] M4 / M5 对 tutoring 契约（`packages/contracts/tutoring/`）给出评审结论，
      解除「确认前不应据此编写生产代码」的前置条件
- [ ] 确认后由 M3 补充：切片长度的具体常量与页内重叠量（由 30 条评测调参决定，
      本 ADR 不预先给出数值）

**此清单未勾选即未确认，不以 AI 自评代替成员评审。**
