# 课堂持久化验收：步骤与待采证矩阵

关联 [#69](https://github.com/StephenYI43/software-engineering-group-1/issues/69)、[#70](https://github.com/StephenYI43/software-engineering-group-1/issues/70)。
owner：M2 / @Saber-www；执行依赖：M1（#48 环境与底座）、M5（#42 learning）、M3（#71）、M4（#72）、M6（#65）。
状态：**M2 已独立执行 #75 候选的平台子集验收；2026-10-21 在新临时实例复跑并固化 §8 完整编排、SQL 和结构输出。全域数据库验收未完成。未采集项仍写「未运行」，未实现页面另标「未实现 / 不适用」。**

## 0. 使用规则（违反任何一条，该条记录作废）

1. **没跑过就不填。** 未执行的写「未运行」，不写「应该通过」。
2. **一条一证据。** 每条至少给：执行的命令、原始输出里的关键行、环境登记号（见 §1）、commit。
   只写「已验证」不算证据。
3. **分层记录，不得混层。** 五层：`repository` / `API` / `UI` / `数据库约束` / `重启持久化`。
   例如「repository 写入成功」不能代替「接口返回 200」，也不能代替「重启后仍能读回」。
4. **Mock 模型可以，Mock 数据库不行。** 答疑可用 MockModelClient；验收数据库必须是真实 PostgreSQL。
   InMemory、SQLite、前端 fixture、同一连接内读回都不能证明持久化，也不能证明重启后仍在。
5. **前端临时态不持久化 ≠ 服务端不保存。** UI 不存草稿，不代表中断轮次、幂等键没有落库
   （见 `student.md` 第 3 节）；两个方向都要单独取证。
6. **破坏性操作只在临时库。** 降级、删卷、清表只在标注为临时的测试库执行，不碰保留卷。
7. **契约优先。** 期望值以领域已确认契约及定稿字典为准；已合入但待确认的学生事件见 `student.md` §2.3。契约与本文冲突时先改本文，
   不按「实现看起来对」写验收结论。

## 1. 环境登记（每次验收先登记，行内引用编号）

| 登记号 | 项                   | 值                                                                                                   | 采证方式                                                           |
| ------ | -------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| E1     | commit               | #75 `e1fb5ffdcbb94e1d54ab096f49c990ba3ab659c4` 隔离快照                                              | `git rev-parse HEAD`                                               |
| E1     | PostgreSQL 版本      | 17.11，macOS arm64 原生临时实例                                                                      | `SELECT version();`                                                |
| E1     | 镜像摘要             | 不适用；Maven Central Zonky 17.11.0 二进制，下载 SHA256 校验一致                                     | `docker image inspect --format '{{index .RepoDigests 0}}' <image>` |
| E1     | Alembic head         | `0001_platform`，单 head；check 无漂移                                                               | `alembic heads` / `alembic current`                                |
| E1     | Python / uv / 锁文件 | 3.12.14 / 0.12.13；uv.lock SHA256 `bc8ebe174c62aaa16535d821745628910f7a88aa1fb1c9674604ff47d549b31f` | `python -V`、`uv --version`、`uv.lock` 摘要                        |
| E1     | Node / pnpm          | 24.21.0 / 11.27.0                                                                                    | `node -v`、`pnpm -v`（应为 24.21.0 / 11.27.0）                     |
| E1     | 启动与 seed 入口     | #75 `uvicorn app.main:app` / `app.core.db.seed` / `scripts.verify_platform_persistence`              | M1 的唯一入口（compose 或脚本路径）                                |
| E1     | 数据卷名             | 不适用；专用临时 data 目录重启保留，独立 `m2_platform_restart_test` 库                               | 重启验收复用的卷                                                   |
| E1     | 执行人 / 时间        | M2，AI 辅助独立实跑；2026-10-20 Asia/Shanghai                                                        | —                                                                  |
| E2     | commit / PG / head   | 同 #75 `e1fb5ff`；PG 17.11；`0001_platform` 单 head                                                  | §8 的新实例升级、重启和只读查询                                    |
| E2     | 执行人 / 时间 / 范围 | M2，2026-10-21 Asia/Shanghai；新建独立临时 data 目录及合成 `_test` 库，仅平台子集                    | 脱敏输出、完整编排和结构快照均在 §8                                |

> 行内「环境」列统一写登记号（如 `E1`）。换环境就新建 E2，不复用编号。

## 2. 前置条件与阻塞判定

| #   | 前置                                                     | 不满足时的处置                             | 当前状态（2026-10-20）                                                             |
| --- | -------------------------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------- |
| P1  | M1 交付唯一 `Base`/`SessionFactory`/Alembic 单链（#48）  | 正式集成待双审；候选可验平台子集           | 候选已提交：#75 `e1fb5ff`（依赖 #73），待双审/合入；M2 已独立复跑平台子集，见 §2.1 |
| P2  | M5 的 learning 迁移并入同一迁移链（#42）                 | 相关步骤标「跳过（依赖未就绪）」           | 未就绪（#42 open，#60 未合并）                                                     |
| P3  | M3 答疑/知识库表（#71）                                  | 跳过 S7 及引用相关反例                     | #76 `b2eab6b` 九表设计草案待修订；尚无本域迁移；#62 为内存实现                     |
| P4  | M4 媒体/数字人表（#72）                                  | 跳过 S8                                    | 未就绪（#72 open，PR #61 未合并）                                                  |
| P5  | 字典检查通过（`node scripts/check-data-dictionary.mjs`） | 不做全域通过判定；不阻塞已迁移平台子集取证 | 本分支 student 局部 0 错误/16 提醒；全量 23 错误。#75/#76 候选联合检查见下文       |

> 前置未满足时，正确做法是在 Issue 里写明阻塞对象与已完成的 A 批内容，
> 不是用 InMemory 或手写建表「先跑一遍」。

### 2.1 当前取证与依赖快照（2026-10-20）

2026-10-20 首轮，本机 Node 24.21.0 / pnpm 11.27.0：检查器 69/69，前端 31/31，
`typecheck/lint/format:check/test/build` 全通过；属于静态/前端证据，不替代数据库项。
2026-10-21 检查器续审补同名 JSONB 列归属、JSON 键大小写及 SQL 字面值回归，总计 87/87；
同名列的缺项在全量模式会失败，不能再由另一张表的版本属性代为通过。
独立复核另发现表名与属性前缀碰撞会误判标题归属，补失败用例后修复；显式标题优先，原有异表冲突检查仍保留。
本轮前端 31/31，`typecheck/lint/format:check/test/build` 及两份 M2 文档的独立格式检查通过。
本分支局部仍为 0 错误/16 提醒，全量仍为 23 个缺文件/未登记引用错误；
只合并临时副本中的 #75/#76 候选再检查，仍为 16 表、2 个 courses 悬空 FK、11 项未验证、9 条提醒。
这两种非零结果继续作为依赖缺项证据，不伪装成全域通过。

M2 对 #75 `e1fb5ff` **独立下载源码快照**，未改提供方文件，用锁定依赖和本机真实 PostgreSQL 17.11 执行：

```text
uv sync --locked                        -> 成功
ruff format --check . / ruff check .    -> 通过
mypy                                    -> 23 source files，无问题
TEST_DATABASE_URL=<专用本机_test库> uv run --locked pytest -q
                                        -> 62 passed, 2 warnings, 96.01%, 9.47s；无跳过
alembic upgrade head / heads / check     -> 0001_platform 唯一head，无新升级操作
information_schema.columns 对平台字典   -> 7表49列名/类型/长度/精度/可空/默认一致
```

随后在另一个可丢弃的 `m2_platform_restart_test` 库，用提供方唯一迁移/seed/验证脚本取证：

```text
python -m scripts.verify_platform_persistence --phase write --state <临时文件> --api-url <本机API>
WRITE: 4 synthetic users, configs, session and audit committed; token not logged.
停止API子进程；pg_ctl -D <本次私有data目录> -l <日志> -o <相同host/port/socket> -w restart -m fast
重建API子进程；同一data目录、同一_test库
python -m scripts.verify_platform_persistence --phase read --state <同一临时文件> --api-url <同一本机API>
READ: same IDs/records after restart; revoked token rejected; bad password 401.
```

两阶段 API PID 不同（72068 → 72081）；PostgreSQL 确实停止再启动并保留数据目录。
最终 SQL 行数：users=4、user_profiles=4、roles=3、user_roles=4、auth_sessions=1、admin_audit_logs=6、system_config_versions=2。
已采集 `information_schema.columns`、`pg_constraint/pg_get_constraintdef`、`pg_indexes`；
初次取证时 S2 的 CHECK/UNIQUE/FK 尚未逐项对账；本轮物理约束续审结果及未决差异见 §2.2，不能因 Alembic 无漂移就标整项通过。
N9 的旧 token 拒绝由实际数据库会话解析验证；未接通的业务受保护 API 不在本次结论内。

原生二进制仅解包至临时目录，无系统服务安装；测试库只含合成数据，状态文件含合成 token，验证后已删除。
首轮重启探针因子进程日志管道超时而中止；随后又发现启动未复用临时端口。
修正日志重定向和显式 host/port/socket 后，在重新创建的专用测试库完整重跑成功；中止轮次不计通过。
本机未运行 Compose；#75 仍待双审/合入，本结果不代替 M5/M6 人工评审，也不代表各业务域已完成。

#76 九表草案已提交、待修订；联合 #75 平台字典、#76 `b2eab6b` 与学生映射实际登记 16 表，
只剩 courses 缺字典造成的 2 条真实悬空 FK，另有 11 项未验证、9 条提醒。没有实体重名/内部 FK 误报，未造占位表。
本分支未并入候选领域字典，全量仍 23 错误；按真实缺项报告，不接为必需绿灯。

### 2.2 S2 平台物理约束复核（2026-10-20 续审）

本次重新启动 E1 私有 PG17.11 实例，只读重新采集 `information_schema.columns`、
`pg_constraint/pg_get_constraintdef` 与 `pg_indexes`；采证后已关闭本次实例。来源仍为 #75 `e1fb5ff`。
7 表49列名、类型、长度/精度、可空和默认值继续一致；实际登记7个主键、8个外键、
4个UNIQUE约束、23个CHECK，另有2个部分唯一索引。以下按平台字典逐表复核，不扩大为服务层验收：

| 表                     | 已对账的物理约束/索引                                                                                | 差异或边界                                       |
| ---------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| users                  | id主键、username_key唯一、status索引；ID/status/时间/规范化名约束                                    | 字典的username范围未写明实际ASCII白名单，见D1    |
| user_profiles          | user_id主键/FK CASCADE；student_number可空唯一；展示名/学号长度约束                                  | major的非空长度等服务层语义不据物理类型宣称已验  |
| roles                  | code主键；student/teacher/admin枚举CHECK                                                             | 无新增物理差异                                   |
| user_roles             | 复合主键；3个FK及RESTRICT/SET NULL；角色查询索引；主角色部分唯一；撤销与时间CHECK                    | 至少一个有效主角色、授权人资格仍由服务层保证     |
| auth_sessions          | 主键；jti摘要唯一；2个FK RESTRICT；用户/到期索引；摘要/请求ID/有效期/撤销一致性CHECK                 | 认证/角色语义仍引用前次实际测试，不从FK推导权限  |
| admin_audit_logs       | 主键；actor FK SET NULL；actor/result/请求ID/JSON对象CHECK；三组索引                                 | details属性白名单与授权不是物理对象CHECK即可证明 |
| system_config_versions | 主键；key/version唯一；active部分唯一；creator FK SET NULL；正版本/状态/JSON版本与对象/激活时间CHECK | retired的activated_at限制未在字典写明，见D2      |

差异清单尚非空，S2 **不能标完整通过**；已在 #75 回报M1，未直接改提供方字典或DDL：

- D1：`ck_users_username_format` 实际为 `^[A-Za-z0-9_.-]{1,64}$`；字典仅写去首尾空白后长度1..64、无控制字符，未明确ASCII白名单。请M1使范围描述与实际限制一致，或明确另行修订实现。
- D2：`ck_system_config_versions_activation` 要求 draft 的 `activated_at` 为空，所有非draft状态（含retired）非空；字典仅写 draft为空、active非空，未说明retired。请M1明确从未发布的draft能否直接退役，再同步字典或约束；本文不替提供方决定。

### 2.3 本轮迁移范围登记与对账边界

执行前记录「本轮已迁移表/列清单、对应领域字典、迁移 revision」；未登记实际范围，不执行 S2 的通过判定。
S2 只核对这份**已迁移范围**的表、列及约束，并独立列出该范围内的缺项或额外项。
领域字典中仅作设计保留、后续阶段或候选的表列另列为「设计保留 / 未迁移」，不算本轮数据库缺陷，
也不能因此宣称整份字典已实现。尚未定稿的字段、跨域外键和 JSONB 版本策略须记录 owner 与恢复条件。

各 S/N 项只在其所属迁移和接口已交付时执行；S1—S3 可覆盖先落地的平台子集，
不能据此对未迁移的 learning、tutoring、media、analytics 给出完成结论。

## 3. 主流程矩阵（S 系列）

| #   | 验收项               | 层级         | 命令 / 操作                                                                                             | 期望（契约依据）                                                                                         | 环境  | 结果                                                            | SQL/证据位置                    | 状态                   |
| --- | -------------------- | ------------ | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ----- | --------------------------------------------------------------- | ------------------------------- | ---------------------- |
| S1  | 空库升级             | `数据库约束` | 空开发库 `alembic upgrade head`；`alembic heads`                                                        | 升级成功；只有一行 head                                                                                  | E1/E2 | 成功；单 head 0001_platform                                     | §2.1 / §8 实跑记录              | 平台候选通过           |
| S2  | 表/列/约束与字典一致 | `数据库约束` | 按本轮已迁移清单查 `information_schema.columns`、`pg_constraint`，逐项对账                              | 已迁移范围内表数、列名、可空、默认、CHECK/UNIQUE/FK 与定稿字典一致；范围内差异为空；设计保留另列         | E1/E2 | 7表49列、42约束、20索引两次结构一致；含2部分唯一；D1/D2待M1确认 | §2.2 / §8 完整结构输出          | 差异待确认，未完整通过 |
| S3  | 合成 seed 幂等       | `repository` | seed 连续执行两次，比较行数与主键集合                                                                   | 两次行数相同、主键不变；无重复账号/课程/班级                                                             | E1/E2 | 两次 seed；用户4/角色3/配置2，ID不变                            | §2.1 +62项实跑 / §8             | 平台候选通过           |
| S4  | 课程与选课隔离       | `API`        | 建课程 + 两班；学生 A/B 分别选课；互相请求对方班级数据                                                  | A 只看到自己班；跨班请求 404（防枚举），不是 403 也不是 200                                              | E1    | 未运行                                                          | 请求/响应 + 状态码              | 未运行                 |
| S5  | 作业发布与提交       | `API`        | 教师发客观题与主观题；学生 A 提交                                                                       | 客观题即时判分（`gradedBy=auto`）；主观题 `isCorrect/score` 为 null；学生响应中**没有 `answerKey` 字段** | E1    | 未运行                                                          | 响应体片段                      | 未运行                 |
| S6  | 错题只收录一次       | `repository` | 批阅主观题为错误；重复批阅同一提交                                                                      | 首次 `null→false` 生成一条错题；重复批阅不新增；`resolved` 不删除记录                                    | E1    | 未运行                                                          | `SELECT count(*) FROM mistakes` | 未运行                 |
| S7  | 一轮 Mock 答疑       | `API`        | 走 M3 的 Mock 路径完成一轮（`isMock=true`）                                                             | 按 M3 定稿且已迁移的会话/轮次/引用模型对账；引用可追溯；wire 的 `isMock=true` 与存储映射一致             | E1    | 未运行                                                          | 已迁移表联查 SQL                | 未运行                 |
| S8  | 数字人配置与媒体任务 | `repository` | 写入一次播报记录或媒体任务（M4 表）                                                                     | 记录可读；文件内容与元数据分开存；不含密钥明文                                                           | E1    | 未运行                                                          | 表查询结果                      | 未运行                 |
| S9  | 教师统计读取         | `API`        | 触发一次班级统计（M6）                                                                                  | 「无活动」是已知 0，「无法判断」不被写成 0；`consumption.dataState` 与水位可见                           | E1    | 未运行                                                          | 响应 JSON                       | 未运行                 |
| S10 | 管理动作与审计同事务 | `repository` | 执行一次管理动作（如禁用账号），再制造一次失败                                                          | 成功：业务变更与 `admin_audit_logs` 同时存在；失败：两者都不留痕                                         | E1    | 未运行                                                          | 事务前后两表计数                | 未运行                 |
| S11 | 重启后读回           | `重启持久化` | 提交后关闭 Session；重启 API；重启 PostgreSQL 容器或原生进程（**保留卷/同一data目录**）；重新查询原记录 | 记录仍在、主键不变、关键字段不变；会话撤销仍生效                                                         | E1/E2 | 平台用户/配置/会话/审计同ID；其余域未运行                       | §2.1 / §8 write/read 输出       | 仅平台范围通过         |
| S12 | 学生端 UI 走真实接口 | `UI`         | 关闭 Mock，走课程→章节→答疑                                                                             | 页面无「示意数据」标识；network 显示真实 200/SSE；失败态不显示伪造答案                                   | E1    | 未运行                                                          | 截图 + network 导出             | 未运行                 |
| S13 | 中断轮次落库         | `repository` | 发起一轮后点停止；再制造一次连接断开                                                                    | 按 M3 定稿映射保持 `isComplete=false` 且阶段不推进；内部状态、断连原因与正文处理按 Q8；未定稿不判通过    | E1    | 未运行                                                          | 轮次表查询 + 阶段字段           | 未运行                 |

## 4. 反例矩阵（N 系列，必须被拒绝）

| #   | 反例             | 层级                 | 注入方式                                                                    | 期望                                                                                                 | 环境  | 结果                                                                | 证据位置            | 状态           |
| --- | ---------------- | -------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----- | ------------------------------------------------------------------- | ------------------- | -------------- |
| N1  | 同一提交重复写入 | `API`                | 同一 `idempotencyKey` 连发两次                                              | 只一条 `submissions` 行；第二次返回首次记录（200）                                                   | E1    | 未运行                                                              | 两次响应 + 行数     | 未运行         |
| N2  | 不同键二次提交   | `API`                | 同一作业换新键再 POST                                                       | 409 `SUBMISSION_ALREADY_EXISTS`，不新增行                                                            | E1    | 未运行                                                              | 响应体              | 未运行         |
| N3  | 失败事务无残留   | `repository`         | 事务内制造约束冲突后回滚                                                    | 业务表与事件表都没有半条记录                                                                         | E1    | 未运行                                                              | 回滚前后计数        | 未运行         |
| N4  | 越权读取         | `API`                | 学生 B 请求 A 的提交/计划/错题                                              | 404（防枚举），不是 200/403/500                                                                      | E1    | 未运行                                                              | 状态码              | 未运行         |
| N5  | 角色越界         | `API`                | 学生调用发布作业/批阅端点                                                   | 403 `FORBIDDEN_ROLE`                                                                                 | E1    | 未运行                                                              | 响应体              | 未运行         |
| N6  | 跨班串数据       | `API` / `repository` | 同一学生加入同课程的两个班，分别经 API / repository 按班查询                | 只返回该班授权范围内数据；若模型不足以区分，记录为阻塞，不用数据库约束通过替代按班查询证据           | E1    | 未运行                                                              | 查询结果            | 未运行         |
| N7  | 坏数据落库       | `数据库约束`         | 直接 SQL 插入违反 FK/UNIQUE/CHECK 的行                                      | 数据库拒绝并报约束名；不得先删约束再重试                                                             | E1    | 未运行                                                              | 报错文本            | 未运行         |
| N8  | 事件乱序/迟到    | `repository`         | 事务 A 先取号后提交、B 后取号先提交                                         | M6 按 #65/M5 最终消费方案不永久漏算、不重复统计；ingestion 游标尚待确认，自增取号不视为提交顺序保证  | E1    | 未运行                                                              | 消费账本查询        | 未运行         |
| N9  | 撤销会话后重启   | `重启持久化`         | 登出后重启 API/PG，用旧 token 请求                                          | 仍被拒绝；库中只有 jti 摘要，无原始 token                                                            | E1/E2 | 重启后 authority.parse 旧token为None；摘要存储；受保护业务API未接通 | §2.1 +62项实跑 / §8 | 平台会话层通过 |
| N10 | JSONB 版本不匹配 | `API` / `repository` | 按领域定稿方案注入缺失/未知版本或与版本不符的 `details`/`answer`/`question` | 按定稿规则拒绝、兼容读取或降级；允许外置版本元数据与对应规则，不强加现有 wire 的内部 `schemaVersion` | E1    | 未运行                                                              | 报错或读取结果      | 未运行         |

## 5. 学生端（M2）可先自查的部分

这些检查不依赖数据库，但须区分已有 fixture 页面、尚未合入的 SSE 客户端、以及未实现的业务页面。
同样**跑了才勾**，且不能替代 S12。若另在 #68 分支采证，必须记录该分支 head，不能冒充 #70 工作区已有实现。

| #   | 检查                 | 层级  | 方式                                      | 期望                                                                | 结果   | 状态                            |
| --- | -------------------- | ----- | ----------------------------------------- | ------------------------------------------------------------------- | ------ | ------------------------------- |
| F1  | 无持久化偏好         | `UI`  | 全仓搜 `localStorage`/`sessionStorage`    | 学生端无业务偏好写入                                                | 未运行 | 未运行                          |
| F2  | Mock 有显式标识      | `UI`  | 页面渲染检查                              | 有「示意数据」标识；`isMock` 轮次有提示                             | 未运行 | 未运行                          |
| F3  | 生产构建移除演示数据 | `UI`  | `pnpm build` 后检查产物                   | 演示轮次与 `?mock=` 开关不进生产包                                  | 未运行 | 未运行                          |
| F4  | 幂等键生命周期       | `UI`  | 对已实现的作业表单 / 章节正文页审阅并测试 | 表单会话内复用；成功结束键；浏览动作刷新才换新键                    | 未运行 | 未实现 / 当前不适用             |
| F5  | 不伪造完成态         | `UI`  | SSE 页面合入后断网 / 中断体验             | 半截回答标「未完成」；失败不显示伪造答案；未完成轮不渲染引用 / 追问 | 未运行 | SSE 页面未合入 / 当前不适用     |
| F6  | 禁止字段不上送       | `API` | 对已实现的答疑 / 作业请求逐项采集请求体   | 学生请求不传 `stage` / `isCorrect` / `gradedBy` / `answerKey`       | 未运行 | 对应请求通路未实现 / 当前不适用 |

N6 的权限与按班过滤由 API / repository 证明，FK/CHECK 通过不能替代它。
N10 只有在领域定稿明确要求数据库 CHECK 时才另采数据库拒绝证据；未定稿前标阻塞，
不能通过擅自向事件 payload 或其他现有 JSON 请求添加版本属性来让测试通过。

## 6. 未完成项（滚动更新，写明 owner 与恢复条件）

| 项                       | owner      | 阻塞原因                                                                 | 恢复条件                                                          |
| ------------------------ | ---------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| 平台七表字典与迁移       | M1         | #75 e1fb5ff 已交候选并经 M2 独立取证；#73/#75 待双审/合入，S2 D1/D2 未决 | M1 裁定差异并同步字典/约束，再复核和合入                          |
| learning 域七要素与迁移  | M5         | #42 未交付，#60 未合并                                                   | 迁移并入单链                                                      |
| 答疑/知识库字典          | M3         | #76 b2eab6b 九表草案已交，Q8/会话创建等待修订；本域迁移未提交            | 草案确认后按唯一迁移链交付并提供真实入口                          |
| 数字人/媒体字典          | M4         | #72 未交付                                                               | 字典 + 表                                                         |
| 分析/后台字典            | M6         | #65 未交付                                                               | 字典 + 表                                                         |
| 学生端映射与检查器       | M2         | A 批续修已提交待 M1/M5 复审；平台 E1/E2 已运行，全域 B 仍受领域交付阻塞  | 先复审 A；各域入口可用后逐项恢复，不等待全域齐备才验证已交子集    |
| 中断轮次正文存储口径     | M3         | Q8 未定                                                                  | M3 在 `tutoring-knowledge.md` 定稿                                |
| 身份/课程 ACL 与选课入口 | M1/M5      | #16/#47 路径、schema 与真实权限服务未交付；Q1 表归属已明确               | M5 交公开关系 service，M1 交身份/角色/资源隔离端点                |
| 保存答疑建议             | M3/M5      | #67 正式响应与授权取用未落地                                             | M3 定稿并提供归属校验，M5 按 sourceTurnId 取用保存，M2 消费确认   |
| 学生作业编辑与题目选项   | M5         | #42 学生编辑提交、重新判分语义与公开选项未定义；计划项 PATCH 已有定义    | 在现有契约补 schema/样例及真实实现，M2 复核                       |
| 章节事件接收与真实摄取   | M1/M5/M6   | #56 待 M1/M6 明确确认、HTTP 路径未定；#65 迟到提交/班级归属待定          | 沿现有线程确认并交可运行入口，按 N6/N8 取证                       |
| 学生个人报告             | M1/M6      | 需求正文与详细契约的 S1/S2 范围口径需确认；现有教师统计不供学生使用      | 先定阶段及仅本人可读契约，再安排 M2 接入                          |
| 学生完整浏览器闭环       | M2及提供方 | 当前 #70 优先；#64/#68 尚待评审合入，身份/学习 API 未齐                  | 当前任务收口后按 #3 拆课程→章节→答疑→引用/计划接线及键盘/E2E 验收 |

## 7. 一次验收的记录模板（按时间倒序追加在下方）

```text
### 验收记录 YYYY-MM-DD（环境 E1）
- commit / PG 版本 / alembic head：
- 执行人 / 运行位置（本机 / CI / 容器）：
- 执行的命令（原样粘贴）：
- 关键输出（行数、约束名、主键、状态码）：
- 未通过项与原因：
- 同一命令再跑一次的差异：
```

## 8. E2 可复现证据包（2026-10-21）

来源为 [#75 精确源码 e1fb5ff](https://github.com/StephenYI43/software-engineering-group-1/tree/e1fb5ffdcbb94e1d54ab096f49c990ba3ab659c4)，
本轮重新初始化临时 PG17.11 实例、空合成库并执行唯一迁移。没有复用 E1 数据或建立替代业务表。
以下完整编排与查询取代仅有私有临时路径的描述；本文件入库后可由 PR commit 稳定引用。

### 8.1 复跑方式与实际关键输出

在上述精确源码的 `apps/api` 运行下列代码；须已安装该快照要求的 Python/uv，
并使 PostgreSQL 17.11 的 `initdb`、`pg_ctl`、`postgres` 位于 PATH；也可用 `M2_PG_BIN` 指向其 bin 目录。
代码自动选择本机端口、新建临时 data 与 `_test` 库，先停 API，再重启保留 data 的 PG，最后重建 API。
结束时关闭实例并移除含合成 token 的状态文件；保留目录中仅供本机复核的合成数据、结构快照及日志。
提供方两阶段验证模块的 [完整源码](https://github.com/StephenYI43/software-engineering-group-1/blob/e1fb5ffdcbb94e1d54ab096f49c990ba3ab659c4/apps/api/scripts/verify_platform_persistence.py) 随相同 commit 固定。

```text
alembic-heads: 0001_platform (head)
alembic-current: 0001_platform (head)
alembic-check: No new upgrade operations detected.
write: WRITE: 4 synthetic users, configs, session and audit committed; token not logged.
pg-restart: server stopped / server started
read: READ: same IDs/records after restart; revoked token rejected; bad password 401.
API PIDs: [7079, 7095]; 7 tables / 49 columns / 42 constraints
counts={"admin_audit_logs":6,"auth_sessions":1,"roles":3,"system_config_versions":2,"user_profiles":4,"user_roles":4,"users":4}
pg-stop: server stopped
```

已逐项比较 E1/E2 的全部列属性、约束定义与索引定义，结构完全一致；本轮未重复执行 E1 的 62 项 pytest。
S2 的 D1/D2 仍存在，未将平台全部约束语义或业务权限标为通过。

<details>
<summary>完整编排（可复制执行；脚本内容 SHA256：4aa3fd922412e3ae2dde30044a511df418a7077594f80cf279248ccff0a26146）</summary>

```bash
uv sync --locked
uv run --locked python - <<'PY'
"""Run from #75 e1fb5ff apps/api after uv sync --locked; PostgreSQL 17.11 required."""

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import psycopg
from psycopg.rows import dict_row


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


pg_bin = Path(os.environ.get("M2_PG_BIN", shutil.which("pg_ctl") or "")).parent
if "M2_PG_BIN" in os.environ:
    pg_bin = Path(os.environ["M2_PG_BIN"])
version = subprocess.check_output([str(pg_bin / "postgres"), "--version"], text=True)
assert "17.11" in version, version
work = Path(tempfile.mkdtemp(prefix="m2-platform-proof-"))
print(f"Evidence directory: {work}", flush=True)
pg_port, http_port = free_port(), free_port()
db_name = "m2_platform_evidence_20261021_test"
env = {
    **os.environ,
    "APP_ENV": "development",
    "DATABASE_URL": f"postgresql+psycopg://m2_test@127.0.0.1:{pg_port}/{db_name}",
}
api_url = f"http://127.0.0.1:{http_port}"
pg_options = f"-h 127.0.0.1 -p {pg_port} -k {work}"
state = work / "state.json"
api_process = None
api_log = None
pg_started = False


def run(label, command):
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=90)
    (work / f"{label}.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    print(f"{label}: {result.stdout.strip()}", flush=True)


def stop_api():
    global api_process, api_log
    if api_process is not None:
        api_process.terminate()
        try:
            api_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api_process.kill()
            api_process.wait(timeout=10)
        api_process = None
    if api_log is not None:
        api_log.close()
        api_log = None


try:
    run("initdb", [str(pg_bin / "initdb"), "-D", str(work / "data"), "-U", "m2_test", "-A", "trust", "--encoding=UTF8", "--no-locale"])
    run("pg-start", [str(pg_bin / "pg_ctl"), "-D", str(work / "data"), "-l", str(work / "pg.log"), "-o", pg_options, "-w", "start"])
    pg_started = True
    with psycopg.connect(host="127.0.0.1", port=pg_port, user="m2_test", dbname="postgres", autocommit=True) as connection:
        connection.execute(f"CREATE DATABASE {db_name}")
    for command in ("upgrade head", "heads", "current", "check"):
        run("alembic-" + command.replace(" ", "-"), [sys.executable, "-m", "alembic", *command.split()])
    api_pids = []
    for phase in ("write", "read"):
        api_log = (work / f"api-{phase}.log").open("w")
        api_process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(http_port)], env=env, stdout=api_log, stderr=subprocess.STDOUT)
        api_pids.append(api_process.pid)
        for attempt in range(100):
            try:
                with urllib.request.urlopen(api_url + "/api/v1/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                if api_process.poll() is not None:
                    raise RuntimeError(f"API {phase} exited; see api-{phase}.log")
                time.sleep(0.1)
        else:
            raise RuntimeError(f"API {phase} did not become ready")
        run(phase, [sys.executable, "-m", "scripts.verify_platform_persistence", "--phase", phase, "--state", str(state), "--api-url", api_url])
        stop_api()
        if phase == "write":
            run("pg-restart", [str(pg_bin / "pg_ctl"), "-D", str(work / "data"), "-l", str(work / "pg.log"), "-o", pg_options, "-w", "restart", "-m", "fast"])
    assert api_pids[0] != api_pids[1]
    queries = {
        "columns": "SELECT table_name,column_name,data_type,character_maximum_length,datetime_precision,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name<>'alembic_version' ORDER BY table_name,ordinal_position",
        "constraints": "SELECT t.relname AS table_name,con.conname,con.contype,pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND t.relname<>'alembic_version' ORDER BY t.relname,con.conname",
        "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename,indexname",
    }
    with psycopg.connect(host="127.0.0.1", port=pg_port, user="m2_test", dbname=db_name, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        snapshot = {name: connection.execute(sql).fetchall() for name, sql in queries.items()}
        tables = sorted({row["table_name"] for row in snapshot["columns"]})
        assert len(tables) == 7 and len(snapshot["columns"]) == 49
        assert len(snapshot["constraints"]) == 42
        assert all(re.fullmatch(r"[a-z_]+", table) for table in tables)
        snapshot["counts"] = {table: connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] for table in tables}
        snapshot["version"] = connection.execute("SELECT version() AS version").fetchone()["version"]
    expected_counts = {"users": 4, "user_profiles": 4, "roles": 3, "user_roles": 4, "auth_sessions": 1, "admin_audit_logs": 6, "system_config_versions": 2}
    assert snapshot["counts"] == expected_counts
    (work / "schema.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    (work / "queries.json").write_text(json.dumps(queries, ensure_ascii=False, indent=2))
    print(f"API PIDs: {api_pids}; 7 tables / 49 columns / 42 constraints; counts={snapshot['counts']}", flush=True)
finally:
    stop_api()
    state.unlink(missing_ok=True)
    if pg_started:
        run("pg-stop", [str(pg_bin / "pg_ctl"), "-D", str(work / "data"), "-w", "stop", "-m", "fast"])
PY
```

</details>

### 8.2 实际执行的只读 SQL

以下为编排中采集结构的三条完整查询；查询事务设置为只读。`alembic_version` 为工具表，单独由迁移 head 核验，
不计入七张平台业务/管理表。`pg_constraint` 的 42 项为 7 PK、8 FK、4 UNIQUE、23 CHECK；
20 个索引中有 2 个部分唯一索引，完整定义见下方。

```sql
BEGIN READ ONLY;
-- columns
SELECT table_name,column_name,data_type,character_maximum_length,datetime_precision,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name<>'alembic_version' ORDER BY table_name,ordinal_position;

-- constraints
SELECT t.relname AS table_name,con.conname,con.contype,pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND t.relname<>'alembic_version' ORDER BY t.relname,con.conname;

-- indexes
SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename,indexname;
COMMIT;
```

### 8.3 完整脱敏结构输出

下面只含列/约束/索引定义，不含账号资料、正文、token、数据库 URL 或本机私有路径。
列默认值 `-` 代表数据库没有显式默认值，其他值保留 PostgreSQL 原始表达式；不将 SQL NULL 与字符串混为一谈。

<details>
<summary>49 列、42 个约束、20 个索引的逐项结果（TSV）</summary>

```text
# Columns: table, column, type, maxLength, datetimePrecision, nullable, default
admin_audit_logs	id	character varying	64	-	NO	-
admin_audit_logs	actor_user_id	character varying	64	-	YES	-
admin_audit_logs	actor_type	character varying	16	-	NO	'user'::character varying
admin_audit_logs	action	character varying	64	-	NO	-
admin_audit_logs	target_type	character varying	64	-	NO	-
admin_audit_logs	target_id	character varying	64	-	YES	-
admin_audit_logs	result	character varying	16	-	NO	-
admin_audit_logs	request_id	character varying	36	-	NO	-
admin_audit_logs	details	jsonb	-	-	NO	'{}'::jsonb
admin_audit_logs	occurred_at	timestamp with time zone	-	6	NO	now()
auth_sessions	id	character varying	64	-	NO	-
auth_sessions	jti_digest	character varying	64	-	NO	-
auth_sessions	user_id	character varying	64	-	NO	-
auth_sessions	role_code	character varying	16	-	NO	-
auth_sessions	issued_at	timestamp with time zone	-	6	NO	-
auth_sessions	expires_at	timestamp with time zone	-	6	NO	-
auth_sessions	revoked_at	timestamp with time zone	-	6	YES	-
auth_sessions	revoke_reason	character varying	32	-	YES	-
auth_sessions	request_id	character varying	36	-	NO	-
roles	code	character varying	16	-	NO	-
roles	name	character varying	50	-	NO	-
roles	description	character varying	255	-	YES	-
roles	created_at	timestamp with time zone	-	6	NO	now()
system_config_versions	id	character varying	64	-	NO	-
system_config_versions	config_key	character varying	100	-	NO	-
system_config_versions	version	integer	-	-	NO	-
system_config_versions	status	character varying	16	-	NO	'draft'::character varying
system_config_versions	value	jsonb	-	-	NO	-
system_config_versions	created_by_user_id	character varying	64	-	YES	-
system_config_versions	created_at	timestamp with time zone	-	6	NO	now()
system_config_versions	activated_at	timestamp with time zone	-	6	YES	-
user_profiles	user_id	character varying	64	-	NO	-
user_profiles	display_name	character varying	100	-	NO	-
user_profiles	student_number	character varying	32	-	YES	-
user_profiles	major	character varying	100	-	YES	-
user_profiles	updated_at	timestamp with time zone	-	6	NO	now()
user_roles	user_id	character varying	64	-	NO	-
user_roles	role_code	character varying	16	-	NO	-
user_roles	is_primary	boolean	-	-	NO	false
user_roles	granted_by_user_id	character varying	64	-	YES	-
user_roles	granted_at	timestamp with time zone	-	6	NO	now()
user_roles	revoked_at	timestamp with time zone	-	6	YES	-
users	id	character varying	64	-	NO	-
users	username	character varying	64	-	NO	-
users	username_key	character varying	64	-	NO	-
users	password_hash	text	-	-	NO	-
users	status	character varying	16	-	NO	'active'::character varying
users	created_at	timestamp with time zone	-	6	NO	now()
users	updated_at	timestamp with time zone	-	6	NO	now()

# Constraints: table, name, kind, definition
admin_audit_logs	ck_admin_audit_logs_actor_type	c	CHECK (((actor_type)::text = ANY ((ARRAY['user'::character varying, 'system'::character varying])::text[])))
admin_audit_logs	ck_admin_audit_logs_details_object	c	CHECK ((jsonb_typeof(details) = 'object'::text))
admin_audit_logs	ck_admin_audit_logs_request_format	c	CHECK (((request_id)::text ~ '^req_[0-9a-f]{32}$'::text))
admin_audit_logs	ck_admin_audit_logs_result	c	CHECK (((result)::text = ANY ((ARRAY['succeeded'::character varying, 'failed'::character varying, 'denied'::character varying])::text[])))
admin_audit_logs	fk_admin_audit_logs_actor_user_id_users	f	FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
admin_audit_logs	pk_admin_audit_logs	p	PRIMARY KEY (id)
auth_sessions	ck_auth_sessions_digest_format	c	CHECK (((jti_digest)::text ~ '^[0-9a-f]{64}$'::text))
auth_sessions	ck_auth_sessions_expiry	c	CHECK ((expires_at > issued_at))
auth_sessions	ck_auth_sessions_request_format	c	CHECK (((request_id)::text ~ '^req_[0-9a-f]{32}$'::text))
auth_sessions	ck_auth_sessions_revocation	c	CHECK ((((revoked_at IS NULL) AND (revoke_reason IS NULL)) OR ((revoked_at IS NOT NULL) AND (revoke_reason IS NOT NULL) AND ((revoke_reason)::text = ANY ((ARRAY['logout'::character varying, 'admin_revoke'::character varying, 'role_changed'::character varying, 'password_changed'::character varying])::text[])))))
auth_sessions	fk_auth_sessions_role_code_roles	f	FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE RESTRICT
auth_sessions	fk_auth_sessions_user_id_users	f	FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
auth_sessions	pk_auth_sessions	p	PRIMARY KEY (id)
auth_sessions	uq_auth_sessions_jti_digest	u	UNIQUE (jti_digest)
roles	ck_roles_code	c	CHECK (((code)::text = ANY ((ARRAY['student'::character varying, 'teacher'::character varying, 'admin'::character varying])::text[])))
roles	pk_roles	p	PRIMARY KEY (code)
system_config_versions	ck_system_config_versions_activation	c	CHECK (((((status)::text = 'draft'::text) AND (activated_at IS NULL)) OR (((status)::text <> 'draft'::text) AND (activated_at IS NOT NULL))))
system_config_versions	ck_system_config_versions_positive_version	c	CHECK ((version > 0))
system_config_versions	ck_system_config_versions_schema_version	c	CHECK (((value ? 'schemaVersion'::text) AND ((value ->> 'schemaVersion'::text) = '1.0'::text)))
system_config_versions	ck_system_config_versions_status	c	CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'active'::character varying, 'retired'::character varying])::text[])))
system_config_versions	ck_system_config_versions_value_object	c	CHECK ((jsonb_typeof(value) = 'object'::text))
system_config_versions	fk_system_config_versions_created_by_user_id_users	f	FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
system_config_versions	pk_system_config_versions	p	PRIMARY KEY (id)
system_config_versions	uq_system_config_versions_config_key	u	UNIQUE (config_key, version)
user_profiles	ck_user_profiles_name	c	CHECK (((length(btrim((display_name)::text)) >= 1) AND (length(btrim((display_name)::text)) <= 100)))
user_profiles	ck_user_profiles_student_number	c	CHECK (((student_number IS NULL) OR (length((student_number)::text) > 0)))
user_profiles	fk_user_profiles_user_id_users	f	FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
user_profiles	pk_user_profiles	p	PRIMARY KEY (user_id)
user_profiles	uq_user_profiles_student_number	u	UNIQUE (student_number)
user_roles	ck_user_roles_primary_active	c	CHECK (((NOT is_primary) OR (revoked_at IS NULL)))
user_roles	ck_user_roles_timestamps	c	CHECK (((revoked_at IS NULL) OR (revoked_at >= granted_at)))
user_roles	fk_user_roles_granted_by_user_id_users	f	FOREIGN KEY (granted_by_user_id) REFERENCES users(id) ON DELETE SET NULL
user_roles	fk_user_roles_role_code_roles	f	FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE RESTRICT
user_roles	fk_user_roles_user_id_users	f	FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
user_roles	pk_user_roles	p	PRIMARY KEY (user_id, role_code)
users	ck_users_id_format	c	CHECK (((id)::text ~ '^user_[0-9a-f]{32}$'::text))
users	ck_users_status	c	CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'disabled'::character varying])::text[])))
users	ck_users_timestamps	c	CHECK ((updated_at >= created_at))
users	ck_users_username_format	c	CHECK (((username)::text ~ '^[A-Za-z0-9_.-]{1,64}$'::text))
users	ck_users_username_key	c	CHECK (((username_key)::text = lower((username)::text)))
users	pk_users	p	PRIMARY KEY (id)
users	uq_users_username_key	u	UNIQUE (username_key)

# Indexes: table, name, definition
admin_audit_logs	ix_admin_audit_actor_time	CREATE INDEX ix_admin_audit_actor_time ON public.admin_audit_logs USING btree (actor_user_id, occurred_at)
admin_audit_logs	ix_admin_audit_request	CREATE INDEX ix_admin_audit_request ON public.admin_audit_logs USING btree (request_id)
admin_audit_logs	ix_admin_audit_target_time	CREATE INDEX ix_admin_audit_target_time ON public.admin_audit_logs USING btree (target_type, target_id, occurred_at)
admin_audit_logs	pk_admin_audit_logs	CREATE UNIQUE INDEX pk_admin_audit_logs ON public.admin_audit_logs USING btree (id)
auth_sessions	ix_auth_sessions_expiry	CREATE INDEX ix_auth_sessions_expiry ON public.auth_sessions USING btree (expires_at)
auth_sessions	ix_auth_sessions_user_expiry	CREATE INDEX ix_auth_sessions_user_expiry ON public.auth_sessions USING btree (user_id, expires_at)
auth_sessions	pk_auth_sessions	CREATE UNIQUE INDEX pk_auth_sessions ON public.auth_sessions USING btree (id)
auth_sessions	uq_auth_sessions_jti_digest	CREATE UNIQUE INDEX uq_auth_sessions_jti_digest ON public.auth_sessions USING btree (jti_digest)
roles	pk_roles	CREATE UNIQUE INDEX pk_roles ON public.roles USING btree (code)
system_config_versions	pk_system_config_versions	CREATE UNIQUE INDEX pk_system_config_versions ON public.system_config_versions USING btree (id)
system_config_versions	uq_system_config_active	CREATE UNIQUE INDEX uq_system_config_active ON public.system_config_versions USING btree (config_key) WHERE ((status)::text = 'active'::text)
system_config_versions	uq_system_config_versions_config_key	CREATE UNIQUE INDEX uq_system_config_versions_config_key ON public.system_config_versions USING btree (config_key, version)
user_profiles	pk_user_profiles	CREATE UNIQUE INDEX pk_user_profiles ON public.user_profiles USING btree (user_id)
user_profiles	uq_user_profiles_student_number	CREATE UNIQUE INDEX uq_user_profiles_student_number ON public.user_profiles USING btree (student_number)
user_roles	ix_user_roles_role_user	CREATE INDEX ix_user_roles_role_user ON public.user_roles USING btree (role_code, user_id)
user_roles	pk_user_roles	CREATE UNIQUE INDEX pk_user_roles ON public.user_roles USING btree (user_id, role_code)
user_roles	uq_user_roles_primary	CREATE UNIQUE INDEX uq_user_roles_primary ON public.user_roles USING btree (user_id) WHERE is_primary
users	ix_users_status	CREATE INDEX ix_users_status ON public.users USING btree (status)
users	pk_users	CREATE UNIQUE INDEX pk_users ON public.users USING btree (id)
users	uq_users_username_key	CREATE UNIQUE INDEX uq_users_username_key ON public.users USING btree (username_key)
```

</details>
