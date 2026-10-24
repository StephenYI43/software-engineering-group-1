# 平台业务与管理数据字典（M1）

关联 #48、#69。状态：**七表迁移与认证持久化已在本任务分支实现，真实PostgreSQL测试及进程重启验证通过；待评审合入。**
owner：M1；评审：M5与M6。本表提出的字段不是已接受公共API变更。

## 与现有认证兼容

当前登录响应是userId/role/name，JWT包含sub/role/name/iat/exp/jti；这些字段保持不变。
users.id映射sub/userId；role由user_roles的有效primary项解析；user_profiles.display_name映射name。
S1对外仍是单角色；user_roles预留授权目录但不是“任意用户可切换角色”的功能。
至少一个有效primary角色由账号创建/授权服务事务保证，部分唯一索引只保证“至多一个”。

现有演示账号密码放在合成配置中，尚非数据库账号存储。本设计要求真正持久化时使用安全密码哈希。
auth_sessions按现有jti的摘要定位，不保存原始token，也不改变JWT字段；签发须持久会话成功后才返回token。
解析同时核对签名、有效期、DB会话/撤销状态及当前授权；数据库不可用时不可退回“放行”。
配置DATABASE_URL后会话撤销持久化，退出后重启仍拒绝凭证，已实测。
未配置数据库时仍是旧离线演示，不声称具备跨重启撤销能力。

## 通用规则

引用主键均使用varchar(64)以兼容各域前缀ID。输入按已冻结实体格式校验；外部旧样例短ID不在本PR批量改写。
所有时间为timestamptz(6)，更新时刻由service显式维护。ON UPDATE NO ACTION表示主键不可修改。
禁止为“跑通测试”去掉外键/唯一/CHECK。下列索引/约束是目标，只有迁移与真实DB测试通过后才能标已实现。

## users

- 用途：账号身份与生命周期；平台业务。
- 主键：`id`；索引：username_key 唯一；status 普通索引。
- 来源：平台授权服务/合成seed；读写：本人仅取最小公开资料；账号启停由有权限管理员操作并审计。
- 保留/删除：停用不物理删除；删除申请由独立流程处理跨域引用/匿名化。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名    | 中文名称/业务含义                                  | PostgreSQL类型与长度/精度 | 可空 | 默认值                            | 取值范围/枚举/唯一/CHECK                         | PK/FK/关联与删除/更新规则  |
| ------------- | -------------------------------------------------- | ------------------------- | ---- | --------------------------------- | ------------------------------------------------ | -------------------------- |
| id            | 用户标识；API userId/studentId/teacherId均引用此值 | varchar(64)               | 否   | 无；服务端生成                    | user_+32小写hex；不解析ID授权                    | PK；其他域引用默认RESTRICT |
| username      | 登录名原始展示值                                   | varchar(64)               | 否   | 无                                | CHECK `^[A-Za-z0-9_.-]{1,64}$`；仅ASCII字母数字、下划线、点和连字符；中文显示名放display_name | 无（非键）                 |
| username_key  | 登录名规范化值                                     | varchar(64)               | 否   | 无；由登录名规范化生成            | ASCII登录名统一小写；非ASCII规则变更需独立决策   | UNIQUE(username_key)       |
| password_hash | 密码哈希及算法参数编码                             | text                      | 否   | 无                                | 采用维护中的密码哈希实现；不得为明文或仅快速散列 | 无（非键）                 |
| status        | 账号状态                                           | varchar(16)               | 否   | active                            | CHECK IN(active,disabled)                        | 无（非键）                 |
| created_at    | 创建时间                                           | timestamptz(6)            | 否   | CURRENT_TIMESTAMP                 | UTC                                              | 无（非键）                 |
| updated_at    | 最后修改时间                                       | timestamptz(6)            | 否   | CURRENT_TIMESTAMP；修改时显式更新 | UTC且不早于created_at                            | 无（非键）                 |

