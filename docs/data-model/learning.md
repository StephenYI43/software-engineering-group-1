# M5 业务与管理数据字典

owner：M5；本批由M1补全设计，原owner负责后续实现；日期2026-10-24。
关联#69、#42、#71、#72、#65；状态：设计草案，待非作者评审，未接应用迁移/repository。

物理结构唯一源为scripts/database-design/domain_model.py；生成DDL在docs/database-design/schema.sql。现有API字段不因新增列自动改变；公共增量须另经schema和消费者确认。

## courses

- 用途：课程内容；业务。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

teacherId映射teacher_user_id；姓名经平台组合，人数/章节数查询聚合，不存冗余计数。教师身份由service验证。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成course_+32hex；API按不透明ID处理 | PK |
| title | 课程名 | varchar(100) | 否 | 无；调用方提供 | length(btrim(title)) BETWEEN 1 AND 100 | 无 |
| description | 课程简介 | varchar(2000) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| subject | 学科 | varchar(32) | 否 | 无；调用方提供 | subject IN ('math','physics','chemistry','english','cs','other') | 无 |
| cover_image_url | 封面地址 | varchar(2048) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| teacher_user_id | 课程主讲教师 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

## classes

- 用途：教学班；业务与管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

course与class分离；同课程可有多班。主讲变更与teaching_assignments同事务并审计，不能只改一边。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成class_+32hex；API按不透明ID处理 | PK |
| course_id | 所属课程 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| teacher_user_id | 主讲教师 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| title | 班级名 | varchar(100) | 否 | 无；调用方提供 | length(btrim(title)) > 0 | 无 |
| semester | 学期 | varchar(32) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(id, course_id)`

## enrollments

- 用途：学生选课及班级归属历史；访问关系管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_enrollments_active ON enrollments(student_user_id,class_id) WHERE left_at IS NULL
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

同人同课可多班；只禁止同班重复有效关系。转班关闭旧时间区间再建新关系，保留历史。表/公共service归M5，选课HTTP鉴权入口归M1；不建第二套ACL表。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成enrollment_+32hex；API按不透明ID处理 | PK |
| student_user_id | 学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| class_id | 教学班 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| joined_at | 加入时间 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| left_at | 退出时间 | timestamptz(6) | 是 | NULL | left_at IS NULL OR left_at >= joined_at | 无 |
| granted_by_user_id | 操作人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |

## teaching_assignments

- 用途：教师授课授权；访问关系管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_teaching_primary ON teaching_assignments(class_id) WHERE revoked_at IS NULL
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

S1单主讲，每班至多一条有效授课；至少一条由建班service事务保证。has_course_access仅查有效关系，不信客户端role。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成teaching_+32hex；API按不透明ID处理 | PK |
| teacher_user_id | 教师 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| class_id | 教学班 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| granted_at | 授予时间 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| revoked_at | 撤销时间 | timestamptz(6) | 是 | NULL | revoked_at IS NULL OR revoked_at >= granted_at | 无 |
| granted_by_user_id | 授予人 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE SET NULL |

## chapters

- 用途：课程章节；业务。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

API order映射同名带引号列；删除不重排。关联文档同课程由service检查；删除课件可以清关联，但不删除历史引用。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成chapter_+32hex；API按不透明ID处理 | PK |
| course_id | 所属课程 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| title | 章节名 | varchar(100) | 否 | 无；调用方提供 | length(btrim(title)) > 0 | 无 |
| order | 课程内顺序 | integer | 否 | 无；调用方提供 | "order" >= 1 | 无 |
| description | 章节简介 | text | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| document_id | 关联课件版本 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→documents.id；ON DELETE SET NULL |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(course_id, "order")`
- `UNIQUE(id,course_id)`

## assignments

- 用途：作业发布与答案管理；业务与管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

