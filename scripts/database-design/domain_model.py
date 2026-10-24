"""Reviewable database DESIGN, not application ORM or an Alembic migration.

The dictionaries, JSON inventory and reference DDL are generated from this file.
Platform tables are read from the existing #75 ORM without changing that code.
"""

from dataclasses import asdict, dataclass, field


@dataclass
class Column:
    name: str
    type: str
    meaning: str
    nullable: bool = False
    default: str | None = None
    check: str | None = None
    reference: str | None = None
    delete: str = "RESTRICT"
    primary: bool = False
    rule: str = ""


@dataclass
class Table:
    name: str
    meaning: str
    owner: str
    category: str
    columns: list[Column]
    constraints: list[str] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    rules: str = ""
    json: dict = field(default_factory=dict)
    status: str = "本批补全设计；未接应用迁移和repository"

    def export(self):
        return asdict(self)


def c(name, type, meaning, **kw):
    return Column(name, type, meaning, **kw)


def ident(prefix):
    return c("id", "varchar(64)", "记录标识", primary=True,
             check="length(id) > 0", rule=f"服务端生成{prefix}_+32hex；API按不透明ID处理")


def fk(name, table, meaning, nullable=False, delete="RESTRICT", key="id"):
    return c(name, "varchar(64)", meaning, nullable=nullable,
             reference=f"{table}.{key}", delete=delete)


def times(updated=True):
    out = [c("created_at", "timestamptz(6)", "创建时刻", default="CURRENT_TIMESTAMP")]
    if updated:
        out.append(c("updated_at", "timestamptz(6)", "修改时刻", default="CURRENT_TIMESTAMP",
                     check="updated_at >= created_at", rule="service显式更新，不是自动ON UPDATE"))
    return out


def enum(name, meaning, values, default=None, nullable=False):
    quoted = ",".join("'" + v + "'" for v in values.split("/"))
    return c(name, "varchar(32)", meaning, nullable=nullable,
             default=None if default is None else "'"+default+"'",
             check=f"{name} IN ({quoted})")


def obj(name, meaning, default=None, version=True, nullable=False):
    check = f"jsonb_typeof({name}) = 'object'"
    if version:
        check += f" AND ({name}->>'schemaVersion') IS NOT DISTINCT FROM '1.0'"
    return c(name, "jsonb", meaning, nullable=nullable, default=default,
             check=check, rule="内部属性与合法键按本域JSONB字典校验")


TABLES = []


def t(*args, **kw):
    item = Table(*args, **kw)
    TABLES.append(item)
    return item


t("courses", "课程内容", "M5", "业务", [
    ident("course"), c("title", "varchar(100)", "课程名", check="length(btrim(title)) BETWEEN 1 AND 100"),
    c("description", "varchar(2000)", "课程简介", nullable=True),
    enum("subject", "学科", "math/physics/chemistry/english/cs/other"),
    c("cover_image_url", "varchar(2048)", "封面地址", nullable=True),
    fk("teacher_user_id", "users", "课程主讲教师"), *times()],
    rules="teacherId映射teacher_user_id；姓名经平台组合，人数/章节数查询聚合，不存冗余计数。教师身份由service验证。")
t("classes", "教学班", "M5", "业务与管理", [
    ident("class"), fk("course_id", "courses", "所属课程"),
    fk("teacher_user_id", "users", "主讲教师"),
    c("title", "varchar(100)", "班级名", check="length(btrim(title)) > 0"),
    c("semester", "varchar(32)", "学期", nullable=True), *times()],
    constraints=["UNIQUE(id, course_id)"],
    rules="course与class分离；同课程可有多班。主讲变更与teaching_assignments同事务并审计，不能只改一边。")
t("enrollments", "学生选课及班级归属历史", "M5", "访问关系管理", [
    ident("enrollment"), fk("student_user_id", "users", "学生"), fk("class_id", "classes", "教学班"),
    c("joined_at", "timestamptz(6)", "加入时间", default="CURRENT_TIMESTAMP"),
    c("left_at", "timestamptz(6)", "退出时间", nullable=True, check="left_at IS NULL OR left_at >= joined_at"),
    fk("granted_by_user_id", "users", "操作人", nullable=True, delete="SET NULL")],
    indexes=["CREATE UNIQUE INDEX uq_enrollments_active ON enrollments(student_user_id,class_id) WHERE left_at IS NULL"],
    rules="同人同课可多班；只禁止同班重复有效关系。转班关闭旧时间区间再建新关系，保留历史。表/公共service归M5，选课HTTP鉴权入口归M1；不建第二套ACL表。")
t("teaching_assignments", "教师授课授权", "M5", "访问关系管理", [
    ident("teaching"), fk("teacher_user_id", "users", "教师"), fk("class_id", "classes", "教学班"),
    c("granted_at", "timestamptz(6)", "授予时间", default="CURRENT_TIMESTAMP"),
    c("revoked_at", "timestamptz(6)", "撤销时间", nullable=True, check="revoked_at IS NULL OR revoked_at >= granted_at"),
    fk("granted_by_user_id", "users", "授予人", nullable=True, delete="SET NULL")],
    indexes=["CREATE UNIQUE INDEX uq_teaching_primary ON teaching_assignments(class_id) WHERE revoked_at IS NULL"],
    rules="S1单主讲，每班至多一条有效授课；至少一条由建班service事务保证。has_course_access仅查有效关系，不信客户端role。")
t("chapters", "课程章节", "M5", "业务", [
    ident("chapter"), fk("course_id", "courses", "所属课程"),
    c("title", "varchar(100)", "章节名", check="length(btrim(title)) > 0"),
    c("order", "integer", "课程内顺序", check='"order" >= 1'),
    c("description", "text", "章节简介", nullable=True),
    fk("document_id", "documents", "关联课件版本", nullable=True, delete="SET NULL"), *times()],
    constraints=['UNIQUE(course_id, "order")', "UNIQUE(id,course_id)"],
    rules="API order映射同名带引号列；删除不重排。关联文档同课程由service检查；删除课件可以清关联，但不删除历史引用。")
