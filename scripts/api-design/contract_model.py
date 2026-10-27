"""Reviewed design inputs for Issue #80, not runtime models or a second database Base.

V2 is a candidate wire contract. Existing v1 callers and domain implementations
are deliberately untouched. All examples use synthetic identifiers.
"""

from copy import deepcopy

SCHEMAS: dict[str, dict] = {}
OPERATIONS: list[dict] = []
NOW = "2026-10-27T01:00:00Z"
TRACE = "req_" + "1" * 32
IDS = {
    key: prefix + "_" + "1" * 32
    for key, prefix in {
        "user": "user",
        "course": "course",
        "class": "class",
        "chapter": "chapter",
        "assignment": "assignment",
        "submission": "submission",
        "mistake": "mistake",
        "plan": "plan",
        "item": "plan_item",
        "reminder": "reminder",
        "session": "sess",
        "turn": "turn",
        "document": "doc",
        "asset": "media",
        "job": "job",
        "report": "report",
        "config": "config",
        "event": "event",
        "exam": "exam",
        "attempt": "attempt",
        "focus": "focus",
        "playback": "playback",
    }.items()
}


def text(desc: str, maximum: int = 100, minimum: int = 1, **extra) -> dict:
    return {
        "type": "string",
        "minLength": minimum,
        "maxLength": maximum,
        "description": desc,
        **extra,
    }


def number(desc: str, minimum: int = 0, maximum: int = 2147483647) -> dict:
    return {
        "type": "integer",
        "minimum": minimum,
        "maximum": maximum,
        "description": desc,
    }


def boolean(desc: str) -> dict:
    return {"type": "boolean", "description": desc}


def enum(desc: str, *values: str) -> dict:
    return {"type": "string", "enum": list(values), "description": desc}


def ref(name: str, desc: str = "") -> dict:
    return {
        "$ref": f"#/components/schemas/{name}",
        **({"description": desc} if desc else {}),
    }


def nullable(schema: dict, desc: str = "") -> dict:
    return {
        "anyOf": [deepcopy(schema), {"type": "null"}],
        "description": desc or schema.get("description", "可空值，null不等于空字符串"),
    }


def array(schema: dict, desc: str, maximum: int = 100, minimum: int = 0) -> dict:
    return {
        "type": "array",
        "items": deepcopy(schema),
        "minItems": minimum,
        "maxItems": maximum,
        "description": desc,
    }


ID = text("不透明资源ID；新ID由服务端生成前缀加32位小写hex，客户端不得按前缀判权", 64)
TIME = text("UTC ISO8601时间，必须以Z结尾", 40, format="date-time", pattern="Z$")
DATE = text("本地日历日期，与timezone共同解释", 10, format="date")
ROLE = enum("角色", "student", "teacher", "admin")
SUBJECT = enum(
    "受控学科，其他专业归other并用课程标题区分",
    "math",
    "physics",
    "chemistry",
    "english",
    "cs",
    "other",
)
STAGE = enum(
    "服务端教学阶段，不透传模型内部思维链", "thought", "hint", "step", "summary"
)
EMOTION = enum("M4冻结情绪", "neutral", "encouraging", "thinking", "celebrating")
ACTION = enum("M4冻结动作", "idle", "nod", "point", "write")
QUESTION = enum(
    "作业题型",
    "single_choice",
    "multiple_choice",
    "fill_blank",
    "short_answer",
    "proof",
)
BASE_TIMES = {"created_at": TIME, "updated_at": TIME}


def model(
    name: str,
    desc: str,
    props: dict,
    *,
    optional=(),
    owner="M1",
    db="",
    rules=(),
    example=None,
    **extra,
) -> dict:
    result = {
        "type": "object",
        "description": desc,
        "properties": deepcopy(props),
        "required": [k for k in props if k not in optional],
        "additionalProperties": False,
        "x-owner": owner,
        "x-database": db,
        "x-business-rules": list(rules),
        **extra,
    }
    if example is not None:
        result["example"] = example
    SCHEMAS[name] = result
    return ref(name)


def page(name: str) -> str:
    key = name + "Page"
    if key not in SCHEMAS:
        model(
            key,
            f"{name}分页结果",
            {
                "items": array(ref(name), "本页记录，空结果为[]，不得null", 100),
                "total": number("授权范围内总数"),
                "page": number("页码", 1, 1000),
                "page_size": number("每页条数", 1, 100),
            },
            owner=SCHEMAS[name].get("x-owner", "M1"),
        )
    return key