## user_profiles

- 用途：资料及教学展示摘要；平台业务。
- 主键：`user_id`；索引：student_number非空唯一。
- 来源：平台授权服务/合成seed；读写：本人最小资料；教师仅在授权花名册内获得StudentSummary；管理员按权限查。
- 保留/删除：资料删除/匿名化按申请执行；不复制到submissions或learning_events。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名     | 中文名称/业务含义         | PostgreSQL类型与长度/精度 | 可空 | 默认值                            | 取值范围/枚举/唯一/CHECK        | PK/FK/关联与删除/更新规则                              |
| -------------- | ------------------------- | ------------------------- | ---- | --------------------------------- | ------------------------------- | ------------------------------------------------------ |
| user_id        | 资料所属用户              | varchar(64)               | 否   | 无                                | 每用户最多一条                  | PK+FK→users.id；ON DELETE CASCADE；ON UPDATE NO ACTION |
| display_name   | 显示名；API name          | varchar(100)              | 否   | 无                                | 长度1..100                      | 无（非键）                                             |
| student_number | 学号；教师/管理员可以为空 | varchar(32)               | 是   | NULL                              | 非空时长度1..32；演示使用合成值 | UNIQUE(student_number)；NULL可多条                     |
| major          | 专业名称                  | varchar(100)              | 是   | NULL                              | 非空时长度1..100                | 无（非键）                                             |
| updated_at     | 资料修改时间              | timestamptz(6)            | 否   | CURRENT_TIMESTAMP；修改时显式更新 | UTC                             | 无（非键）                                             |

## roles

- 用途：角色目录；平台管理。
- 主键：`code`；索引：主键索引。
- 来源：平台授权服务/合成seed；读写：授权服务读取；角色目录变更只经迁移/管理审计。
- 保留/删除：存在分配/历史会话引用时不允许删除。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名  | 中文名称/业务含义    | PostgreSQL类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK        | PK/FK/关联与删除/更新规则 |
| ----------- | -------------------- | ------------------------- | ---- | ----------------- | ------------------------------- | ------------------------- |
| code        | 角色码；兼容JWT role | varchar(16)               | 否   | 无                | CHECK IN(student,teacher,admin) | PK                        |
| name        | 角色中文名称         | varchar(50)               | 否   | 无                | 学生/教师/管理员                | 无（非键）                |
| description | 角色职责说明         | varchar(255)              | 是   | NULL              | 最长255                         | 无（非键）                |
| created_at  | 定义时间             | timestamptz(6)            | 否   | CURRENT_TIMESTAMP | UTC                             | 无（非键）                |

## user_roles

- 用途：用户角色授权关系与授予来源；平台管理。
- 主键：`(user_id,role_code)`；索引：UNIQUE(user_id) WHERE is_primary；role_code,user_id组合索引。
- 来源：平台授权服务/合成seed；读写：显式管理员授权/撤销并审计；学生教师不能提交自报角色。
- 保留/删除：撤销置revoked_at；不删除追责来源；历史授权变更进入audit。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名         | 中文名称/业务含义      | PostgreSQL类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK                        | PK/FK/关联与删除/更新规则                                     |
| ------------------ | ---------------------- | ------------------------- | ---- | ----------------- | ----------------------------------------------- | ------------------------------------------------------------- |
| user_id            | 被授权用户             | varchar(64)               | 否   | 无                | 必须存在用户                                    | PK之一+FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION   |
| role_code          | 角色码                 | varchar(16)               | 否   | 无                | 必须存在角色                                    | PK之一+FK→roles.code；ON DELETE RESTRICT；ON UPDATE NO ACTION |
| is_primary         | 当前API签发的单角色    | boolean                   | 否   | false             | 一个用户至多一条true；revoked_at非空时必须false | 部分UNIQUE(user_id) WHERE is_primary=true                     |
| granted_by_user_id | 授予人；系统seed时为空 | varchar(64)               | 是   | NULL              | 非空必须管理员；自授予须按服务端规则拒绝        | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION          |
| granted_at         | 授予时间               | timestamptz(6)            | 否   | CURRENT_TIMESTAMP | UTC                                             | 无（非键）                                                    |
| revoked_at         | 撤销时间               | timestamptz(6)            | 是   | NULL              | 不早于granted_at；撤销与primary变更同事务       | 无（非键）                                                    |