t("assignments", "作业发布与答案管理", "M5", "业务与管理", [
    ident("assignment"), fk("course_id", "courses", "课程"), fk("class_id", "classes", "教学班", nullable=True),
    fk("chapter_id", "chapters", "章节", nullable=True), fk("teacher_user_id", "users", "发布教师"),
    c("title", "varchar(100)", "作业名", check="length(btrim(title)) > 0"),
    c("description", "varchar(8000)", "题面说明", nullable=True),
    enum("question_type", "题型", "single_choice/multiple_choice/fill_blank/short_answer/proof"),
    obj("public_question", "学生可见题目与选项", "'{\"schemaVersion\":\"1.0\",\"options\":[]}'::jsonb"),
    obj("answer_key", "教师私有标准答案", nullable=True, version=False),
    c("answer_key_schema_version", "varchar(16)", "答案键外置版本", default="'1.0'", check="answer_key_schema_version = '1.0'"),
    c("max_score", "integer", "满分", check="max_score >= 1"),
    c("due_at", "timestamptz(6)", "截止时刻", nullable=True),
    c("published_at", "timestamptz(6)", "发布时间", nullable=True), *times()],
    constraints=["UNIQUE(id,course_id)", "UNIQUE(id,class_id)",
                 "FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT",
                 "FOREIGN KEY(chapter_id,course_id) REFERENCES chapters(id,course_id) ON DELETE RESTRICT"],
    rules="published_at为NULL是草稿，学生不可见；发布后course/class与题目版本不可静默改写。班级为空只表示课程级作业，不自动复制到每个班。answer_key不进入学生投影，连NULL字段也不返回；public_question补公开选项是待确认API增量。",
    json={"public_question": "对象schemaVersion=1.0；options数组0..26项，每项{key:1..8字符,text:1..1000字符}；单选/多选必非空且key唯一。",
          "answer_key": "沿用现有wire，无内嵌版本；按question_type及列级版本规则解码：options是唯一选项key数组；acceptableBlanks是等价答案文本数组，服务端限长/限项。未知键拒绝；主观题可NULL。"})
t("submissions", "作业提交与批阅结果", "M5", "业务与管理", [
    ident("submission"), fk("assignment_id", "assignments", "作业"), fk("student_user_id", "users", "提交学生"),
    fk("course_id", "courses", "提交时课程快照"), fk("class_id", "classes", "提交时班级快照", nullable=True),
    c("answer", "jsonb", "学生答案", check="jsonb_typeof(answer) IN ('object','string')",
      rule="保留现有object或string wire；版本由answer_schema_version外置"),
    c("answer_schema_version", "varchar(16)", "答案存储版本", default="'1.0'", check="answer_schema_version = '1.0'"),
    c("is_correct", "boolean", "判分对错", nullable=True), c("score", "integer", "得分", nullable=True, check="score IS NULL OR score >= 0"),
    enum("graded_by", "判分来源", "auto/teacher/ai_assisted"),
    c("graded_at", "timestamptz(6)", "批阅时间", nullable=True),
    c("idempotency_key", "varchar(128)", "首次提交重试键", check="length(idempotency_key) > 0"),
    c("request_hash", "varchar(64)", "规范化请求摘要", check="request_hash ~ '^[0-9a-f]{64}$'"),
    c("revision", "integer", "乐观锁版本", default="1", check="revision >= 1"),
    c("submitted_at", "timestamptz(6)", "首次提交时刻", default="CURRENT_TIMESTAMP"), *times()],
    constraints=["UNIQUE(assignment_id,student_user_id)", "UNIQUE(student_user_id,idempotency_key)",
                 "FOREIGN KEY(assignment_id,course_id) REFERENCES assignments(id,course_id) ON DELETE RESTRICT",
                 "FOREIGN KEY(assignment_id,class_id) REFERENCES assignments(id,class_id) ON DELETE RESTRICT",
                 "CHECK ((graded_at IS NULL AND is_correct IS NULL AND score IS NULL) OR graded_at IS NOT NULL)"],
    rules="S1同作业每生一份。相同键/参数返回原对象，换参数409；不同键第二次提交409。score<=作业max_score、学生/作业class相等及批阅权限由锁内service检查。编辑提交PATCH路径/重判语义未冻结，revision只预留并发控制，不声称编辑接口存在。",
    json={"answer": "answer_schema_version=1.0；string为1..8000字符；对象仅允许options:string[]或blanks:string[]，按题型校验，数组大小与题目匹配；不得包含isCorrect/score/gradedBy/answerKey。"})
t("mistakes", "个人错题快照", "M5", "业务", [
    ident("mistake"), fk("student_user_id", "users", "所属学生"), fk("course_id", "courses", "课程"),
    fk("chapter_id", "chapters", "章节", nullable=True), fk("assignment_id", "assignments", "作业", nullable=True),
    fk("submission_id", "submissions", "错误提交", nullable=True), fk("source_turn_id", "tutoring_turns", "主动标记答疑轮次", nullable=True),
    enum("source", "收录来源", "wrong_submission/manual"), obj("question", "题目快照", version=False),
    c("student_answer", "jsonb", "答案快照", nullable=True, check="student_answer IS NULL OR jsonb_typeof(student_answer) IN ('object','string')"),
    c("snapshot_schema_version", "varchar(16)", "快照解码版本", default="'1.0'", check="snapshot_schema_version = '1.0'"),
    c("note", "varchar(500)", "学生备注", nullable=True), enum("status", "复习状态", "active/resolved/archived", "active"), *times()],
    indexes=["CREATE UNIQUE INDEX uq_mistakes_submission ON mistakes(student_user_id,submission_id) WHERE submission_id IS NOT NULL",
             "CREATE UNIQUE INDEX uq_mistakes_turn ON mistakes(student_user_id,source_turn_id) WHERE source_turn_id IS NOT NULL"],
    rules="只在错误提交或学生明确标记时收录；错误批阅重试不新增，resolved不硬删。无来源锚点的手动自由文本需service幂等键，未定义通用重复正文判定。",
    json={"question": "外置snapshot_schema_version=1.0；键stem:string<=4000、questionType:冻结作业枚举或tutoring_question、options:null或公开选项数组、attachmentUrl:null或受控地址；未知键拒绝。不向原wire硬加schemaVersion。",
          "student_answer": "同submissions.answer的1.0解码规则；可NULL，绝不混入正确答案。"})