model(
    "FieldError",
    "脱敏参数错误，不回显密码、Token或学生正文",
    {"field": text("字段路径", 200), "reason": text("允许的修正说明", 200)},
)
model(
    "ErrorDetails",
    "安全错误上下文",
    {
        "reason_code": text("内部稳定原因码，不包含堆栈或SQL", 64),
        "fields": array(ref("FieldError"), "字段错误", 20),
        "resource_id": nullable(ID, "仅当前已授权资源可返回，未授权404不得带资源信息"),
    },
    optional=("fields", "resource_id"),
)
model(
    "ErrorEnvelope",
    "v2统一错误，与HTTP状态一致，不能HTTP200伪造错误",
    {
        "code": number("1xxxx参数、2xxxx业务与权限、5xxxx系统", 10000, 59999),
        "message": text("可向用户展示的脱敏提示", 300),
        "data": nullable(ref("ErrorDetails")),
        "trace_id": text(
            "本次服务端请求号，与X-Request-ID一致", 36, pattern=r"^req_[0-9a-f]{32}$"
        ),
    },
)
model(
    "Health",
    "进程存活，不证明DB或模型可用",
    {
        "status": {"type": "string", "const": "ok"},
        "service": {"type": "string", "const": "learning-assistant-api"},
    },
)
model(
    "UserSummary",
    "最小身份摘要，不返回学号、手机号、密码和会话摘要",
    {"user_id": ID, "display_name": text("展示名", 100), "role": ROLE},
)
model(
    "LoginRequest",
    "合成账号登录，真实部署必须TLS且禁用默认演示账号",
    {
        "username": text(
            "ASCII登录名；中文名称放display_name", 64, pattern=r"^[A-Za-z0-9_.-]{1,64}$"
        ),
        "password": {
            **text("仅认证输入，绝不日志记录或响应回显", 128),
            "writeOnly": True,
        },
    },
    example={
        "username": "student_a",
        "password": "synthetic-example-not-a-real-password",
    },
)
model(
    "LoginResult",
    "可撤销会话凭证，Token只在此认证响应交付",
    {
        "token": {**text("敏感Bearer凭证，不放URL或日志", 8192), "format": "password"},
        "token_type": {"type": "string", "const": "bearer"},
        "expires_at": TIME,
        "user": ref("UserSummary"),
    },
    db="users/user_roles/auth_sessions",
    rules=(
        "JWT验签、过期、撤销和当前角色均由服务端校验；数据库故障503，不退回Mock身份。",
    ),
)
model(
    "LogoutResult", "当前凭证幂等撤销", {"revoked": {"type": "boolean", "const": True}}
)
model(
    "Profile",
    "本人资料，跨设备语音偏好不在此重复存储",
    {
        "user_id": ID,
        "display_name": text("姓名或昵称", 100),
        "major": nullable(text("专业", 100)),
        "grade": nullable(text("年级", 32)),
        "timezone": text("IANA时区，服务端ZoneInfo校验", 64),
        **BASE_TIMES,
    },
    db="user_profiles",
)
model(
    "ProfilePatch",
    "本人可编辑字段白名单",
    {
        "display_name": text("展示名", 100),
        "major": nullable(text("专业", 100)),
        "grade": nullable(text("年级", 32)),
        "timezone": text("IANA时区", 64),
    },
    optional=("display_name", "major", "grade", "timezone"),
    minProperties=1,
)
model(
    "UserBatchRequest",
    "只用于已授权课程界面组合姓名，不是全站通讯录",
    {
        "user_ids": {
            **array(ID, "待解析用户ID，必须逐项鉴权", 50, 1),
            "uniqueItems": True,
        }
    },
)
model(
    "UserBatchResult",
    "仅返回允许查看的用户，不说明未返回者是否存在",
    {"items": array(ref("UserSummary"), "可访问的摘要", 50)},
)

model(
    "Course",
    "课程内容资源，与教学班分离",
    {
        "id": ID,
        "title": text("课程名称", 100),
        "description": nullable(text("课程简介", 2000)),
        "subject": SUBJECT,
        "cover_image_url": nullable(
            text("受控图片地址，展示时转义", 2048, format="uri")
        ),
        "teacher_id": ID,
        "teacher_name": nullable(text("平台摘要组合，不另存姓名", 100)),
        "student_count": nullable(number("按权限聚合人数，未知为null")),
        "chapter_count": nullable(number("授权章节数")),
        **BASE_TIMES,
    },
    owner="M5",
    db="courses；teacher_id映射teacher_user_id，计数为查询聚合",
)
model(
    "CourseCreate",
    "教师创建课程，不接受teacher_id",
    {
        "title": text("课程名称", 100),
        "description": nullable(text("简介", 2000)),
        "subject": SUBJECT,
    },
    optional=("description",),
    owner="M5",
)
model(
    "Class",
    "教学班及课程归属",
    {
        "id": ID,
        "course_id": ID,
        "title": text("教学班名", 100),
        "teacher_id": ID,
        "student_count": number("当前有效选课人数"),
        **BASE_TIMES,
    },
    owner="M5",
    db="classes/teaching_assignments/enrollments",
)
model("ClassCreate", "课程负责人新建班级", {"title": text("班级名称", 100)}, owner="M5")
model(
    "Chapter",
    "可阅读章节，不把整份教材放列表",
    {
        "id": ID,
        "course_id": ID,
        "title": text("章节名", 100),
        "order": number("同课程唯一顺序", 1),
        "description": nullable(text("章节摘要", 2000)),
        "document_id": nullable(ID),
        **BASE_TIMES,
    },
    owner="M5",
    db="chapters",
)
model(
    "ChapterCreate",
    "章节创建",
    {
        "title": text("章节名", 100),
        "order": number("同课程唯一顺序", 1),
        "description": nullable(text("章节摘要", 2000)),
        "document_id": nullable(ID),
    },
    optional=("description", "document_id"),
    owner="M5",
    rules=("document_id必须属于当前课程且当前教师有管理权。",),
)
model(
    "EnrollmentWrite",
    "教师管理选课关系；不接受自报角色",
    {"student_user_id": ID},
    owner="M5",
)
model(
    "Enrollment",
    "历史选课关系保留区间",
    {
        "id": ID,
        "class_id": ID,
        "course_id": ID,
        "student_user_id": ID,
        "joined_at": TIME,
        "left_at": nullable(TIME),
    },
    owner="M5",
    db="enrollments",
    rules=("同课程多班允许；退出关闭关系区间，不删除历史，不改写事件班级快照。",),
)
model("TeachingWrite", "课程管理员分配授课关系", {"teacher_user_id": ID}, owner="M5")
model(
    "TeachingAssignment",
    "授课关系",
    {
        "id": ID,
        "class_id": ID,
        "course_id": ID,
        "teacher_user_id": ID,
        "assigned_at": TIME,
        "revoked_at": nullable(TIME),
    },
    owner="M5",
    db="teaching_assignments",
)
model(
    "EnrollmentRequestCreate",
    "学生申请加入班级，不能直接授予访问权",
    {"message": nullable(text("申请理由，可不填，不收集敏感资料", 300))},
    optional=("message",),
)
model(
    "EnrollmentRequest",
    "待教师审核的入班申请",
    {
        "id": ID,
        "class_id": ID,
        "student_user_id": ID,
        "status": enum("申请状态", "pending", "approved", "rejected", "cancelled"),
        "message": nullable(text("申请理由", 300)),
        **BASE_TIMES,
    },
    db="v2新增enrollment_requests管理实体；不冒充#79已有表",
    rules=("批准与enrollments写入及审计同事务，拒绝/取消不授权。",),
)
model(
    "EnrollmentDecision",
    "本班教师审核",
    {
        "status": enum("审核结果", "approved", "rejected"),
        "reason": nullable(text("脱敏理由", 300)),
    },
    optional=("reason",),
)
model(
    "ChapterViewedIntent",
    "客户端只传阅读意图，身份与事件字段由服务端生成",
    {"course_id": ID, "chapter_id": ID, "class_id": nullable(ID)},
    optional=("class_id",),
    owner="M5",
    rules=(
        "正文成功可见才提交；class_id需当前有效选课且属于course；无唯一班级不复制到每班。",
    ),
)
model(
    "LearningEventReceipt",
    "事件已与业务事务一同提交",
    {
        "event_id": ID,
        "occurred_at": TIME,
        "schema_version": {"type": "string", "const": "2.0"},
    },
    owner="M5",
    db="learning_events",
)

