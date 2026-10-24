# M4 业务与管理数据字典

owner：M4；本批由M1补全设计，原owner负责后续实现；日期2026-10-24。
关联#69、#42、#71、#72、#65；状态：设计草案，待非作者评审，未接应用迁移/repository。

物理结构唯一源为scripts/database-design/domain_model.py；生成DDL在docs/database-design/schema.sql。现有API字段不因新增列自动改变；公共增量须另经schema和消费者确认。

## avatar_config_versions

- 用途：数字人教学风格版本；配置管理。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_avatar_config_active ON avatar_config_versions(config_key) WHERE status='active'
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

配置引用受控形象资源，不存模型/语音密钥；已使用版本不可覆盖，修改新建版本。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成avatarcfg_+32hex；API按不透明ID处理 | PK |
| config_key | 风格用途 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| version | 版本 | integer | 否 | 无；调用方提供 | version>=1 | 无 |
| name | 风格名 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| config | 形象和教学参数 | jsonb | 否 | 无；调用方提供 | jsonb_typeof(config) = 'object' AND (config->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| status | 发布状态 | varchar(32) | 否 | 'draft' | status IN ('draft','active','retired') | 无 |
| created_by_user_id | 创建人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(config_key,version)`

JSONB版本及属性：
- `config`：对象schemaVersion=1.0；avatarAssetKey:受控存储键<=512；subjectStyle:冻结学科或other；tone:gentle/neutral/strict；defaultEmotion:冻结四值；defaultAction:冻结四值；非法未知键拒绝。

## avatar_profiles

- 用途：个人数字人和语音偏好；业务。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

跨设备偏好唯一归M4，不让M1/M5/M2另建student_preferences。仅本人修改；auto_play默认关闭避免未经意愿播报。组件目前未提供这些入参，服务端/API与组件schema需M2确认后实现。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成avatar_+32hex；API按不透明ID处理 | PK |
| user_id | 偏好所属用户 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| config_version_id | 风格版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→avatar_config_versions.id；ON DELETE RESTRICT |
| auto_play | 自动播报 | boolean | 否 | false | 按类型边界；跨行/权限由service验证 | 无 |
| volume | 音量 | numeric(3,2) | 否 | 1.00 | volume BETWEEN 0 AND 1 | 无 |
| speech_rate | 语速 | numeric(3,2) | 否 | 1.00 | speech_rate BETWEEN 0.5 AND 2 | 无 |
| subtitles_enabled | 字幕 | boolean | 否 | true | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(user_id)`

## media_assets

- 用途：媒体文件和录音授权元数据；资源管理。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

文件不塞PG；生成签名下载地址前核权，不公开storage_key。录音缺同意拒绝；删除流程先阻断使用、再清对象和派生文本/引用、最后标deleted，失败可重试并审计。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成media_+32hex；API按不透明ID处理 | PK |
| owner_user_id | 文件owner | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| storage_key | 私有存储键 | varchar(512) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| sha256 | 文件摘要 | varchar(64) | 否 | 无；调用方提供 | sha256 ~ '^[0-9a-f]{64}$' | 无 |
| mime_type | 实际媒体类型 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| byte_size | 字节大小 | bigint | 否 | 无；调用方提供 | byte_size>0 | 无 |
| kind | 资产类型 | varchar(32) | 否 | 无；调用方提供 | kind IN ('image','audio','video','document','avatar') | 无 |
| status | 资产生命周期 | varchar(32) | 否 | 'ready' | status IN ('ready','withdrawn','deleting','deleted') | 无 |
| consent_version | 录音/处理同意版本 | varchar(32) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| consented_at | 同意时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| expires_at | 到期时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| deleted_at | 完成删除时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(storage_key)`
- `CHECK(kind<>'audio' OR (consent_version IS NOT NULL AND consented_at IS NOT NULL))`
- `CHECK((status='deleted') = (deleted_at IS NOT NULL))`

## media_jobs

- 用途：语音与媒体处理任务；任务管理。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

键复用换参数409；worker有界重试，实际ASR/TTS不在本批交付，is_mock不能当真实服务。params不存完整对话/密钥，转写文本通过受控output_asset管理。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成mediajob_+32hex；API按不透明ID处理 | PK |
| owner_user_id | 任务owner | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| input_asset_id | 输入资产 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→media_assets.id；ON DELETE RESTRICT |
| output_asset_id | 输出资产 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→media_assets.id；ON DELETE RESTRICT |
| job_type | 处理类型 | varchar(32) | 否 | 无；调用方提供 | job_type IN ('tts','asr','ocr','transcode') | 无 |
| processor_version | 处理器版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| is_mock | Mock标识 | boolean | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| idempotency_key | 重试键 | varchar(128) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| request_hash | 请求摘要 | varchar(64) | 否 | 无；调用方提供 | request_hash ~ '^[0-9a-f]{64}$' | 无 |
| params | 非敏感处理参数 | jsonb | 否 | '{"schemaVersion":"1.0"}'::jsonb | jsonb_typeof(params) = 'object' AND (params->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| status | 任务状态 | varchar(32) | 否 | 'queued' | status IN ('queued','running','succeeded','failed','cancelled') | 无 |
| attempts | 尝试次数 | integer | 否 | 0 | attempts>=0 | 无 |
| error_code | 脱敏错误码 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| request_id | 请求号 | varchar(36) | 否 | 无；调用方提供 | request_id ~ '^req_[0-9a-f]{32}$' | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| started_at | 开始时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| finished_at | 结束时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(owner_user_id,job_type,idempotency_key)`
- `CHECK((status IN ('succeeded','failed','cancelled')) = (finished_at IS NOT NULL))`

JSONB版本及属性：
- `params`：对象schemaVersion=1.0；language可选zh-CN/en-US；voiceCode为服务端白名单<=64；rate可选0.5..2；每种job_type固定允许键，禁止任意URL、命令、密钥或原始学生文本。

## playback_records

- 用途：播报标识与唯一终态；业务。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

条件UPDATE WHERE status=started实现唯一终态，重复相同终态幂等、冲突终态409，不靠单个CHECK验证历史迁移。只播completed完整答复；前端上报是播放遥测，不视为实际学习时长证据。停止不删文字，不复制完整回答到日志。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成playback_+32hex；API按不透明ID处理 | PK |
| utterance_id | 前端播报标识 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| user_id | 播报用户 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| turn_id | 完整答疑来源 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→tutoring_turns.id；ON DELETE RESTRICT |
| media_job_id | 语音任务 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→media_jobs.id；ON DELETE RESTRICT |
| config_version_id | 风格版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→avatar_config_versions.id；ON DELETE RESTRICT |
| is_mock | 是否Mock | boolean | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| status | 播报状态 | varchar(32) | 否 | 'started' | status IN ('started','completed','stopped','error') | 无 |
| stop_reason | 停止原因 | varchar(32) | 是 | NULL | stop_reason IN ('user_stop','replaced','component_unmounted') | 无 |
| error_code | 错误码 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| started_at | 开始时刻 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| ended_at | 终态时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| duration_ms | 耗时毫秒 | integer | 是 | NULL | duration_ms IS NULL OR duration_ms>=0 | 无 |

表级约束：
- `UNIQUE(user_id,utterance_id)`
- `CHECK((status='started')=(ended_at IS NULL))`
- `CHECK(ended_at IS NULL OR ended_at>=started_at)`
- `CHECK((status='stopped')=(stop_reason IS NOT NULL))`
- `CHECK((status='error')=(error_code IS NOT NULL))`

## focus_sessions

- 用途：主动专注计时；业务。
- owner：M4；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_focus_running ON focus_sessions(user_id) WHERE status='running'
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

用户主动开启，S1仅设计保留；不采集摄像头/生理指标，不声称检测疲劳或专注心理状态。服务端校验时间，客户端填时长不直接记入教师统计。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成focus_+32hex；API按不透明ID处理 | PK |
| user_id | 学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| started_at | 开始时刻 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| ended_at | 结束时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| duration_seconds | 有效秒数 | integer | 是 | NULL | duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 86400 | 无 |
| status | 计时状态 | varchar(32) | 否 | 'running' | status IN ('running','completed','cancelled') | 无 |
| idempotency_key | 创建重试键 | varchar(128) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(user_id,idempotency_key)`
- `CHECK((status='running')=(ended_at IS NULL))`
- `CHECK(ended_at IS NULL OR ended_at>=started_at)`

## JSONB内部字典

内部属性使用对象内版本或相邻schema_version列；两种方式都不修改既有wire。具体必填键/类型/取值/空值见各表JSONB规则；见docs/database-design/jsonb-schemas.md的七列属性明细。