t("study_plans", "预习复习计划", "M5", "业务", [
    ident("plan"), fk("student_user_id", "users", "所属学生"), c("title", "varchar(100)", "计划名"),
    fk("course_id", "courses", "课程", nullable=True), fk("chapter_id", "chapters", "章节", nullable=True),
    fk("source_turn_id", "tutoring_turns", "授权导学建议来源", nullable=True),
    enum("source", "来源", "tutoring/manual/imported"), enum("status", "计划状态", "active/completed/archived", "active"),
    c("due_at", "timestamptz(6)", "整体截止", nullable=True), *times()],
    rules="项目首版承载预习/复习/备考清单；1..20项由service同事务验证。source=tutoring必须通过M3归属校验取用建议，不信前端转存正文。最后阅读章节由chapter_viewed事实派生，不另建偏好字段。")
t("plan_items", "计划条目", "M5", "业务", [
    ident("plan_item"), fk("plan_id", "study_plans", "所属计划", delete="CASCADE"),
    c("content", "varchar(500)", "任务内容", check="length(btrim(content)) > 0"),
    c("order", "integer", "条目顺序", check='"order" >= 1'), enum("status", "完成状态", "pending/done", "pending"),
    c("due_at", "timestamptz(6)", "条目截止", nullable=True), fk("chapter_id", "chapters", "关联章节", nullable=True),
    c("knowledge_point", "varchar(200)", "知识点标签", nullable=True),
    fk("related_mistake_id", "mistakes", "关联错题", nullable=True), fk("related_assignment_id", "assignments", "关联作业", nullable=True), *times()],
    constraints=['UNIQUE(plan_id,"order")'],
    rules="关联资源必须属于当前学生授权范围；完成状态翻转才发事件，重复PATCH不重发。记忆曲线与考试押题算法不在S1实现范围。")
t("reminders", "站内截止与复习提醒", "M5", "业务与管理", [
    ident("reminder"), fk("student_user_id", "users", "接收学生"), fk("plan_id", "study_plans", "计划", nullable=True),
    fk("assignment_id", "assignments", "作业", nullable=True), enum("type", "提醒类型", "plan_due/assignment_due/mistake_review_due"),
    c("title", "varchar(100)", "提醒标题"), c("body", "varchar(500)", "提醒正文", nullable=True),
    c("due_at", "timestamptz(6)", "关联截止"), c("is_read", "boolean", "是否已读", default="false"),
    c("read_at", "timestamptz(6)", "阅读时刻", nullable=True),
    c("dedup_key", "varchar(128)", "扫描生成去重键"), *times(False)],
    constraints=["UNIQUE(student_user_id,dedup_key)", "CHECK (is_read = (read_at IS NOT NULL))"],
    rules="due/type/目标生成稳定dedup_key，扫描重试不重复提醒；mistake_review_due为设计保留，S1不声称智能间隔复习已实现。")
t("learning_events", "不可变学习事件与幂等事实", "M5", "业务事实与管理", [
    ident("event"), enum("event_type", "事件类型", "assignment_submitted/assignment_graded/mistake_recorded/mistake_resolved/study_plan_saved/plan_item_completed/reminder_triggered/chapter_viewed"),
    fk("user_id", "users", "学生主体"), fk("course_id", "courses", "课程", nullable=True),
    fk("class_id", "classes", "发生时教学班快照", nullable=True),
    c("occurred_at", "timestamptz(6)", "实际发生时刻"),
    c("recorded_at", "timestamptz(6)", "数据库接受时刻", default="CURRENT_TIMESTAMP"),
    c("trace_id", "varchar(36)", "平台请求号", check="trace_id ~ '^req_[0-9a-f]{32}$'"),
    c("schema_version", "varchar(16)", "事件envelope版本", default="'1.0'", check="schema_version = '1.0'"),
    obj("payload", "事件特有数据", version=False),
    c("idempotency_key", "varchar(128)", "章节浏览动作幂等键", nullable=True, check="idempotency_key IS NULL OR length(idempotency_key)>0"),
    c("request_hash", "varchar(64)", "浏览请求摘要", nullable=True, check="request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$'")],
    constraints=["FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT",
                 "CHECK(class_id IS NULL OR course_id IS NOT NULL)",
                 "CHECK(event_type <> 'chapter_viewed' OR (course_id IS NOT NULL AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL))"],
    indexes=["CREATE UNIQUE INDEX uq_learning_intent ON learning_events(user_id,idempotency_key) WHERE idempotency_key IS NOT NULL",
             "CREATE INDEX ix_events_order ON learning_events(occurred_at,id)",
             "CREATE INDEX ix_events_class_time ON learning_events(class_id,occurred_at)"],
    rules="id映射wire eventId；业务与事件同Session事务，幂等命中不重发。class_id为受信上下文/作业/提交的发生时快照，不向wire 1.0偷偷加字段；公开feed元数据与契约修订另评。多班无明确上下文时class_id=NULL，只入个人/课程汇总，不复制到各班。不可把occurred_at或自增号当提交水位；M6用未处理账本补扫。",
    json={"payload": "版本位于envelope.schema_version=1.0，不要求payload再加版本；按event_type白名单：chapter_viewed仅chapterId；assignment_submitted含submissionId/assignmentId/questionType及可空isCorrect/score；assignment_graded含submissionId/isCorrect/可空score；mistake_recorded含mistakeId/source/可空assignmentId/chapterId；mistake_resolved仅mistakeId；study_plan_saved含planId/source/itemsCount(1..20)；plan_item_completed含planId/itemId；reminder_triggered含reminderId/type/dueAt。字段camelCase，未知/缺必填拒绝。"})