published_at为NULL是草稿，学生不可见；发布后course/class与题目版本不可静默改写。班级为空只表示课程级作业，不自动复制到每个班。answer_key不进入学生投影，连NULL字段也不返回；public_question补公开选项是待确认API增量。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成assignment_+32hex；API按不透明ID处理 | PK |
| course_id | 课程 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| class_id | 教学班 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| chapter_id | 章节 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→chapters.id；ON DELETE RESTRICT |
| teacher_user_id | 发布教师 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| title | 作业名 | varchar(100) | 否 | 无；调用方提供 | length(btrim(title)) > 0 | 无 |
| description | 题面说明 | varchar(8000) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| question_type | 题型 | varchar(32) | 否 | 无；调用方提供 | question_type IN ('single_choice','multiple_choice','fill_blank','short_answer','proof') | 无 |
| public_question | 学生可见题目与选项 | jsonb | 否 | '{"schemaVersion":"1.0","options":[]}'::jsonb | jsonb_typeof(public_question) = 'object' AND (public_question->>'schemaVersion') IS NOT DISTINCT FROM '1.0'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| answer_key | 教师私有标准答案 | jsonb | 是 | NULL | jsonb_typeof(answer_key) = 'object'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| answer_key_schema_version | 答案键外置版本 | varchar(16) | 否 | '1.0' | answer_key_schema_version = '1.0' | 无 |
| max_score | 满分 | integer | 否 | 无；调用方提供 | max_score >= 1 | 无 |
| due_at | 截止时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| published_at | 发布时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(id,course_id)`
- `UNIQUE(id,class_id)`
- `FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT`
- `FOREIGN KEY(chapter_id,course_id) REFERENCES chapters(id,course_id) ON DELETE RESTRICT`

JSONB版本及属性：
- `public_question`：对象schemaVersion=1.0；options数组0..26项，每项{key:1..8字符,text:1..1000字符}；单选/多选必非空且key唯一。
- `answer_key`：沿用现有wire，无内嵌版本；按question_type及列级版本规则解码：options是唯一选项key数组；acceptableBlanks是等价答案文本数组，服务端限长/限项。未知键拒绝；主观题可NULL。

## submissions

- 用途：作业提交与批阅结果；业务与管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

S1同作业每生一份。相同键/参数返回原对象，换参数409；不同键第二次提交409。score<=作业max_score、学生/作业class相等及批阅权限由锁内service检查。编辑提交PATCH路径/重判语义未冻结，revision只预留并发控制，不声称编辑接口存在。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成submission_+32hex；API按不透明ID处理 | PK |
| assignment_id | 作业 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→assignments.id；ON DELETE RESTRICT |
| student_user_id | 提交学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 提交时课程快照 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| class_id | 提交时班级快照 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| answer | 学生答案 | jsonb | 否 | 无；调用方提供 | jsonb_typeof(answer) IN ('object','string'); 保留现有object或string wire；版本由answer_schema_version外置 | 无 |
| answer_schema_version | 答案存储版本 | varchar(16) | 否 | '1.0' | answer_schema_version = '1.0' | 无 |
| is_correct | 判分对错 | boolean | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| score | 得分 | integer | 是 | NULL | score IS NULL OR score >= 0 | 无 |
| graded_by | 判分来源 | varchar(32) | 否 | 无；调用方提供 | graded_by IN ('auto','teacher','ai_assisted') | 无 |
| graded_at | 批阅时间 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| idempotency_key | 首次提交重试键 | varchar(128) | 否 | 无；调用方提供 | length(idempotency_key) > 0 | 无 |
| request_hash | 规范化请求摘要 | varchar(64) | 否 | 无；调用方提供 | request_hash ~ '^[0-9a-f]{64}$' | 无 |
| revision | 乐观锁版本 | integer | 否 | 1 | revision >= 1 | 无 |
| submitted_at | 首次提交时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(assignment_id,student_user_id)`
- `UNIQUE(student_user_id,idempotency_key)`
- `FOREIGN KEY(assignment_id,course_id) REFERENCES assignments(id,course_id) ON DELETE RESTRICT`
- `FOREIGN KEY(assignment_id,class_id) REFERENCES assignments(id,class_id) ON DELETE RESTRICT`
- `CHECK ((graded_at IS NULL AND is_correct IS NULL AND score IS NULL) OR graded_at IS NOT NULL)`

JSONB版本及属性：
- `answer`：answer_schema_version=1.0；string为1..8000字符；对象仅允许options:string[]或blanks:string[]，按题型校验，数组大小与题目匹配；不得包含isCorrect/score/gradedBy/answerKey。

## mistakes

- 用途：个人错题快照；业务。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_mistakes_submission ON mistakes(student_user_id,submission_id) WHERE submission_id IS NOT NULL；CREATE UNIQUE INDEX uq_mistakes_turn ON mistakes(student_user_id,source_turn_id) WHERE source_turn_id IS NOT NULL
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

