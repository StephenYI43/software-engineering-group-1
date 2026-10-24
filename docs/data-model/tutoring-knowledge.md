# M3 业务与管理数据字典

owner：M3；本批由M1补全设计，原owner负责后续实现；日期2026-10-24。
关联#69、#42、#71、#72、#65；状态：设计草案，待非作者评审，未接应用迁移/repository。

物理结构唯一源为scripts/database-design/domain_model.py；生成DDL在docs/database-design/schema.sql。现有API字段不因新增列自动改变；公共增量须另经schema和消费者确认。

## tutoring_sessions

- 用途：学生私有多轮答疑会话；业务。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

生产会话ID由服务端创建接口发号（接口schema待共同确认），不把Mock路径首次见即创建搬入生产。NULL课程为通用问答，不授予任何文档权；教师默认不可读完整对话。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成sess_+32hex；API按不透明ID处理 | PK |
| student_user_id | 所属学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程上下文 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| current_stage | 当前教学阶段 | varchar(32) | 否 | 'thought' | current_stage IN ('thought','hint','step','summary') | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

## tutoring_turns

- 用途：答疑轮次和完整性结算；业务。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_turns_active ON tutoring_turns(session_id) WHERE status='active'
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

沿用main契约，停止/断连/失败归aborted，原因在abort_reason；不推进阶段。成功结算与阶段推进/引用同事务，summary封顶。未完成正文最多16000字符、标未完成、不作后续已完成历史/播报；超限只在aborted时截断，completed正文必须与delta拼接一致，超限报错。进程重启时恢复任务把孤立active结算aborted/server_restart，需与仍活跃worker租约确认，不能误杀在飞轮次。hasEvidence由引用行推导，不再冗余布尔列。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成turn_+32hex；API按不透明ID处理 | PK |
| session_id | 所属会话 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→tutoring_sessions.id；ON DELETE CASCADE |
| seq | 会话内轮次 | integer | 否 | 无；调用方提供 | seq >= 1; 会话行锁下分配；不同于SSE seq | 无 |
| request_id | 创建请求号 | varchar(36) | 否 | 无；调用方提供 | request_id ~ '^req_[0-9a-f]{32}$' | 无 |
| student_content | 学生问题 | varchar(2000) | 否 | 无；调用方提供 | length(btrim(student_content))>0 | 无 |
| assistant_content | 已生成正文或中断部分 | text | 是 | NULL | assistant_content IS NULL OR length(assistant_content)<=16000 | 无 |
| stage | 本轮冻结阶段 | varchar(32) | 否 | 无；调用方提供 | stage IN ('thought','hint','step','summary') | 无 |
| status | 持久化轮次状态 | varchar(32) | 否 | 'active' | status IN ('active','completed','aborted') | 无 |
| abort_reason | 内部中断原因 | varchar(32) | 是 | NULL | abort_reason IN ('client_stop','client_disconnect','model_error','retrieval_error','server_restart') | 无 |
| is_complete | 完整回答标志 | boolean | 否 | false | 按类型边界；跨行/权限由service验证 | 无 |
| is_mock | Mock来源标志 | boolean | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| emotion | 冻结情绪 | varchar(32) | 是 | NULL | emotion IN ('neutral','encouraging','thinking','celebrating') | 无 |
| action | 冻结动作 | varchar(32) | 是 | NULL | action IN ('idle','nod','point','write') | 无 |
| follow_ups | 追问建议 | jsonb | 否 | '{"schemaVersion":"1.0","items":[]}'::jsonb | jsonb_typeof(follow_ups) = 'object' AND (follow_ups->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| prompt_version_id | 提示词版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→prompt_versions.id；ON DELETE RESTRICT |
| model_config_version_id | 模型配置版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→model_config_versions.id；ON DELETE RESTRICT |
| input_tokens | 输入token量 | integer | 是 | NULL | input_tokens IS NULL OR input_tokens>=0 | 无 |
| output_tokens | 输出token量 | integer | 是 | NULL | output_tokens IS NULL OR output_tokens>=0 | 无 |
| duration_ms | 耗时毫秒 | integer | 是 | NULL | duration_ms IS NULL OR duration_ms>=0 | 无 |
| error_code | 错误码 | varchar(32) | 是 | NULL | error_code IN ('MODEL_OUTPUT_INVALID','MODEL_REFUSED','MODEL_TIMEOUT','RETRIEVAL_UNAVAILABLE','TURN_ABORTED') | 无 |
| error_reason | 内部原因码 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| settled_at | 终态时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(session_id,seq)`
- `CHECK(is_complete = (status='completed'))`
- `CHECK((status='active') = (settled_at IS NULL))`
- `CHECK(settled_at IS NULL OR settled_at >= created_at)`
- `CHECK((status='aborted') = (abort_reason IS NOT NULL))`
- `CHECK(status<>'completed' OR (assistant_content IS NOT NULL AND emotion IS NOT NULL AND action IS NOT NULL))`
- `CHECK(error_code IS NULL OR status='aborted')`

JSONB版本及属性：
- `follow_ups`：对象schemaVersion=1.0；items为string数组，0..3项，每项1..200字符；仅completed可供客户端作为建议，其他状态不伪装完整响应。

## turn_citations

- 用途：轮次引用与证据快照；业务。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

按本轮已授权检索白名单构造；snapshot改名不漂移。原始文档下载不因看见引用就放行；撤权后历史片段访问也重新核权。法定/授权清除流程须覆盖快照，不以FK永久保留为由拒绝清除。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| turn_id | 轮次 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | PK+FK→tutoring_turns.id；ON DELETE CASCADE |
| citation_id | 轮内标签 | varchar(8) | 否 | 无；调用方提供 | citation_id ~ '^c[1-9][0-9]?$' | PK |
| document_id | 文档版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE RESTRICT |
| chunk_id | 原片段 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→document_chunks.id；ON DELETE RESTRICT |
| document_title_snapshot | 引用时标题 | varchar(200) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| document_version | 引用时版本 | integer | 否 | 无；调用方提供 | document_version>=1 | 无 |
| page_number | 页码 | integer | 否 | 无；调用方提供 | page_number>=1 | 无 |
| snippet | 证据片段 | varchar(1000) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(turn_id,chunk_id)`
- `FOREIGN KEY(chunk_id,document_id) REFERENCES document_chunks(id,document_id) ON DELETE RESTRICT`

## documents

- 用途：版本化课程文档元数据；业务。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_document_successor ON documents(previous_document_id) WHERE previous_document_id IS NOT NULL
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

新解析版本新建行/chunks，旧引用不改。可检索必须available；课程归档/授权撤回立即停止新检索。二进制不入PG；上传校验实际类型/大小，标题/正文是不可信数据。上传者身份不是无限读全课程授权。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成doc_+32hex；API按不透明ID处理 | PK |
| course_id | 课程 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| uploader_user_id | 上传者 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| title | 文档标题 | varchar(200) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| storage_key | 受控文件存储键 | varchar(512) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| file_sha256 | 文件摘要 | varchar(64) | 否 | 无；调用方提供 | file_sha256 ~ '^[0-9a-f]{64}$' | 无 |
| mime_type | 媒体类型 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| byte_size | 文件字节数 | bigint | 否 | 无；调用方提供 | byte_size>0 | 无 |
| version | 文档版本 | integer | 否 | 1 | version>=1 | 无 |
| previous_document_id | 前一版本 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE RESTRICT |
| status | 可检索状态 | varchar(32) | 否 | 'uploaded' | status IN ('uploaded','available','withdrawn') | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

## document_chunks

- 用途：可定位文档片段；业务。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

切片不跨页，页号1基、字符区间左闭右开；S1不强装pgvector，向量与索引另ADR。仅对已授权文档检索，不能先全库检索再过滤。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成chunk_+32hex；API按不透明ID处理 | PK |
| document_id | 文档版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE CASCADE |
| chunk_index | 文档内序号 | integer | 否 | 无；调用方提供 | chunk_index>=0 | 无 |
| page_number | 页码 | integer | 否 | 无；调用方提供 | page_number>=1 | 无 |
| char_start | 页内起点 | integer | 否 | 无；调用方提供 | char_start>=0 | 无 |
| char_end | 页内终点 | integer | 否 | 无；调用方提供 | char_end>char_start | 无 |
| text | 片段正文 | text | 否 | 无；调用方提供 | length(text)>0 | 无 |
| text_sha256 | 正文摘要 | varchar(64) | 否 | 无；调用方提供 | text_sha256 ~ '^[0-9a-f]{64}$' | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(document_id,chunk_index)`
- `UNIQUE(id,document_id)`

## document_grants

- 用途：文档例外授权及班级授权；权限管理。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_doc_grant_user ON document_grants(document_id,user_id) WHERE revoked_at IS NULL AND user_id IS NOT NULL；CREATE UNIQUE INDEX uq_doc_grant_class ON document_grants(document_id,class_id) WHERE revoked_at IS NULL AND class_id IS NOT NULL
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

个人/班级目标二选一；班级可见性经M5有效花名册，须验证文档/班级课程一致；不复制花名册。授权/撤销与平台audit同事务，撤权后新检索/历史引用/下载分别重查。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成grant_+32hex；API按不透明ID处理 | PK |
| document_id | 文档 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE CASCADE |
| user_id | 被授权个人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| class_id | 被授权班级 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| granted_by_user_id | 授权操作人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |
| granted_at | 授权时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| revoked_at | 撤销时刻 | timestamptz(6) | 是 | NULL | revoked_at IS NULL OR revoked_at>=granted_at | 无 |

表级约束：
- `CHECK((user_id IS NOT NULL)::integer + (class_id IS NOT NULL)::integer = 1)`

## document_import_jobs

- 用途：课件解析任务与重试；任务管理。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

任务状态不同于文档可检索状态；失败保留码不记原课件正文。实际解析器/队列未在本批实现，Mock需标记。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成job_+32hex；API按不透明ID处理 | PK |
| document_id | 输入文档版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE CASCADE |
| parser_version | 解析器版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| idempotency_key | 重试幂等键 | varchar(128) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| status | 任务状态 | varchar(32) | 否 | 'queued' | status IN ('queued','running','succeeded','failed') | 无 |
| request_id | 请求追踪号 | varchar(36) | 否 | 无；调用方提供 | request_id ~ '^req_[0-9a-f]{32}$' | 无 |
| attempts | 尝试次数 | integer | 否 | 0 | attempts>=0 | 无 |
| error_code | 脱敏失败码 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| pages_without_text | 无文字页报告 | jsonb | 否 | '{"schemaVersion":"1.0","pages":[]}'::jsonb | jsonb_typeof(pages_without_text) = 'object' AND (pages_without_text->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| started_at | 开始时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| finished_at | 结束时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(document_id,idempotency_key)`
- `CHECK((status IN ('succeeded','failed')) = (finished_at IS NOT NULL))`
- `CHECK(started_at IS NULL OR started_at>=created_at)`
- `CHECK(finished_at IS NULL OR (started_at IS NOT NULL AND finished_at>=started_at))`

JSONB版本及属性：
- `pages_without_text`：对象schemaVersion=1.0；pages为升序去重的integer数组，元素>=1，表示成功解析中无文字页；失败不伪造成功页数。

## prompt_versions

- 用途：提示词发布版本目录；配置管理。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_prompt_active ON prompt_versions(series) WHERE status='active'
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

正文唯一源为ai/prompts受控不可变Git版本；路径只在该目录，不能由上传内容指定。部署必须包含旧版本；哈希不符失败不回退。draft不伪造发布时间直接retired。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成promptver_+32hex；API按不透明ID处理 | PK |
| series | 模板系列 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| version_label | API提示词版本 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| template_path | 仓库相对路径 | varchar(255) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| content_sha256 | 正文摘要 | varchar(64) | 否 | 无；调用方提供 | content_sha256 ~ '^[0-9a-f]{64}$' | 无 |
| status | 发布状态 | varchar(32) | 否 | 'draft' | status IN ('draft','active','retired') | 无 |
| created_by_user_id | 登记人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| activated_at | 启用时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| retired_at | 退役时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(series,version_label)`
- `CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))`

## model_config_versions

- 用途：模型配置版本；配置管理。
- owner：M3；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_model_config_active ON model_config_versions(config_key) WHERE status='active'
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

provider来自已注册adapter，不能任意URL。密钥仅环境/secret服务，库不存密钥。温度范围是设计而非保证任意供应商支持，adapter进一步校验。版本锁内分配；发布/退役与审计同事务。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成modelcfg_+32hex；API按不透明ID处理 | PK |
| config_key | 配置用途 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| version | 版本号 | integer | 否 | 无；调用方提供 | version>=1 | 无 |
| provider | 受控供应商代码 | varchar(32) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| model_name | 模型名 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| is_mock | Mock配置 | boolean | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| temperature | 采样温度 | numeric(3,2) | 否 | 无；调用方提供 | temperature BETWEEN 0 AND 2 | 无 |
| max_output_tokens | 最大输出token | integer | 否 | 无；调用方提供 | max_output_tokens>0 | 无 |
| timeout_seconds | 总超时秒 | numeric(6,2) | 否 | 无；调用方提供 | timeout_seconds>0 | 无 |
| status | 配置状态 | varchar(32) | 否 | 'draft' | status IN ('draft','active','retired') | 无 |
| created_by_user_id | 创建人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| activated_at | 发布时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| retired_at | 退役时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(config_key,version)`
- `CHECK(is_mock = (provider='mock'))`
- `CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))`

## JSONB内部字典

内部属性使用对象内版本或相邻schema_version列；两种方式都不修改既有wire。具体必填键/类型/取值/空值见各表JSONB规则；见docs/database-design/jsonb-schemas.md的七列属性明细。