# M3: retain the nine-table scope and field meaning of #76; settle its open design gaps.
t("tutoring_sessions", "学生私有多轮答疑会话", "M3", "业务", [
    ident("sess"), fk("student_user_id", "users", "所属学生"), fk("course_id", "courses", "课程上下文", nullable=True),
    enum("current_stage", "当前教学阶段", "thought/hint/step/summary", "thought"), *times()],
    rules="生产会话ID由服务端创建接口发号（接口schema待共同确认），不把Mock路径首次见即创建搬入生产。NULL课程为通用问答，不授予任何文档权；教师默认不可读完整对话。")
t("tutoring_turns", "答疑轮次和完整性结算", "M3", "业务", [
    ident("turn"), fk("session_id", "tutoring_sessions", "所属会话", delete="CASCADE"),
    c("seq", "integer", "会话内轮次", check="seq >= 1", rule="会话行锁下分配；不同于SSE seq"),
    c("request_id", "varchar(36)", "创建请求号", check="request_id ~ '^req_[0-9a-f]{32}$'"),
    c("student_content", "varchar(2000)", "学生问题", check="length(btrim(student_content))>0"),
    c("assistant_content", "text", "已生成正文或中断部分", nullable=True, check="assistant_content IS NULL OR length(assistant_content)<=16000"),
    enum("stage", "本轮冻结阶段", "thought/hint/step/summary"), enum("status", "持久化轮次状态", "active/completed/aborted", "active"),
    enum("abort_reason", "内部中断原因", "client_stop/client_disconnect/model_error/retrieval_error/server_restart", nullable=True),
    c("is_complete", "boolean", "完整回答标志", default="false"), c("is_mock", "boolean", "Mock来源标志"),
    enum("emotion", "冻结情绪", "neutral/encouraging/thinking/celebrating", nullable=True),
    enum("action", "冻结动作", "idle/nod/point/write", nullable=True),
    obj("follow_ups", "追问建议", "'{\"schemaVersion\":\"1.0\",\"items\":[]}'::jsonb"),
    fk("prompt_version_id", "prompt_versions", "提示词版本"), fk("model_config_version_id", "model_config_versions", "模型配置版本"),
    c("input_tokens", "integer", "输入token量", nullable=True, check="input_tokens IS NULL OR input_tokens>=0"),
    c("output_tokens", "integer", "输出token量", nullable=True, check="output_tokens IS NULL OR output_tokens>=0"),
    c("duration_ms", "integer", "耗时毫秒", nullable=True, check="duration_ms IS NULL OR duration_ms>=0"),
    enum("error_code", "错误码", "MODEL_OUTPUT_INVALID/MODEL_REFUSED/MODEL_TIMEOUT/RETRIEVAL_UNAVAILABLE/TURN_ABORTED", nullable=True),
    c("error_reason", "varchar(64)", "内部原因码", nullable=True), *times(False),
    c("settled_at", "timestamptz(6)", "终态时刻", nullable=True)],
    constraints=["UNIQUE(session_id,seq)", "CHECK(is_complete = (status='completed'))",
                 "CHECK((status='active') = (settled_at IS NULL))", "CHECK(settled_at IS NULL OR settled_at >= created_at)",
                 "CHECK((status='aborted') = (abort_reason IS NOT NULL))",
                 "CHECK(status<>'completed' OR (assistant_content IS NOT NULL AND emotion IS NOT NULL AND action IS NOT NULL))",
                 "CHECK(error_code IS NULL OR status='aborted')"],
    indexes=["CREATE UNIQUE INDEX uq_turns_active ON tutoring_turns(session_id) WHERE status='active'"],
    rules="沿用main契约，停止/断连/失败归aborted，原因在abort_reason；不推进阶段。成功结算与阶段推进/引用同事务，summary封顶。未完成正文最多16000字符、标未完成、不作后续已完成历史/播报；超限只在aborted时截断，completed正文必须与delta拼接一致，超限报错。进程重启时恢复任务把孤立active结算aborted/server_restart，需与仍活跃worker租约确认，不能误杀在飞轮次。hasEvidence由引用行推导，不再冗余布尔列。",
    json={"follow_ups": "对象schemaVersion=1.0；items为string数组，0..3项，每项1..200字符；仅completed可供客户端作为建议，其他状态不伪装完整响应。"},
    status="基于#76补全并修正状态/冻结枚举；待M2/M3/M5评审，未接应用")
t("turn_citations", "轮次引用与证据快照", "M3", "业务", [
    c("turn_id", "varchar(64)", "轮次", primary=True, reference="tutoring_turns.id", delete="CASCADE"),
    c("citation_id", "varchar(8)", "轮内标签", primary=True, check="citation_id ~ '^c[1-9][0-9]?$'"),
    fk("document_id", "documents", "文档版本"), fk("chunk_id", "document_chunks", "原片段"),
    c("document_title_snapshot", "varchar(200)", "引用时标题"), c("document_version", "integer", "引用时版本", check="document_version>=1"),
    c("page_number", "integer", "页码", check="page_number>=1"), c("snippet", "varchar(1000)", "证据片段"), *times(False)],
    constraints=["UNIQUE(turn_id,chunk_id)",
                 "FOREIGN KEY(chunk_id,document_id) REFERENCES document_chunks(id,document_id) ON DELETE RESTRICT"],
    rules="按本轮已授权检索白名单构造；snapshot改名不漂移。原始文档下载不因看见引用就放行；撤权后历史片段访问也重新核权。法定/授权清除流程须覆盖快照，不以FK永久保留为由拒绝清除。")