## auth_sessions

- 用途：会话持久化与退出撤销；平台业务/管理交叉。
- 主键：`id`；索引：jti_digest唯一；user_id,expires_at索引；expires_at清理索引。
- 来源：平台授权服务/合成seed；读写：认证服务读写；用户只退出自己会话；管理员撤销需审计；不向客户端返回摘要。
- 保留/删除：活跃/已撤销会话保留至过期及项目确认的审计期限；不得在过期前清理撤销状态。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名    | 中文名称/业务含义        | PostgreSQL类型与长度/精度 | 可空 | 默认值                | 取值范围/枚举/唯一/CHECK                                                              | PK/FK/关联与删除/更新规则                              |
| ------------- | ------------------------ | ------------------------- | ---- | --------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| id            | 持久会话记录ID           | varchar(64)               | 否   | 无；服务端生成        | authsess_+32小写hex；此记录ID不改变现有JWT格式                                        | PK                                                     |
| jti_digest    | 现有JWT jti的SHA-256摘要 | varchar(64)               | 否   | 无；服务端计算        | 64小写hex；不存原始token                                                              | UNIQUE(jti_digest)                                     |
| user_id       | 会话用户；JWT sub        | varchar(64)               | 否   | 无                    | 必须存在且active                                                                      | FK→users.id；ON DELETE RESTRICT；ON UPDATE NO ACTION   |
| role_code     | 签发角色快照             | varchar(16)               | 否   | 无                    | 签发时为有效primary role；解析时再核验当前授权                                        | FK→roles.code；ON DELETE RESTRICT；ON UPDATE NO ACTION |
| issued_at     | 签发时间                 | timestamptz(6)            | 否   | 无；使用JWT iat对应值 | UTC                                                                                   | 无（非键）                                             |
| expires_at    | 过期时间                 | timestamptz(6)            | 否   | 无；使用JWT exp对应值 | CHECK expires_at>issued_at                                                            | 无（非键）                                             |
| revoked_at    | 退出/撤销时间            | timestamptz(6)            | 是   | NULL                  | 非空即撤销；重启后仍生效                                                              | 无（非键）                                             |
| revoke_reason | 撤销原因                 | varchar(32)               | 是   | NULL                  | CHECK IN(logout,admin_revoke,role_changed,password_changed)或NULL；与撤销时刻同时赋值 | 无（非键）                                             |
| request_id    | 签发请求追踪ID           | varchar(36)               | 否   | 无；服务端生成        | req_+32小写hex；不能采信外部请求自报ID                                                | 无（非键）                                             |

## admin_audit_logs

