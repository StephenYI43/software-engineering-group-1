# 第一组接口设计

项目为大学生辅助学习 AI 数字人系统。关联 #80。本文与 `packages/contracts/api-v2/openapi.json` 是统一的 **v2 候选设计**，不是当前 FastAPI 已部署路由的导出文件。

## 来源和兼容性

截至2026-10-27，main 为7c174a4，实际挂载健康检查、登录、退出。analytics内存内核已由#38合入，但未挂主应用、未接PG。答疑#62 ee37891、客户端#68 8c6c6d4、媒体#61 411d3d7、learning骨架#60 c49ec1、平台PG底座#75 e1fb5ff、全域数据库#79 8061f4b为独立候选或分支贡献，不冒充已合并。

老师模板采用接口汇总、统一编码/参数定义、逐接口实例三章；PPT第5页要求数据项到资源，第8/14页采用统一封套与snake_case，第9页要求破坏性变更升版本。因此本批保留所有既有v1调用，另补v2候选。**没有自动更换前端客户端、服务端路由或数据库字段。** 公共契约仍需提供方/调用方与非作者评审。

| 方面 | 既有v1 | 本批v2候选 |
| --- | --- | --- |
| URL | /api/v1 | /api/v2，未实现 |
| JSON和路径参数 | camelCase | snake_case，禁止混用别名 |
| 成功JSON | 资源或分页对象 | code/message/data/trace_id，code=0 |
| 错误 | code/message/requestId/details；统一处理未全接入 | HTTP状态加数值业务码，安全data和trace_id |
| SSE | 帧字段在JSON根级 | 每帧统一封套，帧序号在data.seq；不是可直接替换的旧客户端 |
| 204/文件 | 沿原契约 | 204无体；文件与SSE为协议例外，不伪造JSON |
| 旧组件SDK | AvatarController camelCase | 保留，通过M2适配，不改组件入参 |

## 文件和复生成

- `scripts/api-design/contract_model.py`、`operations.py`：唯一的设计源；DTO、权限、资源与状态规则。
- `scripts/api-design/build_contracts.py`：生成OpenAPI、接口目录、Postman集合和TypeScript声明。
- `packages/contracts/api-v2/openapi.json`：可导入Swagger/Apifox的机器契约；只用本地#ref，不抓取外部schema。
- `packages/contracts/api-v2/catalog.json`：文档共用的逐接口字段、例子和实际状态。
- `apps/web/src/generated/api-v2.ts`：生成的wire类型；没有导入旧客户端。类型不代替JSON Schema、ACL或事务校验。
- `packages/contracts/api-v2/internal-contracts.json`：跨域公开函数、事件和组件适配边界。
- `verification.md`：实际命令和未验证范围，不把schema校验当成服务联调。

本版为114个HTTP操作、233个可校验结构。考试导入明确要求教师已确认的结构化试题，创建草稿、发布、公开试题、受控答案和教师批阅分别定义；不假称上传PDF即可自动完成整张试卷。

使用锁定API环境在仓库根目录运行：

```powershell
cd apps/api
uv sync --locked
uv run --locked python ../../scripts/api-design/build_contracts.py --check
uv run --locked pytest tests/contracts --no-cov
```

重新生成时去掉 `--check`；生成文件不得手改后不更新源。Postman集合只供导入，不自动运行。域名example.invalid不能用于真实部署；上传用例须自行选择获许可合成文件。

## 业务与数据覆盖

| 需求 | 资源/接口组 | 主要持久化输入 |
| --- | --- | --- |
| 数字人陪伴 | V 偏好、播放、计时；SDK01/02 | avatar_profiles/playback_records/focus_sessions |
| 课程导学 | C 课程章节、G 导学任务 | courses/chapters；导学派生内容另补存储 |
| 智能答疑 | T 会话、轮次、SSE、建议 | tutoring_sessions/turns/citations、版本化prompt/config |
| 作业习题 | A 作业、提交、批阅；W 错题/同类题 | assignments/submissions/mistakes |
| 预习复习 | L 计划/提醒、G 导学 | study_plans/plan_items/reminders |
| 课堂辅助 | K 文档解析/提炼、V ASR/OCR | documents/chunks/import_jobs/grants、media_assets/jobs |
| 备考冲刺 | E 试卷、作答、交卷与报告 | S2新增exam_papers/questions/attempts/answers，当前40表未包含 |
| 数据成长 | R 班级统计、报告、隔离重放 | analytics六表；读侧仍待真实PG实现 |
| 多学科与导入 | C subject/course、K 受控文件 | 受控学科代码，其他专业归other，不假称已有所有专业知识库 |
| 教师与管理 | C 授课选课、A 发布批阅、M 用户/配置/审计 | roles/user_roles、访问关系、config_versions/audit_logs |

本设计的入班申请、派生摘要/导学和考试实体属于显式新增持久化依赖，须先做独立建模/迁移。现有#79只允许事件schema_version=1.0，LearningEventV2的2.0不能原样写入；先评审增量迁移/适配、按版本分派，再灰度消费。不能把API版本2与内部配置对象版本1.0混为一谈。

## 评审和迁移顺序

1. M1/M2/M3/M4/M5/M6确认本域schema、例子、角色与旧v1映射；状态仍candidate，不按AI自评冻结。
2. M1先完成真实actor、错误封装和v2路由装配；M5维护唯一选课授课service并协调单链revision；M1维护metadata注册。
3. 按登录/课程/答疑/计划/事件/统计的最小链路逐批接真实PG。模型、repo、service、router、消费者与浏览器分别验收。
4. v1只有在用户迁移验收和团队批准停用日期后才退役，不能编造“已完成迁移”或删除旧端点。

## 参考

老师提供的《接口设计文档模板》和《接口设计技术及应用 方法 工具 规范与安全策略》30页PPT。原件只读，不上传公开仓库。

- OpenAPI 3.1.1：https://spec.openapis.org/oas/v3.1.1.html
- HTTP语义RFC9110：https://www.rfc-editor.org/rfc/rfc9110.html
- OWASP API Security Top10 2023：https://api-security.owasp.org/editions/2023/en/0x11-t10/
- 规范校验工具：https://openapi-spec-validator.readthedocs.io/