t("documents", "版本化课程文档元数据", "M3", "业务", [
    ident("doc"), fk("course_id", "courses", "课程"), fk("uploader_user_id", "users", "上传者"),
    c("title", "varchar(200)", "文档标题"), c("storage_key", "varchar(512)", "受控文件存储键"),
    c("file_sha256", "varchar(64)", "文件摘要", check="file_sha256 ~ '^[0-9a-f]{64}$'"),
    c("mime_type", "varchar(100)", "媒体类型"), c("byte_size", "bigint", "文件字节数", check="byte_size>0"),
    c("version", "integer", "文档版本", default="1", check="version>=1"),
    fk("previous_document_id", "documents", "前一版本", nullable=True),
    enum("status", "可检索状态", "uploaded/available/withdrawn", "uploaded"), *times()],
    indexes=["CREATE UNIQUE INDEX uq_document_successor ON documents(previous_document_id) WHERE previous_document_id IS NOT NULL"],
    rules="新解析版本新建行/chunks，旧引用不改。可检索必须available；课程归档/授权撤回立即停止新检索。二进制不入PG；上传校验实际类型/大小，标题/正文是不可信数据。上传者身份不是无限读全课程授权。")
t("document_chunks", "可定位文档片段", "M3", "业务", [
    ident("chunk"), fk("document_id", "documents", "文档版本", delete="CASCADE"),
    c("chunk_index", "integer", "文档内序号", check="chunk_index>=0"), c("page_number", "integer", "页码", check="page_number>=1"),
    c("char_start", "integer", "页内起点", check="char_start>=0"), c("char_end", "integer", "页内终点", check="char_end>char_start"),
    c("text", "text", "片段正文", check="length(text)>0"), c("text_sha256", "varchar(64)", "正文摘要", check="text_sha256 ~ '^[0-9a-f]{64}$'"), *times(False)],
    constraints=["UNIQUE(document_id,chunk_index)", "UNIQUE(id,document_id)"],
    rules="切片不跨页，页号1基、字符区间左闭右开；S1不强装pgvector，向量与索引另ADR。仅对已授权文档检索，不能先全库检索再过滤。")
t("document_grants", "文档例外授权及班级授权", "M3", "权限管理", [
    ident("grant"), fk("document_id", "documents", "文档", delete="CASCADE"),
    fk("user_id", "users", "被授权个人", nullable=True), fk("class_id", "classes", "被授权班级", nullable=True),
    fk("granted_by_user_id", "users", "授权操作人", nullable=True, delete="SET NULL"),
    c("granted_at", "timestamptz(6)", "授权时刻", default="CURRENT_TIMESTAMP"),
    c("revoked_at", "timestamptz(6)", "撤销时刻", nullable=True, check="revoked_at IS NULL OR revoked_at>=granted_at")],
    constraints=["CHECK((user_id IS NOT NULL)::integer + (class_id IS NOT NULL)::integer = 1)"],
    indexes=["CREATE UNIQUE INDEX uq_doc_grant_user ON document_grants(document_id,user_id) WHERE revoked_at IS NULL AND user_id IS NOT NULL",
             "CREATE UNIQUE INDEX uq_doc_grant_class ON document_grants(document_id,class_id) WHERE revoked_at IS NULL AND class_id IS NOT NULL"],
    rules="个人/班级目标二选一；班级可见性经M5有效花名册，须验证文档/班级课程一致；不复制花名册。授权/撤销与平台audit同事务，撤权后新检索/历史引用/下载分别重查。")
t("document_import_jobs", "课件解析任务与重试", "M3", "任务管理", [
    ident("job"), fk("document_id", "documents", "输入文档版本", delete="CASCADE"),
    c("parser_version", "varchar(64)", "解析器版本"), c("idempotency_key", "varchar(128)", "重试幂等键"),
    enum("status", "任务状态", "queued/running/succeeded/failed", "queued"),
    c("request_id", "varchar(36)", "请求追踪号", check="request_id ~ '^req_[0-9a-f]{32}$'"),
    c("attempts", "integer", "尝试次数", default="0", check="attempts>=0"),
    c("error_code", "varchar(64)", "脱敏失败码", nullable=True),
    obj("pages_without_text", "无文字页报告", "'{\"schemaVersion\":\"1.0\",\"pages\":[]}'::jsonb"),
    *times(False), c("started_at", "timestamptz(6)", "开始时刻", nullable=True),
    c("finished_at", "timestamptz(6)", "结束时刻", nullable=True)],
    constraints=["UNIQUE(document_id,idempotency_key)", "CHECK((status IN ('succeeded','failed')) = (finished_at IS NOT NULL))",
                 "CHECK(started_at IS NULL OR started_at>=created_at)", "CHECK(finished_at IS NULL OR (started_at IS NOT NULL AND finished_at>=started_at))"],
    rules="任务状态不同于文档可检索状态；失败保留码不记原课件正文。实际解析器/队列未在本批实现，Mock需标记。",
    json={"pages_without_text": "对象schemaVersion=1.0；pages为升序去重的integer数组，元素>=1，表示成功解析中无文字页；失败不伪造成功页数。"})
t("prompt_versions", "提示词发布版本目录", "M3", "配置管理", [
    ident("promptver"), c("series", "varchar(64)", "模板系列"), c("version_label", "varchar(64)", "API提示词版本"),
    c("template_path", "varchar(255)", "仓库相对路径"), c("content_sha256", "varchar(64)", "正文摘要", check="content_sha256 ~ '^[0-9a-f]{64}$'"),
    enum("status", "发布状态", "draft/active/retired", "draft"), fk("created_by_user_id", "users", "登记人", nullable=True, delete="SET NULL"),
    *times(False), c("activated_at", "timestamptz(6)", "启用时刻", nullable=True), c("retired_at", "timestamptz(6)", "退役时刻", nullable=True)],
    constraints=["UNIQUE(series,version_label)", "CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))"],
    indexes=["CREATE UNIQUE INDEX uq_prompt_active ON prompt_versions(series) WHERE status='active'"],
    rules="正文唯一源为ai/prompts受控不可变Git版本；路径只在该目录，不能由上传内容指定。部署必须包含旧版本；哈希不符失败不回退。draft不伪造发布时间直接retired。")