model(
    "Option",
    "公开选项，不含正确性提示",
    {"key": text("同题唯一选项代码", 8), "text": text("选项正文", 1000)},
    owner="M5",
)
model(
    "AnswerKey",
    "教师私有标准答案；不得进入学生DTO",
    {
        "options": array(text("正确选项代码", 8), "选择题答案", 26),
        "acceptable_blanks": array(text("等价填空答案", 1000), "填空答案", 100),
    },
    optional=("options", "acceptable_blanks"),
    owner="M5",
    minProperties=1,
)
SCHEMAS["StudentAnswer"] = {
    "description": "学生答案，不接受is_correct或score",
    "oneOf": [
        text("主观题答案", 8000),
        {
            "type": "object",
            "properties": {
                "options": {
                    **array(text("选项代码", 8), "所选项", 26, 1),
                    "uniqueItems": True,
                }
            },
            "required": ["options"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "blanks": array(text("填空内容", 1000), "按顺序填空", 100, 1)
            },
            "required": ["blanks"],
            "additionalProperties": False,
        },
    ],
    "x-owner": "M5",
}
model(
    "Assignment",
    "作业公开视图，教师答案须走独立受控子接口",
    {
        "id": ID,
        "course_id": ID,
        "class_id": ID,
        "chapter_id": nullable(ID),
        "title": text("作业题目", 100),
        "description": nullable(text("题面", 8000)),
        "question_type": QUESTION,
        "options": array(ref("Option"), "非选择题为空数组", 26),
        "max_score": number("满分", 1, 10000),
        "due_at": nullable(TIME),
        "published_at": nullable(TIME),
        "teacher_id": ID,
        **BASE_TIMES,
    },
    owner="M5",
    db="assignments/public_question",
    rules=("学生看不到草稿及answer_key，字段必须不存在而非null。",),
)
model(
    "AssignmentCreate",
    "创建教师作业，服务端校验题型和答案键",
    {
        "class_id": ID,
        "chapter_id": nullable(ID),
        "title": text("标题", 100),
        "description": text("题面", 8000),
        "question_type": QUESTION,
        "options": array(ref("Option"), "公开选项", 26),
        "answer_key": nullable(ref("AnswerKey")),
        "max_score": number("满分", 1, 10000),
        "due_at": nullable(TIME),
        "publish": boolean("是否发布，草稿不可见于学生"),
    },
    optional=("chapter_id", "due_at"),
    owner="M5",
    rules=(
        "选择题至少两项、key唯一，正确代码必须命中公开选项；单选恰好一个。主观题answer_key=null。",
    ),
)
model(
    "AssignmentPatch",
    "教师修改题面或截止时间；已有提交后不得直接改判分依据",
    {
        "title": text("标题", 100),
        "description": text("题面", 8000),
        "due_at": nullable(TIME),
        "publish": boolean("发布状态"),
    },
    optional=("title", "description", "due_at", "publish"),
    owner="M5",
    minProperties=1,
)
model(
    "SubmissionCreate",
    "提交答案，user与班级来自已验证上下文",
    {"answer": ref("StudentAnswer")},
    owner="M5",
)
model(
    "Submission",
    "提交与判分结果；未判分为null而非false",
    {
        "id": ID,
        "assignment_id": ID,
        "student_id": ID,
        "class_id": ID,
        "answer": ref("StudentAnswer"),
        "is_correct": nullable(boolean("判定结果")),
        "score": nullable(number("得分，不得超过对应max_score", 0, 10000)),
        "graded_by": nullable(ID),
        "graded_at": nullable(TIME),
        **BASE_TIMES,
    },
    owner="M5",
    db="submissions",
    rules=("提交/客观判分/错题收录/事件同事务；未批阅主观题不进入错误率分母。",),
)
model(
    "SubmissionStatus",
    "未提交是正常状态，HTTP200且submission=null",
    {"submission": nullable(ref("Submission"))},
    owner="M5",
)
model(
    "GradingPatch",
    "教师批阅，禁止客户端传graded_by",
    {
        "is_correct": boolean("教师最终结论"),
        "score": number("得分，service校验上限", 0, 10000),
    },
    owner="M5",
    rules=("改判与新grading事件同事务，M6按提交最新有效判分重算，不重复计提交数。",),
)
model(
    "MistakeQuestion",
    "错题题面快照，不含标准答案",
    {
        "stem": text("题干", 4000),
        "question_type": enum(
            "题型",
            "single_choice",
            "multiple_choice",
            "fill_blank",
            "short_answer",
            "proof",
            "tutoring_question",
        ),
        "options": array(ref("Option"), "可空选项集用空数组", 26),
    },
    owner="M5",
)
model(
    "MistakeCreate",
    "主动标记；下列三种来源必须恰好一种",
    {
        "source_turn_id": ID,
        "submission_id": ID,
        "question": ref("MistakeQuestion"),
        "course_id": nullable(ID),
    },
    optional=("source_turn_id", "submission_id", "question", "course_id"),
    owner="M5",
    oneOf=[
        {"required": ["source_turn_id"]},
        {"required": ["submission_id"]},
        {"required": ["question"]},
    ],
    rules=(
        "仅错答或用户明确标记收录，不把所有答疑问题自动当错题。来源与归属在服务端一次校验。",
    ),
)
model(
    "Mistake",
    "个人错题",
    {
        "id": ID,
        "student_id": ID,
        "course_id": nullable(ID),
        "source": enum("来源", "manual", "auto"),
        "status": enum("掌握状态", "unresolved", "resolved"),
        "question": ref("MistakeQuestion"),
        "student_answer": nullable(ref("StudentAnswer")),
        "source_turn_id": nullable(ID),
        "submission_id": nullable(ID),
        **BASE_TIMES,
    },
    owner="M5",
    db="mistakes",
)
model(
    "MistakePatch",
    "本人更新掌握状态",
    {"status": enum("状态", "unresolved", "resolved")},
    owner="M5",
)
model(
    "PlanItemInput",
    "计划项输入",
    {
        "content": text("学习任务", 500),
        "chapter_id": nullable(ID),
        "knowledge_point": nullable(text("知识点", 100)),
        "due_at": nullable(TIME),
    },
    optional=("chapter_id", "knowledge_point", "due_at"),
    owner="M5",
)
model(
    "PlanSuggestionItem",
    "M3建议，不伪造M5章节ID",
    {
        "content": text("建议任务", 500),
        "chapter_id": {"type": "null", "description": "只能null，M5保存时匹配"},
        "knowledge_point": nullable(text("知识点", 100)),
        "due_at": nullable(TIME),
    },
    owner="M3",
)
model(
    "PlanSuggestion",
    "服务端可取用的结构化建议",
    {
        "title": text("建议标题", 100),
        "items": array(ref("PlanSuggestionItem"), "建议项", 20, 1),
        "due_at": nullable(TIME),
    },
    owner="M3",
)
model(
    "ManualPlanCreate",
    "手工创建计划",
    {
        "source": {"type": "string", "const": "manual"},
        "title": text("标题", 100),
        "course_id": nullable(ID),
        "items": array(ref("PlanItemInput"), "计划项", 20, 1),
    },
    optional=("course_id",),
    owner="M5",
)
model(
    "TutoringPlanCreate",
    "保存建议只引用轮次，不接受前端转存items",
    {"source": {"type": "string", "const": "tutoring"}, "source_turn_id": ID},
    owner="M5",
)
SCHEMAS["PlanCreate"] = {
    "description": "两种互斥创建路径",
    "oneOf": [ref("ManualPlanCreate"), ref("TutoringPlanCreate")],
    "x-owner": "M5",
}
model(
    "PlanItem",
    "持久计划项",
    {
        "id": ID,
        "plan_id": ID,
        "content": text("任务", 500),
        "order": number("计划内顺序", 1),
        "status": enum("状态", "pending", "done"),
        "chapter_id": nullable(ID),
        "knowledge_point": nullable(text("知识点", 100)),
        "due_at": nullable(TIME),
        **BASE_TIMES,
    },
    owner="M5",
    db="plan_items",
)
model(
    "StudyPlan",
    "个人学习计划",
    {
        "id": ID,
        "student_id": ID,
        "title": text("标题", 100),
        "course_id": nullable(ID),
        "source": enum("来源", "manual", "tutoring", "imported"),
        "source_turn_id": nullable(ID),
        "status": enum("状态", "active", "completed", "archived"),
        "items": array(ref("PlanItem"), "计划项", 20),
        "due_at": nullable(TIME),
        **BASE_TIMES,
    },
    owner="M5",
    db="study_plans",
)
model(
    "PlanPatch",
    "更新计划",
    {
        "title": text("标题", 100),
        "due_at": nullable(TIME),
        "status": enum("状态", "active", "completed", "archived"),
    },
    optional=("title", "due_at", "status"),
    owner="M5",
    minProperties=1,
)
model(
    "PlanItemPatch",
    "更新计划项",
    {
        "content": text("任务", 500),
        "due_at": nullable(TIME),
        "status": enum("状态", "pending", "done"),
        "order": number("顺序", 1),
    },
    optional=("content", "due_at", "status", "order"),
    owner="M5",
    minProperties=1,
)
model(
    "Reminder",
    "服务端生成的站内提醒，不能由学生任意创建",
    {
        "id": ID,
        "type": enum("提醒类型", "plan_due", "assignment_due", "mistake_review_due"),
        "title": text("标题", 100),
        "body": nullable(text("正文", 500)),
        "due_at": TIME,
        "is_read": boolean("是否已读"),
        "read_at": nullable(TIME),
        "created_at": TIME,
    },
    owner="M5",
    db="reminders",
)
model("ReminderPatch", "已读状态", {"is_read": boolean("已读")}, owner="M5")

