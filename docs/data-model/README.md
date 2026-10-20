# 课堂数据建模与持久化交付基线

关联：[#69 总任务](https://github.com/StephenYI43/software-engineering-group-1/issues/69)。
基线日期：2026-10-20。状态：**设计草案，待相关负责人评审；本文不代表已经建表或完成持久化。**

## 实际起点

main `d01f32e` 已有健康检查与演示认证；learning 只有契约附属的表概览，PR #60 是未合并的 dataclass/InMemory 骨架。
尚无完整全域数据字典、数据库连接和迁移，也没有重启后保留记录的验收证据。
模型基线PR #73先交统一格式、全域关系草图与平台七表字段设计；#48任务分支已增量实现平台七表迁移、认证持久化与真实PG验证，仍待评审合入。后续领域由各owner提交。
平台接入与验证证据见 [数据库指南](platform-verification.md)。

## 七要素工作格式

老师的具体模板尚未取得，暂采用以下数据库字段七列；取得模板后做列映射，不把这个选择描述成老师已确认标准。

| 物理字段名 | 中文名称/业务含义（需要时补别名） | PostgreSQL 类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK                   | PK/FK/关联与删除/更新规则      |
| ---------- | --------------------------------- | -------------------------- | ---- | ----------------- | ------------------------------------------ | ------------------------------ |
| id         | 记录标识                          | varchar(64)                | 否   | 无，服务端生成    | 非空；实体前缀+32位小写hex；对调用方不透明 | PK；被引用时按业务另定删除规则 |
| created_at | 创建时刻                          | timestamptz(6)             | 否   | CURRENT_TIMESTAMP | UTC时间；API输出ISO 8601                   | 无（非键）                     |

每列必须填写；没有默认或关联写“无”，不能留空。JSONB 内部各属性也需类型、必填、范围、默认及 schemaVersion。
字段之外每张表必须写用途、owner、业务/管理类别、候选/组合键、索引、数据来源、读写权限、数据保留与删除策略、实现状态。
数据库状态分为：设计草案→评审确认→迁移已实现→真实 PostgreSQL 测试通过；前端 Mock 或内存测试不能提升状态。

## 模块清单与唯一负责人

| 模块          | 业务覆盖                                                                                                                                               | 管理覆盖                                                                                                     | 本域文件/任务                   | 当前文档状态                           |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | ------------------------------- | -------------------------------------- |
| 平台/M1       | users、user_profiles、auth_sessions                                                                                                                    | roles、user_roles、admin_audit_logs、system_config_versions                                                  | [platform.md](platform.md)；#48 | 任务分支已迁移及真实PG验证，待评审合入 |
| 学生端/M2     | 课程/作业/错题/计划/答疑字段到已有域的映射                                                                                                             | 持久偏好归属、UI临时态说明、字典检查与验收                                                                   | `student.md`；#70               | 待M2提交；不重复建业务表               |
| 答疑知识/M3   | tutoring_sessions、tutoring_turns、turn_citations、documents、document_chunks                                                                          | document_grants、document_import_jobs、prompt_versions、model_config_versions                                | `tutoring-knowledge.md`；#71    | 待M3提交                               |
| 数字人媒体/M4 | avatar_profiles、playback_records、focus_sessions                                                                                                      | media_assets、media_jobs、avatar_config_versions                                                             | `avatar-media.md`；#72          | 待M4提交                               |
| 学习业务/M5   | courses、classes、chapters、enrollments、teaching_assignments、assignments、submissions、mistakes、study_plans、plan_items、reminders、learning_events | 发布/批阅/幂等/选课与授课维护；通用审计复用M1                                                                | `learning.md`；#42              | 有契约概览；七要素与真实DB待提交       |
| 分析教师/M6   | analytics_daily_metrics、analytics_report_snapshots                                                                                                    | analytics_consumers、analytics_processed_events、analytics_quarantined_events、report_jobs；授权花名册复用M5 | `analytics-admin.md`；#65       | 有统计契约；七要素与真实DB待提交       |

这些表名中仅 learning 的已有契约名称应视作已接受的基线，其余候选名称须领域 owner 与消费者确认。
S2实体可先设计，但必须标“设计保留”；持久化课堂验收先完成S1小闭环。
跨域不复制用户、课程、花名册；管理员身份、角色、配置与审计数据也必须建模。统计不能将“未知”保存成0冒充已知。

## 关系与一致性

全域草图见 [erd.md](erd.md)。图中连线表达目标关系，尚非数据库已存在的外键。
业务主键保持兼容现有API的前缀+32hex字符串；列snake_case，JSON camelCase；映射写进本域字典。
时间采用timestamptz并统一UTC。updated_at由服务端更新逻辑或明确触发器维护，DEFAULT不会在UPDATE时自动刷新。

课程与教学班分开。用户可在同课程多个班；只凭course_id不足以判定class_id。
模型内容与上传文件是数据，不授予访问权限。授权查询在检索前发生，课件二进制与数据库元数据分开。
事件与业务在同一事务写入；repository不得自行commit。避免“先提交业务再写事件”的双写遗漏。
序列/identity按分配顺序增长，不保证提交顺序；M6必须验证较小ID事务延迟提交仍可被消费。

## 数据库实施边界

选型沿用 #48 的已发布方向：PostgreSQL17、SQLAlchemy2同步Session、psycopg3、Alembic。
准确依赖版本、镜像小版本/摘要由 #48 实测锁定，不使用latest。
一个Base、SessionFactory和元数据注册入口，由M1维护；M5协调单一Alembic迁移链。
模型基线PR #73本身不新增实现；#48后续实现保持JWT/登录响应兼容，数据库模式下持久化账号与会话。课程ACL仍由#16交付。

数据字典不完整时先提交明确差异；不得为让校验通过临时填“待定”或吞掉缺表错误。
每个字段都应能定位到契约/需求和实际迁移；设计保留实体不计入已持久化数量。

## 课堂验收证据

owner：M2，实际结果填写 `acceptance.md`，不得预先勾选。

1. 清洁开发库执行upgrade head，确认单一head，约束/索引与字典一致。
2. 重复seed合成学生A/B、教师、管理员、课程和两个班，主键及行数稳定。
3. 写入课程/选课、作业提交与事件、Mock答疑回合、媒体任务/偏好、教师统计、管理审计。
4. 提交事务后关闭Session；重启API与保留数据卷的PostgreSQL；核对记录仍在、主键不变。
5. 验证幂等、回滚、外键、唯一、CHECK、跨用户/班级隔离以及并发乱序提交事件。
6. 报告commit、版本、命令、输出、SQL行数、运行层级（repository/API/UI）和未完成项。

删除/降级只在显式临时测试库执行；保留卷重启不能使用删除卷命令。
课堂模型可Mock，数据库不得用InMemory或SQLite冒充PostgreSQL。
本PR的验证仅为文档差异、链接和平台七列结构检查；没有真实数据库测试结果。