t("model_config_versions", "模型配置版本", "M3", "配置管理", [
    ident("modelcfg"), c("config_key", "varchar(64)", "配置用途"), c("version", "integer", "版本号", check="version>=1"),
    c("provider", "varchar(32)", "受控供应商代码"), c("model_name", "varchar(100)", "模型名"), c("is_mock", "boolean", "Mock配置"),
    c("temperature", "numeric(3,2)", "采样温度", check="temperature BETWEEN 0 AND 2"),
    c("max_output_tokens", "integer", "最大输出token", check="max_output_tokens>0"),
    c("timeout_seconds", "numeric(6,2)", "总超时秒", check="timeout_seconds>0"),
    enum("status", "配置状态", "draft/active/retired", "draft"),
    fk("created_by_user_id", "users", "创建人", nullable=True, delete="SET NULL"), *times(False),
    c("activated_at", "timestamptz(6)", "发布时间", nullable=True), c("retired_at", "timestamptz(6)", "退役时间", nullable=True)],
    constraints=["UNIQUE(config_key,version)", "CHECK(is_mock = (provider='mock'))",
                 "CHECK((status='draft' AND activated_at IS NULL AND retired_at IS NULL) OR (status='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR (status='retired' AND activated_at IS NOT NULL AND retired_at>=activated_at))"],
    indexes=["CREATE UNIQUE INDEX uq_model_config_active ON model_config_versions(config_key) WHERE status='active'"],
    rules="provider来自已注册adapter，不能任意URL。密钥仅环境/secret服务，库不存密钥。温度范围是设计而非保证任意供应商支持，adapter进一步校验。版本锁内分配；发布/退役与审计同事务。")

# M4: complete missing media, preference and administration design.
t("avatar_config_versions", "数字人教学风格版本", "M4", "配置管理", [
    ident("avatarcfg"), c("config_key", "varchar(64)", "风格用途"), c("version", "integer", "版本", check="version>=1"),
    c("name", "varchar(100)", "风格名"), obj("config", "形象和教学参数"),
    enum("status", "发布状态", "draft/active/retired", "draft"),
    fk("created_by_user_id", "users", "创建人", nullable=True, delete="SET NULL"), *times(False)],
    constraints=["UNIQUE(config_key,version)"], indexes=["CREATE UNIQUE INDEX uq_avatar_config_active ON avatar_config_versions(config_key) WHERE status='active'"],
    rules="配置引用受控形象资源，不存模型/语音密钥；已使用版本不可覆盖，修改新建版本。",
    json={"config": "对象schemaVersion=1.0；avatarAssetKey:受控存储键<=512；subjectStyle:冻结学科或other；tone:gentle/neutral/strict；defaultEmotion:冻结四值；defaultAction:冻结四值；非法未知键拒绝。"})
t("avatar_profiles", "个人数字人和语音偏好", "M4", "业务", [
    ident("avatar"), fk("user_id", "users", "偏好所属用户"), fk("config_version_id", "avatar_config_versions", "风格版本"),
    c("auto_play", "boolean", "自动播报", default="false"),
    c("volume", "numeric(3,2)", "音量", default="1.00", check="volume BETWEEN 0 AND 1"),
    c("speech_rate", "numeric(3,2)", "语速", default="1.00", check="speech_rate BETWEEN 0.5 AND 2"),
    c("subtitles_enabled", "boolean", "字幕", default="true"), *times()], constraints=["UNIQUE(user_id)"],
    rules="跨设备偏好唯一归M4，不让M1/M5/M2另建student_preferences。仅本人修改；auto_play默认关闭避免未经意愿播报。组件目前未提供这些入参，服务端/API与组件schema需M2确认后实现。")
t("media_assets", "媒体文件和录音授权元数据", "M4", "资源管理", [
    ident("media"), fk("owner_user_id", "users", "文件owner"), fk("course_id", "courses", "课程", nullable=True),
    c("storage_key", "varchar(512)", "私有存储键"), c("sha256", "varchar(64)", "文件摘要", check="sha256 ~ '^[0-9a-f]{64}$'"),
    c("mime_type", "varchar(100)", "实际媒体类型"), c("byte_size", "bigint", "字节大小", check="byte_size>0"),
    enum("kind", "资产类型", "image/audio/video/document/avatar"),
    enum("status", "资产生命周期", "ready/withdrawn/deleting/deleted", "ready"),
    c("consent_version", "varchar(32)", "录音/处理同意版本", nullable=True),
    c("consented_at", "timestamptz(6)", "同意时刻", nullable=True),
    c("expires_at", "timestamptz(6)", "到期时刻", nullable=True), c("deleted_at", "timestamptz(6)", "完成删除时刻", nullable=True), *times()],
    constraints=["UNIQUE(storage_key)", "CHECK(kind<>'audio' OR (consent_version IS NOT NULL AND consented_at IS NOT NULL))",
                 "CHECK((status='deleted') = (deleted_at IS NOT NULL))"],
    rules="文件不塞PG；生成签名下载地址前核权，不公开storage_key。录音缺同意拒绝；删除流程先阻断使用、再清对象和派生文本/引用、最后标deleted，失败可重试并审计。")
