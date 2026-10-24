# M6 业务与管理数据字典

owner：M6；本批由M1补全设计，原owner负责后续实现；日期2026-10-24。
关联#69、#42、#71、#72、#65；状态：设计草案，待非作者评审，未接应用迁移/repository。

物理结构唯一源为scripts/database-design/domain_model.py；生成DDL在docs/database-design/schema.sql。现有API字段不因新增列自动改变；公共增量须另经schema和消费者确认。

## analytics_consumers

- 用途：消费者与算法发布状态；消费管理。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

每轮事务锁本行串行化同消费者；last_observed只用于诊断，不参与排除旧事件。每次提交后新事务重查未处理事件，禁止WHERE id>水位造成永久漏读。不同算法版本独立consumer与聚合空间。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成consumer_+32hex；API按不透明ID处理 | PK |
| consumer_key | 消费者名称 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| algorithm_version | 算法版本 | varchar(32) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| status | 消费者状态 | varchar(32) | 否 | 'paused' | status IN ('active','paused','retired') | 无 |
| last_poll_at | 最近扫描时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| last_observed_at | 最近观察事件时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| processed_count | 累计处理量 | bigint | 否 | 0 | processed_count>=0 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(consumer_key,algorithm_version)`

## analytics_processed_events

- 用途：已处理事件账本；消费管理。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

(consumer,event)唯一；写账本与聚合更新同事务，不先写done后改指标。重启重复扫不重复计数；源事件不可变。只有已成功处理才进入账本，隔离另表不伪装已完成。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| consumer_id | 消费者版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | PK+FK→analytics_consumers.id；ON DELETE RESTRICT |
| event_id | 源事件 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | PK+FK→learning_events.id；ON DELETE RESTRICT |
| processed_at | 成功处理时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| source_hash | 源事实摘要 | varchar(64) | 否 | 无；调用方提供 | source_hash ~ '^[0-9a-f]{64}$' | 无 |

## analytics_daily_metrics

- 用途：学生班级日统计；业务统计。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

class为事件发生时快照；无class事件不摊到每班。无观测时unknown+NULL，已确认无活动才known+0；不能用count默认0推断数据完整。迟到事件到达后重算受影响学生/班级/日，不按到达顺序累加推断时长。日界按时区日历，不按固定24小时跨DST。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成metric_+32hex；API按不透明ID处理 | PK |
| consumer_id | 算法消费者 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→analytics_consumers.id；ON DELETE RESTRICT |
| student_user_id | 学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| class_id | 发生时班级 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| metric_date | 统计本地日 | date | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| timezone | 日界时区 | varchar(64) | 否 | 'Asia/Shanghai' | 按类型边界；跨行/权限由service验证 | 无 |
| study_seconds | 推断学习秒 | integer | 是 | NULL | study_seconds IS NULL OR study_seconds>=0 | 无 |
| submission_count | 提交数 | integer | 否 | 0 | submission_count>=0 | 无 |
| wrong_count | 已判错数量 | integer | 否 | 0 | wrong_count>=0 | 无 |
| sample_count | 有效样本数 | integer | 否 | 0 | sample_count>=0 | 无 |
| data_state | 数据状态 | varchar(32) | 否 | 'unknown' | data_state IN ('unknown','partial','known') | 无 |
| data_through | 本范围纳入最新发生时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,course_id,class_id,metric_date,timezone)`
- `FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT`
- `CHECK(class_id IS NULL OR course_id IS NOT NULL)`
- `CHECK(data_state <> 'unknown' OR study_seconds IS NULL)`

## analytics_report_snapshots

- 用途：个人和班级成长报告快照；业务报告。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

本人报告与教师班级报告二选一；教师须当前授权班级，学生只本人。雷达掌握度必须带样本/算法/未知状态，不凭模型编造分数；个人报告API为后续schema增量，尚未实现。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成report_+32hex；API按不透明ID处理 | PK |
| consumer_id | 算法版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→analytics_consumers.id；ON DELETE RESTRICT |
| student_user_id | 个人报告主体 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| class_id | 班级报告范围 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| period_start | 周期起点 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| period_end | 周期终点 | timestamptz(6) | 否 | 无；调用方提供 | period_end>period_start | 无 |
| metrics | 指标与知识点掌握度 | jsonb | 否 | 无；调用方提供 | jsonb_typeof(metrics) = 'object' AND (metrics->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| sample_count | 样本数 | integer | 否 | 无；调用方提供 | sample_count>=0 | 无 |
| data_through | 纳入最新发生时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| generated_at | 生成时间 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1)`
- `UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,class_id,period_start,period_end)`

JSONB版本及属性：
- `metrics`：对象schemaVersion=1.0；dataState:unknown/partial/known；studySeconds非负或null；knowledgePoints数组0..100项，每项{key:string<=100,mastery:number 0..1或null,sampleCount:integer>=0,dataState}；weakSubjects数组受控学科；suggestions为脱敏文本数组0..10项。

## report_jobs

- 用途：周月报告生成任务；任务管理。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

调度重试复用幂等键；执行时重新检查请求者权限，不能拿创建时权限永久导出。报告结果与任务成功同事务。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成reportjob_+32hex；API按不透明ID处理 | PK |
| requested_by_user_id | 请求者 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| student_user_id | 个人目标 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| class_id | 班级目标 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| consumer_id | 算法版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→analytics_consumers.id；ON DELETE RESTRICT |
| period_start | 开始 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| period_end | 结束 | timestamptz(6) | 否 | 无；调用方提供 | period_end>period_start | 无 |
| status | 生成状态 | varchar(32) | 否 | 'queued' | status IN ('queued','running','succeeded','failed','cancelled') | 无 |
| idempotency_key | 请求重试键 | varchar(128) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| error_code | 脱敏错误码 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| report_id | 结果快照 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→analytics_report_snapshots.id；ON DELETE RESTRICT |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| finished_at | 终态时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(requested_by_user_id,idempotency_key)`
- `CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1)`
- `CHECK((status IN ('succeeded','failed','cancelled'))=(finished_at IS NOT NULL))`
- `CHECK(status<>'succeeded' OR report_id IS NOT NULL)`

## analytics_quarantined_events

- 用途：毒事件隔离与审计重放；运维管理。
- owner：M6；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

不复制敏感payload，引用原事件。open明确告警/报告partial，不静默跳过；授权人工审计后置retry_ready，成功处理后ledger+聚合+resolved同事务。源事件保持不变；修schema/算法用新consumer版本或受控重放。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成quarantine_+32hex；API按不透明ID处理 | PK |
| consumer_id | 消费者 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→analytics_consumers.id；ON DELETE RESTRICT |
| event_id | 源事件 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→learning_events.id；ON DELETE RESTRICT |
| error_code | 脱敏失败码 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| status | 处理状态 | varchar(32) | 否 | 'open' | status IN ('open','retry_ready','resolved') | 无 |
| attempts | 失败次数 | integer | 否 | 1 | attempts>=1 | 无 |
| resolved_by_user_id | 人工处理者 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |
| first_failed_at | 首次失败 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| last_failed_at | 最近失败 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| resolved_at | 重放解决时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(consumer_id,event_id)`
- `CHECK(last_failed_at>=first_failed_at)`
- `CHECK((status='resolved')=(resolved_at IS NOT NULL))`

## JSONB内部字典

内部属性使用对象内版本或相邻schema_version列；两种方式都不修改既有wire。具体必填键/类型/取值/空值见各表JSONB规则；见docs/database-design/jsonb-schemas.md的七列属性明细。