- 用途：管理员/教师敏感管理动作的追责记录；平台管理。
- 主键：`id`；索引：actor_user_id,occurred_at；target_type,target_id,occurred_at；request_id。
- 来源：平台授权服务/合成seed；读写：服务端追加；管理员按权限只读；普通业务无UPDATE/DELETE接口。
- 保留/删除：保留期限由学校/项目实际要求确认后写进配置；课堂仅用合成记录；日志不可携带完整学生正文。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名    | 中文名称/业务含义                 | PostgreSQL类型与长度/精度 | 可空 | 默认值            | 取值范围/枚举/唯一/CHECK                                                            | PK/FK/关联与删除/更新规则                            |
| ------------- | --------------------------------- | ------------------------- | ---- | ----------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------- |
| id            | 审计记录ID                        | varchar(64)               | 否   | 无；服务端生成    | audit_+32小写hex                                                                    | PK                                                   |
| actor_user_id | 操作者；系统动作/身份失效时可为空 | varchar(64)               | 是   | NULL              | 系统动作用actor_type=system；身份被删除可保留匿名记录                               | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION |
| actor_type    | 操作者类别                        | varchar(16)               | 否   | user              | CHECK IN(user,system)                                                               | 无（非键）                                           |
| action        | 管理动作码                        | varchar(64)               | 否   | 无                | 如user_disabled,role_granted,assignment_graded,config_published；注册清单随实现评审 | 无（非键）                                           |
| target_type   | 目标实体类型                      | varchar(64)               | 否   | 无                | 使用登记的领域实体类型；不能由客户端任意写入                                        | 无（非键）；与target_id为追踪快照                    |
| target_id     | 目标实体ID快照                    | varchar(64)               | 是   | NULL              | 目标尚未创建/操作失败可空；不使用此值判权                                           | 无物理FK；多领域审计且须保留已删除目标记录           |
| result        | 操作结果                          | varchar(16)               | 否   | 无                | CHECK IN(succeeded,failed,denied)                                                   | 无（非键）                                           |
| request_id    | 请求追踪ID                        | varchar(36)               | 否   | 无；服务端生成    | req_+32小写hex                                                                      | 无（非键）                                           |
| details       | 脱敏变更摘要                      | jsonb                     | 否   | {}                | 仅schemaVersion/changedFields/reasonCode；见下文；禁止密钥/token/完整正文           | 无（非键）                                           |
| occurred_at   | 审计发生时间                      | timestamptz(6)            | 否   | CURRENT_TIMESTAMP | UTC                                                                                 | 无（非键）                                           |

## system_config_versions

- 用途：可追溯的系统配置版本；平台管理。
- 主键：`id`；索引：UNIQUE(config_key,version)；UNIQUE(config_key) WHERE status=active。
- 来源：平台授权服务/合成seed；读写：公开只读项按白名单；发布/回滚由管理员服务执行并审计；客户端不可改模型权限。
- 保留/删除：历史版本保留便于回滚，不覆盖已发布版本；禁止保存真实secret值。
- 状态：已在任务分支迁移与真实PostgreSQL测试；待非作者评审合入，未部署。

| 物理字段名         | 中文名称/业务含义    | PostgreSQL类型与长度/精度 | 可空 | 默认值                    | 取值范围/枚举/唯一/CHECK                                    | PK/FK/关联与删除/更新规则                            |
| ------------------ | -------------------- | ------------------------- | ---- | ------------------------- | ----------------------------------------------------------- | ---------------------------------------------------- |
| id                 | 配置版本ID           | varchar(64)               | 否   | 无；服务端生成            | syscfg_+32小写hex                                           | PK                                                   |
| config_key         | 配置项标识           | varchar(100)              | 否   | 无                        | 如upload_limits、session_policy；与version组合唯一          | UNIQUE(config_key,version)之一                       |
| version            | 递增版本号           | integer                   | 否   | 无；服务端在锁/事务内生成 | CHECK version>0；不能并发MAX+1不加保护                      | UNIQUE(config_key,version)之一                       |
| status             | 配置版本状态         | varchar(16)               | 否   | draft                     | CHECK IN(draft,active,retired)；同key至多一个active         | 部分UNIQUE(config_key) WHERE status=active           |
| value              | 有版本的配置值       | jsonb                     | 否   | 无                        | 对象；schemaVersion必填；按config_key校验属性，不能任意JSON | 无（非键）                                           |
| created_by_user_id | 创建者；系统seed可空 | varchar(64)               | 是   | NULL                      | 非空须授权管理员                                            | FK→users.id；ON DELETE SET NULL；ON UPDATE NO ACTION |
| created_at         | 版本创建时间         | timestamptz(6)            | 否   | CURRENT_TIMESTAMP         | UTC                                                         | 无（非键）                                           |
| activated_at       | 发布时间             | timestamptz(6)            | 是   | NULL                      | draft时NULL；active/retired时必须非空；发布/退役与audit同事务；不得伪造发布时间 | 无（非键）                                           |