model(
    "Citation",
    "当前已授权文档的引用快照",
    {
        "citation_id": text("轮内标签c1至c99", 8, pattern=r"^c[1-9][0-9]?$"),
        "document_id": ID,
        "document_title": text("标题不可信，展示时转义", 200),
        "page_number": number("页码从1起", 1),
        "snippet": text("允许展示的引用片段", 1000),
    },
    owner="M3",
    db="turn_citations",
)
model(
    "TutoringSession",
    "学生私有答疑会话，服务端发号",
    {"session_id": ID, "course_id": nullable(ID), "current_stage": STAGE, **BASE_TIMES},
    owner="M3",
    db="tutoring_sessions",
    rules=(
        "course_id=null仅通用问答，不授予任何课程文档权限；教师默认不能读学生完整对话。",
    ),
)
model(
    "SessionCreate",
    "建立会话；不接受客户端session_id",
    {"course_id": nullable(ID)},
    optional=("course_id",),
    owner="M3",
)
model(
    "MessageCreate",
    "提问与有限阶段请求",
    {
        "content": text("学生问题", 2000),
        "requested_stage": nullable(STAGE),
        "course_id": nullable(ID),
    },
    optional=("requested_stage", "course_id"),
    owner="M3",
    rules=(
        "禁止stage/emotion/action/user_id等越权字段；requested_stage由服务端钳制。",
    ),
)
model(
    "TutoringResponse",
    "已完成的答疑结果；阶段由服务端决定",
    {
        "turn_id": ID,
        "session_id": ID,
        "stage": STAGE,
        "content": text("已完成正文", 16000),
        "citations": array(ref("Citation"), "授权引用，无依据为空数组", 99),
        "has_evidence": boolean("与citations非空等价"),
        "follow_ups": array(text("建议追问", 200), "追问最多3条", 3),
        "emotion": EMOTION,
        "action": ACTION,
        "is_mock": boolean("真实来源标识"),
        "prompt_version": text("Git中受控提示词版本", 64),
        "created_at": TIME,
        "plan_suggestion": nullable(ref("PlanSuggestion")),
    },
    owner="M3",
    db="tutoring_turns/turn_citations/prompt_versions",
    rules=(
        "content与全部delta拼接完全一致，不静默截断；has_evidence=false时citations=[]。",
    ),
)
model(
    "TutoringTurn",
    "轮次读取结果；中断与成功不可混用",
    {
        "turn_id": ID,
        "session_id": ID,
        "seq": number("会话内轮次，不是SSE帧序号", 1),
        "status": enum("持久状态", "active", "completed", "aborted"),
        "is_complete": boolean("仅completed为true"),
        "partial_content": nullable(text("中断片段，不作完整历史或播报", 16000)),
        "abort_reason": nullable(
            enum(
                "内部结算原因，按本人读取权限展示",
                "client_stop",
                "client_disconnect",
                "model_error",
                "retrieval_error",
                "server_restart",
            )
        ),
        "response": nullable(ref("TutoringResponse")),
        "created_at": TIME,
        "settled_at": nullable(TIME),
    },
    owner="M3",
    db="tutoring_turns",
    rules=(
        "同会话最多一个active；成功结算/引用/阶段推进同事务，失败不推进；恢复确认worker租约过期。",
    ),
)
model(
    "SseStartedData",
    "started帧数据",
    {
        "seq": {"type": "integer", "const": 1},
        "turn_id": ID,
        "stage": STAGE,
        "is_mock": boolean("模型来源"),
    },
    owner="M3",
)
model(
    "SseDeltaData",
    "增量正文，不含隐藏推理链",
    {
        "seq": number("严格连续帧号", 2),
        "turn_id": ID,
        "text_delta": text("增量正文，可含换行", 16000, 0),
    },
    owner="M3",
)
model(
    "SseCompletedData",
    "成功终帧",
    {
        "seq": number("最后帧号", 2),
        "turn_id": ID,
        "is_complete": {"type": "boolean", "const": True},
        "response": ref("TutoringResponse"),
    },
    owner="M3",
)
model(
    "SseStoppedData",
    "用户停止终帧；断连不能再发帧",
    {
        "seq": number("最后帧号", 2),
        "turn_id": ID,
        "is_complete": {"type": "boolean", "const": False},
        "reason": {"type": "string", "const": "client_stop"},
    },
    owner="M3",
)
model(
    "SseErrorData",
    "流建立后的系统失败",
    {
        "seq": number("最后帧号", 2),
        "turn_id": ID,
        "is_complete": {"type": "boolean", "const": False},
        "reason_code": enum(
            "错误原因",
            "MODEL_OUTPUT_INVALID",
            "MODEL_REFUSED",
            "MODEL_TIMEOUT",
            "RETRIEVAL_UNAVAILABLE",
            "TURN_ABORTED",
        ),
    },
    owner="M3",
)

