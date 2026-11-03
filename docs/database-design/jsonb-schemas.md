# JSONB属性七要素与版本位置

所有下列属性都是设计约束，除平台已验证子集外尚待service校验实现；数据库CHECK不替代所有嵌套结构校验。@前缀表示外置列元数据而不是JSON键，不修改既有wire。

## admin_audit_logs.details

版本位置：空对象允许；非空时details.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 审计摘要版本 | string(16) | 非空对象时 | 无 | 1.0 | 无 |
| changedFields | 改动字段名 | string[0..50] | 否 | 无 | 每项1..100字符，只记字段名 | 无 |
| reasonCode | 原因码 | string(64) | 否 | 无 | 白名单，不含正文/密钥 | 无 |

## system_config_versions.value

版本位置：value.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| maxUploadBytes | 上传大小限制 | integer | upload_limits时 | 无 | 大于0，上限由部署批准 | 无 |
| allowedMimeTypes | 媒体类型白名单 | string[] | upload_limits时 | 无 | 非空、去重；仍须实际文件校验 | 无 |
| sessionTtlSeconds | 会话秒数 | integer | session_policy时 | 86400 | 与AuthSettings范围一致，不放宽权限 | 无 |

## assignments.public_question

版本位置：public_question.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| options | 学生可见选项 | object[0..26] | 是 | [] | 选择题非空，非选择题空数组 | 无 |
| options[].key | 选项代码 | string(8) | 有选项时 | 无 | 同题唯一，不含答案提示 | 无 |
| options[].text | 选项正文 | string(1000) | 有选项时 | 无 | 1..1000字符，不执行HTML/命令 | 无 |

## assignments.answer_key

版本位置：外置列answer_key_schema_version=1.0；原wire不增加键

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| @answer_key_schema_version | 外置版本元数据 | varchar(16) | 列必填 | 1.0 | 不属于JSON内部键 | assignments.answer_key_schema_version |
| options | 正确选项代码 | string[] | 选择题时 | 无 | 单选恰1项，多选非空唯一，须命中公开选项key | 无 |
| acceptableBlanks | 填空等价答案 | string[] | 填空题时 | 无 | 每项1..1000字符，按题目空数校验；上限100项 | 无 |

## submissions.answer

版本位置：外置列answer_schema_version=1.0

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| @answer_schema_version | 外置版本元数据 | varchar(16) | 列必填 | 1.0 | 不向原wire添加schemaVersion | submissions.answer_schema_version |
| $ | 答案根值 | object或string | 是 | 无 | string 1..8000字符；object按题型 | 无 |
| options | 所选代码 | string[0..26] | 选择题时 | 无 | 代码唯一且属于该题 | 无 |
| blanks | 填空答案 | string[1..100] | 填空时 | 无 | 每项<=1000字符，数量与题目匹配 | 无 |

## mistakes.question

版本位置：外置列snapshot_schema_version=1.0

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| @snapshot_schema_version | 快照版本 | varchar(16) | 列必填 | 1.0 | 不属于JSON键 | mistakes.snapshot_schema_version |
| stem | 题干 | string(4000) | 是 | 无 | 1..4000字符 | 无 |
| questionType | 题型 | string(32) | 是 | 无 | 五种作业题型或tutoring_question | 无 |
| options | 选项快照 | object[]或null | 是 | null | 同public_question.options，不含正确答案 | 无 |
| attachmentUrl | 受控附件地址 | string(2048)或null | 否 | null | 鉴权后生成/净化，拒绝可执行协议 | 无 |

## mistakes.student_answer

版本位置：与question共用snapshot_schema_version=1.0

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| $ | 答错时答案快照 | object/string/null | 否 | NULL | 同submissions.answer的1.0结构；NULL是未知，不是空答案 | mistakes.snapshot_schema_version |

## learning_events.payload

