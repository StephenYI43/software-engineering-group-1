# 第一组数据库设计

项目：大学生辅助学习 AI 数字人系统。日期：2026-10-24。父任务#69。

本批按组长授权直接补全缺失设计，不再要求原owner先设计后才能继续。平台七表沿用#75 e1fb5ff；M3九表参考#76 b2eab6b并修正持久状态、冻结枚举等差异；M4、M5、M6缺失部分由M1完成设计。原owner继续负责实现和测试，不将他人贡献改署成自己已完成。

## 内容与状态

- 40张表覆盖业务与管理，字段逐项给出物理名、中文含义、类型/长度、可空、默认、约束和关系。
- `schema.json`：生成后的字段清单；`schema.sql`：空临时库参考DDL，含平台JSON null补强CHECK；不是Alembic revision，绝不能在已有应用库整包执行。
- `../data-model/learning.md`、`tutoring-knowledge.md`、`avatar-media.md`、`analytics-admin.md`：分域字典。
- `jsonb-schemas.md`：JSON属性与版本位置，保持既有wire键，不擅自强加payload.schemaVersion。
- `decisions.md`：权限、状态、并发、事件迟到、保留/删除、API增量与实施批次。
- `verification.md`：本批实际运行与未运行项，设计SQL通过不代表repository/API/UI已完成。

最终文档使用老师模板六章顺序；源模板不上传公开Git。文档封面与生成文件不包含真实学生资料、连接密钥或未经授权课件。

## 复生成

在仓库根目录使用已锁定apps/api依赖：

```powershell
cd apps/api
uv sync --locked
uv run --locked python ../../scripts/database-design/build_schema.py
```

结构唯一源为`domain_model.py`和现有平台ORM；不得手改生成SQL后不更新源定义。应用落地仍需M5协调单一Alembic链、领域owner编写migration/repository，M1维护metadata注册。公共接口增量按schema→提供方/消费者评审→实现的顺序推进。本PR不修改现有公共API、不直接写main、不自动合并或部署。