model(
    "Document",
    "版本化课程文件元数据，二进制不存PG",
    {
        "id": ID,
        "course_id": ID,
        "title": text("标题", 200),
        "version": number("版本", 1),
        "mime_type": text("经魔数核验的文件类型", 100),
        "byte_size": number("字节数", 1, 20971520),
        "status": enum(
            "可检索状态，与任务状态不同", "uploaded", "available", "withdrawn"
        ),
        "created_at": TIME,
        "updated_at": TIME,
    },
    owner="M3",
    db="documents",
)
model(
    "DocumentUpload",
    "multipart文件上传；仅受授权测试资料",
    {
        "file": {
            "type": "string",
            "format": "binary",
            "description": "PDF/PPTX/DOCX；最多20MiB，魔数/页数/解压比校验",
        },
        "title": text("标题", 200),
    },
    owner="M3",
)
model(
    "Job",
    "异步任务的公开最小状态，不返回worker密钥或存储key",
    {
        "job_id": ID,
        "status": enum(
            "统一任务状态", "queued", "running", "succeeded", "failed", "cancelled"
        ),
        "is_mock": boolean("是否模拟执行"),
        "result_id": nullable(ID),
        "error_code": nullable(text("失败码，不包含原文件或模型正文", 64)),
        "created_at": TIME,
        "started_at": nullable(TIME),
        "finished_at": nullable(TIME),
    },
    rules=(
        "202只表示入队，不能当处理完成；成功/失败必须终结时间；失败不得伪造输出资源。",
    ),
)
model(
    "DocumentGrantCreate",
    "个人与班级授权恰好二选一",
    {"user_id": ID, "class_id": ID},
    optional=("user_id", "class_id"),
    owner="M3",
    oneOf=[{"required": ["user_id"]}, {"required": ["class_id"]}],
)
model(
    "DocumentGrant",
    "文档授权记录",
    {
        "id": ID,
        "document_id": ID,
        "user_id": nullable(ID),
        "class_id": nullable(ID),
        "granted_at": TIME,
        "revoked_at": nullable(TIME),
    },
    owner="M3",
    db="document_grants",
    rules=("班级必须属于文档课程；撤回后新检索、历史引用原文件下载都重新鉴权。",),
)
model(
    "DocumentSummary",
    "获授权课件的重点、难点与考点，不在GET触发收费生成",
    {
        "document_id": ID,
        "summary": text("重点提炼", 8000),
        "key_points": array(text("知识点", 300), "重点", 50),
        "is_mock": boolean("来源"),
    },
    owner="M3",
    db="v2新增受控派生内容或受授权存储；须补迁移/生命周期，不冒充#79已有表",
)
model(
    "MediaUpload",
    "媒体上传，录音必须有明确处理同意",
    {
        "file": {
            "type": "string",
            "format": "binary",
            "description": "PNG/JPEG/MP3/WAV；最多20MiB，校验真实格式",
        },
        "kind": enum("媒体类型", "image", "audio"),
        "consent_version": nullable(text("录音处理告知版本", 32)),
    },
    optional=("consent_version",),
    owner="M4",
    rules=(
        "kind=audio时consent_version必填且已知有效；缺同意拒绝，不采集真实课堂录音作演示。",
    ),
)
model(
    "MediaAsset",
    "私有媒体元数据",
    {
        "id": ID,
        "kind": enum("类型", "image", "audio", "video", "document", "avatar"),
        "mime_type": text("媒体类型", 100),
        "byte_size": number("文件字节", 1, 20971520),
        "status": enum("资源状态", "ready", "withdrawn", "deleting", "deleted"),
        "created_at": TIME,
    },
    owner="M4",
    db="media_assets",
)
model(
    "MediaJobCreate",
    "媒体处理不接受任意URL/provider或模型密钥",
    {
        "type": enum("任务类型", "tts", "asr", "ocr"),
        "input_asset_id": ID,
        "source_turn_id": ID,
        "language": enum("语言", "zh-CN", "en-US"),
        "voice_code": text("受控音色代码", 64),
    },
    optional=("input_asset_id", "source_turn_id", "language", "voice_code"),
    owner="M4",
    oneOf=[
        {
            "properties": {"type": {"const": "tts"}},
            "required": ["source_turn_id"],
            "not": {"required": ["input_asset_id"]},
        },
        {
            "properties": {"type": {"enum": ["asr", "ocr"]}},
            "required": ["input_asset_id"],
            "not": {"required": ["source_turn_id"]},
        },
    ],
    rules=(
        "TTS只读取本人已完成轮次正文；ASR/OCR核验输入owner与类型；文本、密钥不写任务params。",
    ),
)
model(
    "Transcript",
    "本人录音转写与提炼",
    {
        "asset_id": ID,
        "text": text("转写正文，不进日志", 100000),
        "key_points": array(text("重点", 500), "重点提炼", 50),
        "is_mock": boolean("来源标识"),
    },
    owner="M4",
    db="受控派生文本存储，media_jobs结果通过media_assets授权关联",
)
model(
    "AvatarProfile",
    "唯一的跨设备数字人/语音偏好所有者M4",
    {
        "config_version_id": ID,
        "auto_play": boolean("默认false，不能未征同意自动播报"),
        "volume": {"type": "number", "minimum": 0, "maximum": 1, "description": "音量"},
        "speech_rate": {
            "type": "number",
            "minimum": 0.5,
            "maximum": 2,
            "description": "语速",
        },
        "subtitles_enabled": boolean("字幕开关"),
        **BASE_TIMES,
    },
    owner="M4",
    db="avatar_profiles",
)
model(
    "AvatarProfilePatch",
    "本人的偏好更新",
    {
        "config_version_id": ID,
        "auto_play": boolean("默认false"),
        "volume": {"type": "number", "minimum": 0, "maximum": 1, "description": "音量"},
        "speech_rate": {
            "type": "number",
            "minimum": 0.5,
            "maximum": 2,
            "description": "语速",
        },
        "subtitles_enabled": boolean("字幕"),
    },
    optional=(
        "config_version_id",
        "auto_play",
        "volume",
        "speech_rate",
        "subtitles_enabled",
    ),
    owner="M4",
    minProperties=1,
)
model(
    "PlaybackCreate",
    "客户端播报遥测，不是测得的学习时长",
    {
        "utterance_id": ID,
        "turn_id": ID,
        "config_version_id": ID,
        "is_mock": boolean("来源"),
    },
    owner="M4",
)
model(
    "Playback",
    "播报唯一终态",
    {
        "id": ID,
        "utterance_id": ID,
        "status": enum("状态", "started", "completed", "stopped", "error"),
        "stop_reason": nullable(
            enum("停止原因", "user_stop", "replaced", "component_unmounted")
        ),
        "started_at": TIME,
        "ended_at": nullable(TIME),
    },
    owner="M4",
    db="playback_records",
)
model(
    "PlaybackPatch",
    "只允许started进入一个终态",
    {
        "status": enum("终态", "completed", "stopped", "error"),
        "stop_reason": nullable(
            enum("停止原因", "user_stop", "replaced", "component_unmounted")
        ),
        "error_code": nullable(text("脱敏错误码", 64)),
    },
    optional=("stop_reason", "error_code"),
    owner="M4",
    rules=(
        "条件UPDATE校验原状态；重复相同终态幂等，竞争不同终态409；error/stopped补相应原因。",
    ),
)
model(
    "FocusCreate",
    "用户主动开始专注计时，不采集摄像头或生理数据",
    {"course_id": nullable(ID)},
    optional=("course_id",),
    owner="M4",
)
model(
    "FocusSession",
    "服务端计时区间",
    {
        "id": ID,
        "course_id": nullable(ID),
        "status": enum("状态", "running", "completed", "cancelled"),
        "started_at": TIME,
        "ended_at": nullable(TIME),
        "duration_seconds": nullable(number("服务端核验秒数", 0, 86400)),
    },
    owner="M4",
    db="focus_sessions",
)
model(
    "FocusPatch",
    "结束本人计时，不接受客户端自报时长",
    {"status": enum("目标终态", "completed", "cancelled")},
    owner="M4",
)