版本位置：envelope列schema_version=1.0；payload不加版本键

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| @schema_version | 事件envelope版本 | varchar(16) | 列必填 | 1.0 | 外置版本，不改变wire | learning_events.schema_version |
| chapterId | 浏览或错题章节 | string(64)或null | chapter_viewed时 | 无 | 浏览时非空且属course；错题可空 | chapters.id，service核验 |
| submissionId | 提交标识 | string(64) | 提交/批阅时 | 无 | 按版本校验 | submissions.id |
| assignmentId | 作业标识 | string(64)或null | assignment_submitted时 | 无 | 错题来源可空 | assignments.id |
| questionType | 题型 | string(32) | assignment_submitted时 | 无 | 冻结作业枚举 | 无 |
| isCorrect | 判分结果 | boolean或null | 批阅时 | null | 主观未判NULL，不冒充false | 无 |
| score | 得分 | integer或null | 否 | null | 0..max_score或NULL | 无 |
| mistakeId | 错题标识 | string(64) | 错题事件时 | 无 | 按版本校验 | mistakes.id |
| source | 错题或计划来源 | string(32) | recorded/saved时 | 无 | 按event_type枚举 | 无 |
| planId | 计划标识 | string(64) | 计划/计划项事件时 | 无 | 按版本校验 | study_plans.id |
| itemsCount | 计划条目数 | integer | study_plan_saved时 | 无 | 1..20 | 无 |
| itemId | 完成计划项 | string(64) | plan_item_completed时 | 无 | 按版本校验 | plan_items.id |
| reminderId | 提醒标识 | string(64) | reminder_triggered时 | 无 | 按版本校验 | reminders.id |
| type | 提醒类型 | string(32) | 提醒事件时 | 无 | 冻结三种提醒类型 | 无 |
| dueAt | 提醒关联截止 | ISO8601 UTC | 提醒事件时 | 无 | 合法UTC时刻 | 无 |

## tutoring_turns.follow_ups

版本位置：follow_ups.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| items | 追问建议 | string[0..3] | 是 | [] | 每项1..200字符；未完成不当完整建议 | 无 |

## document_import_jobs.pages_without_text

版本位置：pages_without_text.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| pages | 无文字页号 | integer[] | 是 | [] | 页号>=1、升序去重；只有成功解析才作最终报告 | 无 |

## avatar_config_versions.config

版本位置：config.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| avatarAssetKey | 形象资源键 | string(512) | 是 | 无 | 受控资源，不是任意路径/URL | 无 |
| subjectStyle | 学科风格 | string(32) | 是 | other | math/physics/chemistry/english/cs/other | 无 |
| tone | 语气风格 | string(16) | 是 | gentle | gentle/neutral/strict | 无 |
| defaultEmotion | 默认情绪 | string(16) | 是 | neutral | neutral/encouraging/thinking/celebrating | 无 |
| defaultAction | 默认动作 | string(16) | 是 | idle | idle/nod/point/write | 无 |

## media_jobs.params

版本位置：params.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| language | 识别语言 | string(16) | 否 | 缺省 | zh-CN/en-US | 无 |
| voiceCode | 受控音色代码 | string(64) | 否 | 无 | 服务端白名单，不是任意URL | 无 |
| rate | 语速 | number | 否 | 1.0 | 0.5..2.0，具体provider进一步校验 | 无 |

## analytics_report_snapshots.metrics

版本位置：metrics.schemaVersion

| 属性路径 | 中文名称/含义 | 类型及长度 | 必填或可空 | 默认值 | 范围与约束 | 关联与版本位置 |
| --- | --- | --- | --- | --- | --- | --- |
| schemaVersion | 内部结构版本 | string(16) | 是 | 显式1.0 | 固定1.0且不为JSON null | 无 |
| dataState | 数据完整性 | string(16) | 是 | 无 | unknown/partial/known | 无 |
| studySeconds | 学习秒数 | integer或null | 是 | null | >=0；unknown必须NULL | 无 |
| knowledgePoints | 知识点雷达指标 | object[0..100] | 是 | [] | 每项有key/mastery/sampleCount/dataState | 无 |
| knowledgePoints[].key | 知识点标签 | string(100) | 有项时 | 无 | 非空 | 无 |
| knowledgePoints[].mastery | 掌握度 | number或null | 有项时 | null | 0..1或未知NULL；不能凭空填分 | 无 |
| knowledgePoints[].sampleCount | 指标样本 | integer | 有项时 | 0 | >=0 | 无 |
| knowledgePoints[].dataState | 指标状态 | string(16) | 有项时 | unknown | unknown/partial/known | 无 |
| weakSubjects | 薄弱学科 | string[] | 是 | [] | 受控学科代码，未知不编造 | 无 |
| suggestions | 诊断建议 | string[0..10] | 是 | [] | 每项<=500字符，需样本依据、无敏感正文 | 无 |