本批明确D1/D2：用户名限制与#75实际CHECK一致；配置只允许draft→active→retired，未发布草稿不可直接退役，继续保留draft或经授权清理。此处不改变#75代码。
本批参考schema.sql另补schemaVersion不接受JSON null的CHECK；#75现有表达式可能因SQL UNKNOWN放过该值，须由M1后续新增迁移修正，不声称原测试已覆盖。

## JSONB内部字典

admin_audit_logs.details不是自由正文容器。默认空对象表示没有额外摘要；非空对象必须含schemaVersion，服务端白名单构建。

| 物理字段名              | 中文名称/业务含义           | PostgreSQL类型与长度/精度                    | 可空                          | 默认值                      | 取值范围/枚举/唯一/CHECK                                 | PK/FK/关联与删除/更新规则 |
| ----------------------- | --------------------------- | -------------------------------------------- | ----------------------------- | --------------------------- | -------------------------------------------------------- | ------------------------- |
| details.schemaVersion   | 审计摘要版本                | jsonb内string，最长16字符                    | 非空details时否               | 无；显式赋1.0               | 1.0                                                      | 无（非键）                |
| details.changedFields   | 被修改字段名列表            | jsonb内string数组，最多50项，每项最长100字符 | 是                            | 缺省                        | 只记录字段名，不记录敏感新旧值                           | 无（非键）                |
| details.reasonCode      | 原因码                      | jsonb内string，最长64字符                    | 是                            | 缺省                        | 登记的原因枚举；不得是任意学生正文                       | 无（非键）                |
| value.schemaVersion     | 配置对象版本                | jsonb内string，最长16字符                    | 否                            | 无；显式赋1.0               | 1.0                                                      | 无（非键）                |
| value.maxUploadBytes    | upload_limits最大上传字节数 | jsonb内integer                               | config_key=upload_limits时否  | 无；种子配置显式赋值        | 大于0，实施任务验证上界                                  | 无（非键）                |
| value.allowedMimeTypes  | upload_limits允许类型       | jsonb内string数组                            | config_key=upload_limits时否  | 无                          | 非空、去重的白名单；不能只信浏览器MIME                   | 无（非键）                |
| value.sessionTtlSeconds | session_policy凭证寿命      | jsonb内integer                               | config_key=session_policy时否 | 86400，仅与当前默认策略对应 | 取当前AuthSettings实施校验范围；不能借配置放宽未授权能力 | 无（非键）                |

配置支持的config_key仅先设计upload_limits/session_policy；其他key须先补内部字典再接受写入。
JSON条件/范围应由版本化schema严格校验；通用jsonb对象/类型边界可另加数据库CHECK。
密钥放环境或受控secret存储；若未来增加引用，仅存secretRef及版本，不存密钥值。

## 必须保留的验收反例

1. 两个用户名大小写规范化后相同，第二次INSERT因唯一约束失败。
2. 同用户两个is_primary=true在事务中不能并存；撤销角色同时清primary，认证重新判权。
3. 会话退出成功后重启API/PG仍拒绝同token；原始token不能出现在库/日志。
4. 不存在user/role的关系被FK拒绝；admin角色不能由学生请求体自报获得。
5. 一个配置key不能有两个active版本；并发发布在锁/事务内明确胜负。
6. 成功管理变更与成功audit同事务；事务回滚无成功记录。失败/拒绝审计使用受控单独事务保存，不能被业务回滚一起抹掉，也不能假称业务成功。
7. 查询审计/资料必须先授权；返回最小信息，不把摘要的JSON原样作为完整学生资料展示。