t("media_jobs", "语音与媒体处理任务", "M4", "任务管理", [
    ident("mediajob"), fk("owner_user_id", "users", "任务owner"), fk("input_asset_id", "media_assets", "输入资产", nullable=True),
    fk("output_asset_id", "media_assets", "输出资产", nullable=True), enum("job_type", "处理类型", "tts/asr/ocr/transcode"),
    c("processor_version", "varchar(64)", "处理器版本"), c("is_mock", "boolean", "Mock标识"),
    c("idempotency_key", "varchar(128)", "重试键"), c("request_hash", "varchar(64)", "请求摘要", check="request_hash ~ '^[0-9a-f]{64}$'"),
    obj("params", "非敏感处理参数", "'{\"schemaVersion\":\"1.0\"}'::jsonb"),
    enum("status", "任务状态", "queued/running/succeeded/failed/cancelled", "queued"),
    c("attempts", "integer", "尝试次数", default="0", check="attempts>=0"),
    c("error_code", "varchar(64)", "脱敏错误码", nullable=True),
    c("request_id", "varchar(36)", "请求号", check="request_id ~ '^req_[0-9a-f]{32}$'"), *times(False),
    c("started_at", "timestamptz(6)", "开始时刻", nullable=True), c("finished_at", "timestamptz(6)", "结束时刻", nullable=True)],
    constraints=["UNIQUE(owner_user_id,job_type,idempotency_key)",
                 "CHECK((status IN ('succeeded','failed','cancelled')) = (finished_at IS NOT NULL))"],
    rules="键复用换参数409；worker有界重试，实际ASR/TTS不在本批交付，is_mock不能当真实服务。params不存完整对话/密钥，转写文本通过受控output_asset管理。",
    json={"params": "对象schemaVersion=1.0；language可选zh-CN/en-US；voiceCode为服务端白名单<=64；rate可选0.5..2；每种job_type固定允许键，禁止任意URL、命令、密钥或原始学生文本。"})
t("playback_records", "播报标识与唯一终态", "M4", "业务", [
    ident("playback"), c("utterance_id", "varchar(64)", "前端播报标识"), fk("user_id", "users", "播报用户"),
    fk("turn_id", "tutoring_turns", "完整答疑来源", nullable=True), fk("media_job_id", "media_jobs", "语音任务", nullable=True),
    fk("config_version_id", "avatar_config_versions", "风格版本"), c("is_mock", "boolean", "是否Mock"),
    enum("status", "播报状态", "started/completed/stopped/error", "started"),
    enum("stop_reason", "停止原因", "user_stop/replaced/component_unmounted", nullable=True),
    c("error_code", "varchar(64)", "错误码", nullable=True),
    c("started_at", "timestamptz(6)", "开始时刻"), c("ended_at", "timestamptz(6)", "终态时刻", nullable=True),
    c("duration_ms", "integer", "耗时毫秒", nullable=True, check="duration_ms IS NULL OR duration_ms>=0")],
    constraints=["UNIQUE(user_id,utterance_id)", "CHECK((status='started')=(ended_at IS NULL))",
                 "CHECK(ended_at IS NULL OR ended_at>=started_at)", "CHECK((status='stopped')=(stop_reason IS NOT NULL))",
                 "CHECK((status='error')=(error_code IS NOT NULL))"],
    rules="条件UPDATE WHERE status=started实现唯一终态，重复相同终态幂等、冲突终态409，不靠单个CHECK验证历史迁移。只播completed完整答复；前端上报是播放遥测，不视为实际学习时长证据。停止不删文字，不复制完整回答到日志。")
t("focus_sessions", "主动专注计时", "M4", "业务", [
    ident("focus"), fk("user_id", "users", "学生"), fk("course_id", "courses", "课程", nullable=True),
    c("started_at", "timestamptz(6)", "开始时刻"), c("ended_at", "timestamptz(6)", "结束时刻", nullable=True),
    c("duration_seconds", "integer", "有效秒数", nullable=True, check="duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 86400"),
    enum("status", "计时状态", "running/completed/cancelled", "running"),
    c("idempotency_key", "varchar(128)", "创建重试键")],
    constraints=["UNIQUE(user_id,idempotency_key)", "CHECK((status='running')=(ended_at IS NULL))", "CHECK(ended_at IS NULL OR ended_at>=started_at)"],
    indexes=["CREATE UNIQUE INDEX uq_focus_running ON focus_sessions(user_id) WHERE status='running'"],
    rules="用户主动开启，S1仅设计保留；不采集摄像头/生理指标，不声称检测疲劳或专注心理状态。服务端校验时间，客户端填时长不直接记入教师统计。")

# M6: ledger-backed polling, not a timestamp/sequence cutoff.
t("analytics_consumers", "消费者与算法发布状态", "M6", "消费管理", [
    ident("consumer"), c("consumer_key", "varchar(64)", "消费者名称"), c("algorithm_version", "varchar(32)", "算法版本"),
    enum("status", "消费者状态", "active/paused/retired", "paused"),
    c("last_poll_at", "timestamptz(6)", "最近扫描时间", nullable=True),
    c("last_observed_at", "timestamptz(6)", "最近观察事件时刻", nullable=True),
    c("processed_count", "bigint", "累计处理量", default="0", check="processed_count>=0"), *times()],
    constraints=["UNIQUE(consumer_key,algorithm_version)"],
    rules="每轮事务锁本行串行化同消费者；last_observed只用于诊断，不参与排除旧事件。每次提交后新事务重查未处理事件，禁止WHERE id>水位造成永久漏读。不同算法版本独立consumer与聚合空间。")
t("analytics_processed_events", "已处理事件账本", "M6", "消费管理", [
    c("consumer_id", "varchar(64)", "消费者版本", primary=True, reference="analytics_consumers.id"),
    c("event_id", "varchar(64)", "源事件", primary=True, reference="learning_events.id"),
    c("processed_at", "timestamptz(6)", "成功处理时刻", default="CURRENT_TIMESTAMP"),
    c("source_hash", "varchar(64)", "源事实摘要", check="source_hash ~ '^[0-9a-f]{64}$'")],
    rules="(consumer,event)唯一；写账本与聚合更新同事务，不先写done后改指标。重启重复扫不重复计数；源事件不可变。只有已成功处理才进入账本，隔离另表不伪装已完成。")