SCHEMAS["MetricNumber"] = {
    "description": "未知不能用0代替；确认无活动才known+0",
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "state": {"const": "known", "type": "string"},
                "value": {"type": "number", "minimum": 0},
                "algorithm": text("统计口径", 64),
            },
            "required": ["state", "value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "state": {"const": "unknown", "type": "string"},
                "reason": enum(
                    "未知原因",
                    "no_events_in_period",
                    "duration_source_unavailable",
                    "not_observed",
                ),
            },
            "required": ["state", "reason"],
            "additionalProperties": False,
        },
    ],
    "x-owner": "M6",
}
model(
    "StatisticsPeriod",
    "半开统计区间[from,to)，按IANA时区日历切日",
    {
        "from": TIME,
        "to": TIME,
        "timezone": text("IANA时区", 64),
        "days": number("日数", 1, 366),
    },
    owner="M6",
)
model(
    "Coverage",
    "当前授权范围的数据覆盖率",
    {
        "student_count": number("当前授权学生数"),
        "students_with_data": number("有数据学生"),
        "students_without_data": number("无数据学生"),
    },
    owner="M6",
)
model(
    "Consumption",
    "响应消费完整度，不把最大时间当提交游标",
    {
        "data_state": enum("完整度", "complete", "partial", "unknown"),
        "upstream_watermark": nullable(TIME),
    },
    owner="M6",
)
model(
    "StatisticsSummary",
    "班级汇总",
    {
        "total_duration_seconds": ref("MetricNumber"),
        "active_student_count": ref("MetricNumber"),
        "submission_count": ref("MetricNumber"),
        "coverage": ref("Coverage"),
    },
    owner="M6",
)
model(
    "WeakQuestionType",
    "题型薄弱点，不与章节错题数混排",
    {
        "key": QUESTION,
        "label": nullable(text("展示名", 100)),
        "error_rate": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "错误率",
        },
        "sample_size": number("有效判分样本"),
        "insufficient_sample": boolean("样本少于5时为true"),
    },
    owner="M6",
)
model(
    "WeakChapter",
    "章节错题维度，无记录不制造0行",
    {
        "key": ID,
        "label": nullable(text("章节标题", 100)),
        "mistake_count": number("收录数"),
        "resolved_count": number("已解决数"),
        "sample_size": number("样本"),
        "insufficient_sample": boolean("样本不足"),
    },
    owner="M6",
)
model(
    "WeakPoints",
    "两种量纲分别排序",
    {
        "by_question_type": array(ref("WeakQuestionType"), "题型", 5),
        "by_chapter": array(ref("WeakChapter"), "章节", 100),
    },
    owner="M6",
)
model(
    "StudentStatistics",
    "教师当前授权范围内的学生摘要，不能读取对话全文",
    {
        "user_id": ID,
        "display_name": nullable(text("展示名", 100)),
        "data_state": enum("时长数据状态", "known", "unknown"),
        "duration_seconds": ref("MetricNumber"),
        "submission_count": ref("MetricNumber"),
        "weakest_chapter": nullable(ref("WeakChapter")),
    },
    owner="M6",
)
model(
    "ClassOverview",
    "班级概览候选v2，沿用已合入内核的统计口径",
    {
        "class_id": ID,
        "course_id": ID,
        "period": ref("StatisticsPeriod"),
        "data_through": nullable(TIME),
        "consumption": ref("Consumption"),
        "generated_at": TIME,
        "summary": ref("StatisticsSummary"),
        "weak_points": ref("WeakPoints"),
        "students": ref(page("StudentStatistics")),
    },
    owner="M6",
    db="analytics_daily_metrics/processed_events；当前main仅InMemory",
    rules=(
        "历史按事件class快照，查询按当前教师授权裁剪；源故障503而非空成功；按指定timezone过滤不跨时区重复求和。",
    ),
)
model(
    "ReportCreate",
    "请求本人或当前授权班级报告，恰好一种目标",
    {
        "student_user_id": ID,
        "class_id": ID,
        "period_start": TIME,
        "period_end": TIME,
        "timezone": text("IANA时区，范围需合法", 64),
    },
    optional=("student_user_id", "class_id"),
    owner="M6",
    oneOf=[{"required": ["student_user_id"]}, {"required": ["class_id"]}],
)
model(
    "KnowledgeMastery",
    "雷达图维度必须带样本和未知状态",
    {
        "key": text("受控知识点", 100),
        "mastery": nullable({"type": "number", "minimum": 0, "maximum": 1}),
        "sample_count": number("样本数"),
        "data_state": enum("状态", "known", "unknown", "partial"),
    },
    owner="M6",
)
model(
    "LearningReport",
    "个人或班级成长报告；未知指标不编分数",
    {
        "id": ID,
        "student_user_id": nullable(ID),
        "class_id": nullable(ID),
        "period_start": TIME,
        "period_end": TIME,
        "data_through": nullable(TIME),
        "duration_seconds": ref("MetricNumber"),
        "knowledge_points": array(ref("KnowledgeMastery"), "雷达维度", 100),
        "suggestions": array(
            text("有样本依据的建议，不含其他学生正文", 500), "建议", 10
        ),
        "generated_at": TIME,
    },
    owner="M6",
    db="analytics_report_snapshots/report_jobs",
)
model(
    "QuarantinedEvent",
    "失败事件管理，只返回引用和脱敏原因",
    {
        "id": ID,
        "event_id": ID,
        "consumer_id": ID,
        "error_code": text("错误码", 64),
        "status": enum("隔离状态", "open", "retry_ready", "resolved"),
        "attempts": number("尝试数", 1),
        "first_failed_at": TIME,
        "last_failed_at": TIME,
    },
    owner="M6",
    db="analytics_quarantined_events",
)
model(
    "ReplayCreate",
    "受控重放，不改源事件",
    {"reason": text("审计理由，禁止敏感正文", 300)},
    owner="M6",
)