只在错误提交或学生明确标记时收录；错误批阅重试不新增，resolved不硬删。无来源锚点的手动自由文本需service幂等键，未定义通用重复正文判定。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成mistake_+32hex；API按不透明ID处理 | PK |
| student_user_id | 所属学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| chapter_id | 章节 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→chapters.id；ON DELETE RESTRICT |
| assignment_id | 作业 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→assignments.id；ON DELETE RESTRICT |
| submission_id | 错误提交 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→submissions.id；ON DELETE RESTRICT |
| source_turn_id | 主动标记答疑轮次 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→tutoring_turns.id；ON DELETE RESTRICT |
| source | 收录来源 | varchar(32) | 否 | 无；调用方提供 | source IN ('wrong_submission','manual') | 无 |
| question | 题目快照 | jsonb | 否 | 无；调用方提供 | jsonb_typeof(question) = 'object'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| student_answer | 答案快照 | jsonb | 是 | NULL | student_answer IS NULL OR jsonb_typeof(student_answer) IN ('object','string') | 无 |
| snapshot_schema_version | 快照解码版本 | varchar(16) | 否 | '1.0' | snapshot_schema_version = '1.0' | 无 |
| note | 学生备注 | varchar(500) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| status | 复习状态 | varchar(32) | 否 | 'active' | status IN ('active','resolved','archived') | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

JSONB版本及属性：
- `question`：外置snapshot_schema_version=1.0；键stem:string<=4000、questionType:冻结作业枚举或tutoring_question、options:null或公开选项数组、attachmentUrl:null或受控地址；未知键拒绝。不向原wire硬加schemaVersion。
- `student_answer`：同submissions.answer的1.0解码规则；可NULL，绝不混入正确答案。

## study_plans

- 用途：预习复习计划；业务。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

项目首版承载预习/复习/备考清单；1..20项由service同事务验证。source=tutoring必须通过M3归属校验取用建议，不信前端转存正文。最后阅读章节由chapter_viewed事实派生，不另建偏好字段。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成plan_+32hex；API按不透明ID处理 | PK |
| student_user_id | 所属学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| title | 计划名 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| course_id | 课程 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| chapter_id | 章节 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→chapters.id；ON DELETE RESTRICT |
| source_turn_id | 授权导学建议来源 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→tutoring_turns.id；ON DELETE RESTRICT |
| source | 来源 | varchar(32) | 否 | 无；调用方提供 | source IN ('tutoring','manual','imported') | 无 |
| status | 计划状态 | varchar(32) | 否 | 'active' | status IN ('active','completed','archived') | 无 |
| due_at | 整体截止 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

## plan_items

- 用途：计划条目；业务。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

关联资源必须属于当前学生授权范围；完成状态翻转才发事件，重复PATCH不重发。记忆曲线与考试押题算法不在S1实现范围。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成plan_item_+32hex；API按不透明ID处理 | PK |
| plan_id | 所属计划 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→study_plans.id；ON DELETE CASCADE |
| content | 任务内容 | varchar(500) | 否 | 无；调用方提供 | length(btrim(content)) > 0 | 无 |
| order | 条目顺序 | integer | 否 | 无；调用方提供 | "order" >= 1 | 无 |
| status | 完成状态 | varchar(32) | 否 | 'pending' | status IN ('pending','done') | 无 |
| due_at | 条目截止 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| chapter_id | 关联章节 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→chapters.id；ON DELETE RESTRICT |
| knowledge_point | 知识点标签 | varchar(200) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| related_mistake_id | 关联错题 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→mistakes.id；ON DELETE RESTRICT |
| related_assignment_id | 关联作业 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→assignments.id；ON DELETE RESTRICT |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| updated_at | 修改时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | updated_at >= created_at; service显式更新，不是自动ON UPDATE | 无 |

表级约束：
- `UNIQUE(plan_id,"order")`

## reminders

- 用途：站内截止与复习提醒；业务与管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；组合唯一键见约束
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

due/type/目标生成稳定dedup_key，扫描重试不重复提醒；mistake_review_due为设计保留，S1不声称智能间隔复习已实现。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成reminder_+32hex；API按不透明ID处理 | PK |
| student_user_id | 接收学生 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| plan_id | 计划 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→study_plans.id；ON DELETE RESTRICT |
| assignment_id | 作业 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→assignments.id；ON DELETE RESTRICT |
| type | 提醒类型 | varchar(32) | 否 | 无；调用方提供 | type IN ('plan_due','assignment_due','mistake_review_due') | 无 |
| title | 提醒标题 | varchar(100) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| body | 提醒正文 | varchar(500) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| due_at | 关联截止 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| is_read | 是否已读 | boolean | 否 | false | 按类型边界；跨行/权限由service验证 | 无 |
| read_at | 阅读时刻 | timestamptz(6) | 是 | NULL | 按类型边界；跨行/权限由service验证 | 无 |
| dedup_key | 扫描生成去重键 | varchar(128) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| created_at | 创建时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |

表级约束：
- `UNIQUE(student_user_id,dedup_key)`
- `CHECK (is_read = (read_at IS NOT NULL))`

## learning_events

- 用途：不可变学习事件与幂等事实；业务事实与管理。
- owner：M5；M1补全，相关提供方/消费者交叉评审。
- 索引：主键与FK查询索引；CREATE UNIQUE INDEX uq_learning_intent ON learning_events(user_id,idempotency_key) WHERE idempotency_key IS NOT NULL；CREATE INDEX ix_events_order ON learning_events(occurred_at,id)；CREATE INDEX ix_events_class_time ON learning_events(class_id,occurred_at)
- 权限：service先验证当前principal、角色、资源归属；后台不因admin标签自动取得对话全文；无生产Mock放行。
- 保留：演示仅合成数据，项目验收后清理；真实数据采集前须配置获批准的保留期、撤回与清理流程，未确认不接真实资料。
- 状态：设计草案；本批SQL结构验证不等于业务持久化完成。

id映射wire eventId；业务与事件同Session事务，幂等命中不重发。class_id为受信上下文/作业/提交的发生时快照，不向wire 1.0偷偷加字段；公开feed元数据与契约修订另评。多班无明确上下文时class_id=NULL，只入个人/课程汇总，不复制到各班。不可把occurred_at或自增号当提交水位；M6用未处理账本补扫。

| 物理字段名 | 中文名称/含义 | PostgreSQL类型及长度/精度 | 可空 | 默认值 | 取值范围/唯一/CHECK | PK/FK/关联与删除规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | 记录标识 | varchar(64) | 否 | 无；调用方提供 | length(id) > 0; 服务端生成event_+32hex；API按不透明ID处理 | PK |
| event_type | 事件类型 | varchar(32) | 否 | 无；调用方提供 | event_type IN ('assignment_submitted','assignment_graded','mistake_recorded','mistake_resolved','study_plan_saved','plan_item_completed','reminder_triggered','chapter_viewed') | 无 |
| user_id | 学生主体 | varchar(64) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | FK→users.id；ON DELETE RESTRICT |
| course_id | 课程 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→courses.id；ON DELETE RESTRICT |
| class_id | 发生时教学班快照 | varchar(64) | 是 | NULL | 按类型边界；跨行/权限由service验证 | FK→classes.id；ON DELETE RESTRICT |
| occurred_at | 实际发生时刻 | timestamptz(6) | 否 | 无；调用方提供 | 按类型边界；跨行/权限由service验证 | 无 |
| recorded_at | 数据库接受时刻 | timestamptz(6) | 否 | CURRENT_TIMESTAMP | 按类型边界；跨行/权限由service验证 | 无 |
| trace_id | 平台请求号 | varchar(36) | 否 | 无；调用方提供 | trace_id ~ '^req_[0-9a-f]{32}$' | 无 |
| schema_version | 事件envelope版本 | varchar(16) | 否 | '1.0' | schema_version = '1.0' | 无 |
| payload | 事件特有数据 | jsonb | 否 | 无；调用方提供 | jsonb_typeof(payload) = 'object'; 内部属性与合法键按本域JSONB字典校验 | 无 |
| idempotency_key | 章节浏览动作幂等键 | varchar(128) | 是 | NULL | idempotency_key IS NULL OR length(idempotency_key)>0 | 无 |
| request_hash | 浏览请求摘要 | varchar(64) | 是 | NULL | request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$' | 无 |

表级约束：
- `FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT`
- `CHECK(class_id IS NULL OR course_id IS NOT NULL)`
- `CHECK(event_type <> 'chapter_viewed' OR (course_id IS NOT NULL AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL))`

JSONB版本及属性：
- `payload`：版本位于envelope.schema_version=1.0，不要求payload再加版本；按event_type白名单：chapter_viewed仅chapterId；assignment_submitted含submissionId/assignmentId/questionType及可空isCorrect/score；assignment_graded含submissionId/isCorrect/可空score；mistake_recorded含mistakeId/source/可空assignmentId/chapterId；mistake_resolved仅mistakeId；study_plan_saved含planId/source/itemsCount(1..20)；plan_item_completed含planId/itemId；reminder_triggered含reminderId/type/dueAt。字段camelCase，未知/缺必填拒绝。

## JSONB内部字典

内部属性使用对象内版本或相邻schema_version列；两种方式都不修改既有wire。具体必填键/类型/取值/空值见各表JSONB规则；见docs/database-design/jsonb-schemas.md的七列属性明细。