t("analytics_daily_metrics", "学生班级日统计", "M6", "业务统计", [
    ident("metric"), fk("consumer_id", "analytics_consumers", "算法消费者"), fk("student_user_id", "users", "学生"),
    fk("course_id", "courses", "课程", nullable=True), fk("class_id", "classes", "发生时班级", nullable=True),
    c("metric_date", "date", "统计本地日"), c("timezone", "varchar(64)", "日界时区", default="'Asia/Shanghai'"),
    c("study_seconds", "integer", "推断学习秒", nullable=True, check="study_seconds IS NULL OR study_seconds>=0"),
    c("submission_count", "integer", "提交数", default="0", check="submission_count>=0"),
    c("wrong_count", "integer", "已判错数量", default="0", check="wrong_count>=0"),
    c("sample_count", "integer", "有效样本数", default="0", check="sample_count>=0"),
    enum("data_state", "数据状态", "unknown/partial/known", "unknown"),
    c("data_through", "timestamptz(6)", "本范围纳入最新发生时间", nullable=True), *times()],
    constraints=["UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,course_id,class_id,metric_date,timezone)",
                 "FOREIGN KEY(class_id,course_id) REFERENCES classes(id,course_id) ON DELETE RESTRICT",
                 "CHECK(class_id IS NULL OR course_id IS NOT NULL)",
                 "CHECK(data_state <> 'unknown' OR study_seconds IS NULL)"],
    rules="class为事件发生时快照；无class事件不摊到每班。无观测时unknown+NULL，已确认无活动才known+0；不能用count默认0推断数据完整。迟到事件到达后重算受影响学生/班级/日，不按到达顺序累加推断时长。日界按时区日历，不按固定24小时跨DST。")
t("analytics_report_snapshots", "个人和班级成长报告快照", "M6", "业务报告", [
    ident("report"), fk("consumer_id", "analytics_consumers", "算法版本"),
    fk("student_user_id", "users", "个人报告主体", nullable=True), fk("class_id", "classes", "班级报告范围", nullable=True),
    c("period_start", "timestamptz(6)", "周期起点"), c("period_end", "timestamptz(6)", "周期终点", check="period_end>period_start"),
    obj("metrics", "指标与知识点掌握度"), c("sample_count", "integer", "样本数", check="sample_count>=0"),
    c("data_through", "timestamptz(6)", "纳入最新发生时间", nullable=True),
    c("generated_at", "timestamptz(6)", "生成时间", default="CURRENT_TIMESTAMP")],
    constraints=["CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1)",
                 "UNIQUE NULLS NOT DISTINCT(consumer_id,student_user_id,class_id,period_start,period_end)"],
    rules="本人报告与教师班级报告二选一；教师须当前授权班级，学生只本人。雷达掌握度必须带样本/算法/未知状态，不凭模型编造分数；个人报告API为后续schema增量，尚未实现。",
    json={"metrics": "对象schemaVersion=1.0；dataState:unknown/partial/known；studySeconds非负或null；knowledgePoints数组0..100项，每项{key:string<=100,mastery:number 0..1或null,sampleCount:integer>=0,dataState}；weakSubjects数组受控学科；suggestions为脱敏文本数组0..10项。"})
t("report_jobs", "周月报告生成任务", "M6", "任务管理", [
    ident("reportjob"), fk("requested_by_user_id", "users", "请求者"),
    fk("student_user_id", "users", "个人目标", nullable=True), fk("class_id", "classes", "班级目标", nullable=True),
    fk("consumer_id", "analytics_consumers", "算法版本"),
    c("period_start", "timestamptz(6)", "开始"), c("period_end", "timestamptz(6)", "结束", check="period_end>period_start"),
    enum("status", "生成状态", "queued/running/succeeded/failed/cancelled", "queued"),
    c("idempotency_key", "varchar(128)", "请求重试键"), c("error_code", "varchar(64)", "脱敏错误码", nullable=True),
    fk("report_id", "analytics_report_snapshots", "结果快照", nullable=True), *times(False),
    c("finished_at", "timestamptz(6)", "终态时间", nullable=True)],
    constraints=["UNIQUE(requested_by_user_id,idempotency_key)",
                 "CHECK((student_user_id IS NOT NULL)::integer+(class_id IS NOT NULL)::integer=1)",
                 "CHECK((status IN ('succeeded','failed','cancelled'))=(finished_at IS NOT NULL))",
                 "CHECK(status<>'succeeded' OR report_id IS NOT NULL)"],
    rules="调度重试复用幂等键；执行时重新检查请求者权限，不能拿创建时权限永久导出。报告结果与任务成功同事务。")
t("analytics_quarantined_events", "毒事件隔离与审计重放", "M6", "运维管理", [
    ident("quarantine"), fk("consumer_id", "analytics_consumers", "消费者"), fk("event_id", "learning_events", "源事件"),
    c("error_code", "varchar(64)", "脱敏失败码"),
    enum("status", "处理状态", "open/retry_ready/resolved", "open"),
    c("attempts", "integer", "失败次数", default="1", check="attempts>=1"),
    fk("resolved_by_user_id", "users", "人工处理者", nullable=True, delete="SET NULL"),
    c("first_failed_at", "timestamptz(6)", "首次失败", default="CURRENT_TIMESTAMP"),
    c("last_failed_at", "timestamptz(6)", "最近失败", default="CURRENT_TIMESTAMP"),
    c("resolved_at", "timestamptz(6)", "重放解决时刻", nullable=True)],
    constraints=["UNIQUE(consumer_id,event_id)", "CHECK(last_failed_at>=first_failed_at)",
                 "CHECK((status='resolved')=(resolved_at IS NOT NULL))"],
    rules="不复制敏感payload，引用原事件。open明确告警/报告partial，不静默跳过；授权人工审计后置retry_ready，成功处理后ledger+聚合+resolved同事务。源事件保持不变；修schema/算法用新consumer版本或受控重放。")

assert len(TABLES) == 33