model(
    "AdminUserCreate",
    "管理员创建课程演示账号，无开放手机号注册",
    {
        "username": text("ASCII登录名", 64, pattern=r"^[A-Za-z0-9_.-]{1,64}$"),
        "display_name": text("展示名", 100),
        "role": ROLE,
        "initial_password": {
            **text("仅一次输入，服务端加盐哈希，不回显", 128, 12),
            "writeOnly": True,
        },
    },
)
model(
    "AdminUserPatch",
    "角色和停用由独立授权服务处理并审计",
    {"role": ROLE, "status": enum("账号状态", "active", "disabled")},
    optional=("role", "status"),
    minProperties=1,
    rules=("禁止停用最后一名有效管理员；角色变更撤销旧会话，不凭JWT旧role继续授权。",),
)
model(
    "ConfigCreate",
    "版本化配置，不接受明文密钥或任意provider URL",
    {
        "config_key": enum(
            "本轮允许配置键", "upload_limits", "session_policy", "avatar_style"
        ),
        "value": text("经过键专属schema校验的JSON文本，不含秘密", 8000),
    },
    db="system_config_versions/avatar_config_versions；value入库为有版本JSON对象",
    rules=(
        "value必须解析为对象并匹配config_key专属schema；schemaVersion不得JSON null；未知键拒绝。",
    ),
)
model(
    "ConfigVersion",
    "配置目录元数据，不返回敏感值",
    {
        "id": ID,
        "config_key": text("配置键", 64),
        "version": number("版本", 1),
        "status": enum("生命周期", "draft", "active", "retired"),
        "created_at": TIME,
        "activated_at": nullable(TIME),
        "retired_at": nullable(TIME),
    },
    db="system_config_versions/avatar_config_versions",
)
model(
    "ConfigStatusPatch",
    "配置发布或退役，不能伪造发布时间",
    {"status": enum("目标状态", "active", "retired")},
    rules=(
        "draft→active→retired；未发布草稿不能直接退役；同key仅一个active，与审计同事务。",
    ),
)
model(
    "AuditEntry",
    "最小审计元数据，禁止Token、密码、录音或完整问答",
    {
        "id": ID,
        "actor_user_id": nullable(ID),
        "action": text("受控动作码", 64),
        "resource_id": nullable(ID),
        "result": enum("结果", "success", "denied", "failed"),
        "trace_id": text("服务端请求号", 36, pattern=r"^req_[0-9a-f]{32}$"),
        "created_at": TIME,
    },
    db="admin_audit_logs",
)
model(
    "Guide",
    "章节化导学、重点难点和考点",
    {
        "course_id": ID,
        "chapter_id": nullable(ID),
        "explanation": text("口语化导学正文", 8000),
        "key_points": array(text("重点难点或易错点", 300), "知识点", 50),
        "examples": array(text("讲解示例", 1000), "示例", 10),
        "is_mock": boolean("来源"),
    },
    owner="M3",
    db="v2新增受控派生内容；需单独设计存储及有效版本，不冒充#79已有字段",
)
model(
    "GuideJobCreate",
    "按课程或章节生成导学，不接受任意模型提示词",
    {
        "chapter_id": nullable(ID),
        "mode": enum("用途", "preview", "review", "exam_cram"),
    },
    optional=("chapter_id",),
    owner="M3",
)
model(
    "ExamPaperCreate",
    "教师导入获许可真题/模拟卷",
    {
        "course_id": ID,
        "document_id": ID,
        "title": text("试卷名", 100),
        "duration_minutes": number("建议考试分钟", 1, 300),
    },
    owner="M5",
)
model(
    "ExamPaper",
    "备考试卷目录",
    {
        "id": ID,
        "course_id": ID,
        "title": text("试卷名", 100),
        "duration_minutes": number("分钟", 1, 300),
        "question_count": number("题数", 1, 200),
        "published_at": nullable(TIME),
    },
    owner="M5",
    db="S2新增exam_papers/exam_questions，需独立迁移，#79未覆盖",
)
model(
    "ExamAttemptCreate",
    "开启本人模拟考试",
    {"mode": enum("模式", "practice", "timed")},
    owner="M5",
)
model(
    "ExamAttempt",
    "考试进度，不在结束前返回答案",
    {
        "id": ID,
        "paper_id": ID,
        "status": enum("状态", "in_progress", "submitted", "graded", "aborted"),
        "started_at": TIME,
        "submitted_at": nullable(TIME),
    },
    owner="M5",
    db="S2新增exam_attempts/exam_answers，需迁移",
)
model(
    "ExamAnswerPatch",
    "考试内逐题作答",
    {"question_id": ID, "answer": ref("StudentAnswer")},
    owner="M5",
)
