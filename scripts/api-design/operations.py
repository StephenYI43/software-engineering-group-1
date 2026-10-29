"""Complete resource operation inventory for the v2 candidate, Issue #80."""

from contract_model import (
    ID,
    SCHEMAS,
    TIME,
    array,
    boolean,
    enum,
    model,
    nullable,
    number,
    page,
    ref,
    text,
)

OPERATIONS: list[dict] = []
GROUPS = {
    "P": ("平台身份", "M1"),
    "C": ("课程与访问关系", "M5"),
    "A": ("作业与提交", "M5"),
    "W": ("错题与训练", "M5"),
    "L": ("计划与提醒", "M5"),
    "T": ("智能答疑", "M3"),
    "K": ("知识库文件", "M3"),
    "V": ("数字人与媒体", "M4"),
    "R": ("学习分析", "M6"),
    "M": ("管理后台", "M1"),
    "G": ("智能导学", "M3"),
    "E": ("备考模拟", "M5"),
}
ALL = ("student", "teacher", "admin")
STUDENT = ("student",)
TEACHER = ("teacher", "admin")
ADMIN = ("admin",)
OWN = "必须从已验证会话取得actor；本人私有资源逐条校验owner，越权与不存在统一404。"
COURSE = (
    "先核验当前课程/班级访问关系及父子资源一致性；"
    "教师仅管理有效授课班级，管理员需明确课程管理授权。"
)
WRITE = "repository仅flush；service提交业务、对应事件和必要审计的同一事务；回滚不得留半成品。"
ADMIN_SCOPE = (
    "校验当前管理员身份及显式管理范围；目标不是管理员本人资源。"
    "访问角色、配置和隔离重放分别检查对应管理权限并审计，范围外404。"
)
REPORT_ACCESS = (
    "学生仅本人报告；教师仅当前有效授课班级的汇总报告；"
    "管理员须显式管理授权，不默认读取学生全文或私人报告。"
)


def op(
    group,
    method,
    path,
    name,
    result=None,
    request=None,
    *,
    roles=ALL,
    access=OWN,
    status=None,
    legacy="new-design",
    phase="S1",
    media="json",
    paged=False,
    filters=(),
    policy="",
    owner=None,
    consumers="M2/M6",
):
    index = 1 + sum(x["group"] == group for x in OPERATIONS)
    if group == "M" or path.startswith("/admin/"):
        access = ADMIN_SCOPE
    ident = f"{group}{index:02d}"
    status = status or (201 if method == "POST" else 204 if method == "DELETE" else 200)
    natural = method in {"GET", "DELETE"} or path.endswith(("/logout", "/stop"))
    OPERATIONS.append(
        {
            "id": ident,
            "group": group,
            "tag": GROUPS[group][0],
            "method": method,
            "path": "/api/v2" + path,
            "summary": name,
            "operation_id": f"{group.lower()}_{index:02d}_{method.lower()}",
            "owner": owner or GROUPS[group][1],
            "consumers": consumers,
            "request": request,
            "response": page(result) if paged else result,
            "roles": list(roles),
            "access": access,
            "status": status,
            "legacy_stage": legacy,
            "phase": phase,
            "media": media,
            "paged": paged,
            "filters": list(filters),
            "idempotency": "authentication"
            if path.endswith("/auth/login")
            else "natural"
            if natural
            else "required",
            "optimistic_lock": method == "PATCH" and not path.endswith("/reminders/{reminder_id}"),
            "policy": policy
            or (
                WRITE
                if method in {"POST", "PATCH", "DELETE"}
                else "授权后读取，私有数据Cache-Control: no-store。"
            ),
            "implementation": "design-only",
        }
    )


model(
    "ChapterContent",
    "章节正文单独读取，列表不携带大正文",
    {
        "chapter_id": ID,
        "content": text("授权正文，Markdown展示转义并禁用原始HTML", 100000),
        "documents": array(ref("Document"), "本章节允许访问的附件元数据", 20),
    },
    owner="M5",
    db="chapters与授权文档组合",
)
model(
    "ImportCreate",
    "对已上传文件发起解析，不能指定任意解析器或URL",
    {"parser": enum("受控解析器，版本由服务端冻结", "default")},
    owner="M3",
)
model(
    "GenerateCreate",
    "生成任务的显式输入白名单，不接受系统提示词",
    {"mode": enum("生成用途", "preview", "review", "exam_cram")},
    owner="M3",
)
model("EmptyRequest", "无业务字段；需要的身份来自会话", {})
model(
    "GuideJobRequest",
    "课程导学任务",
    {
        "chapter_id": nullable(ID),
        "mode": enum("用途", "preview", "review", "exam_cram"),
    },
    optional=("chapter_id",),
    owner="M3",
)

op(
    "P",
    "GET",
    "/health",
    "存活检查",
    "Health",
    roles=(),
    access="匿名只读，不检查DB、模型或身份。",
    legacy="main",
)
op(
    "P",
    "POST",
    "/auth/login",
    "账号登录",
    "LoginResult",
    "LoginRequest",
    roles=(),
    status=200,
    access="匿名认证入口；按IP与账号组合限流，不区分账号不存在与密码错误。",
    legacy="main",
    policy="不得缓存认证响应或记录请求体；校验密码后签发可撤销会话，审计不含明文Token。",
)
op(
    "P",
    "POST",
    "/auth/logout",
    "退出当前会话",
    "LogoutResult",
    legacy="main",
    policy="只从经服务端验签的当前Bearer凭证提取jti；重复退出幂等，不接受body中的任意jti。",
    status=200,
)
op("P", "GET", "/users/me", "读取本人身份与资料", "Profile")
op("P", "PATCH", "/users/me", "更新本人资料", "Profile", "ProfilePatch")
op(
    "P",
    "POST",
    "/users/batch-queries",
    "授权用户摘要批量查询",
    "UserBatchResult",
    "UserBatchRequest",
    status=200,
    access="本人或当前授课/管理范围内学生；逐项授权，未返回ID不说明是否存在。",
    policy="只读POST不创建用户；最多50个ID，批量查询避免N+1，不开放全站通讯录。",
)
op(
    "P",
    "GET",
    "/jobs/{job_id}",
    "统一读取授权任务状态",
    "Job",
    owner="M1入口/M3或M4或M6提供方",
    policy="M1只读组合各域公开get_owned_job，不直写别域表；每域验证actor和归属，未知或未授权统一404。",
)
op(
    "P",
    "GET",
    "/jobs/{job_id}/result",
    "读取已完成授权任务结果",
    "JobResult",
    owner="M1入口/实际领域提供方",
    policy="仅succeeded可读取；未完成409、失败返回脱敏失败状态；按领域再次核验owner和课程权限，不返回任意外部URL。",
)

op(
    "C",
    "GET",
    "/courses",
    "课程列表",
    "Course",
    paged=True,
    filters=("subject",),
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "POST",
    "/courses",
    "教师创建课程",
    "Course",
    "CourseCreate",
    roles=TEACHER,
    access="验证当前教师或课程管理创建权限；创建者从actor取得，不要求尚不存在的新课程已有授课关系。新班级的初始授课关系由M5在同事务建立。",
    legacy="contract-only",
)
op(
    "C",
    "GET",
    "/courses/{course_id}",
    "课程详情",
    "Course",
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "GET",
    "/courses/{course_id}/classes",
    "教学班列表",
    "Class",
    paged=True,
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "POST",
    "/courses/{course_id}/classes",
    "创建教学班",
    "Class",
    "ClassCreate",
    roles=TEACHER,
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "GET",
    "/courses/{course_id}/chapters",
    "课程章节列表",
    "Chapter",
    paged=True,
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "POST",
    "/courses/{course_id}/chapters",
    "创建课程章节",
    "Chapter",
    "ChapterCreate",
    roles=TEACHER,
    access=COURSE,
    legacy="contract-only",
)
op(
    "C",
    "GET",
    "/chapters/{chapter_id}/content",
    "读取章节正文",
    "ChapterContent",
    access=COURSE,
)
op(
    "C",
    "GET",
    "/classes/{class_id}/enrollments",
    "查询本班选课关系",
    "Enrollment",
    roles=TEACHER,
    access=COURSE,
    paged=True,
)
op(
    "C",
    "POST",
    "/classes/{class_id}/enrollments",
    "教师为本班添加学生",
    "Enrollment",
    "EnrollmentWrite",
    roles=TEACHER,
    access=COURSE,
    owner="M1入口/M5表与service",
    policy=WRITE + "student_user_id是被管理对象，不是actor；禁止学生自行调用。",
)
op(
    "C",
    "DELETE",
    "/classes/{class_id}/enrollments/{student_user_id}",
    "结束选课关系",
    roles=TEACHER,
    access=COURSE,
    owner="M1入口/M5表与service",
    policy="关闭有效区间并审计，不删除历史；重复结束204，未授权404。",
)
op(
    "C",
    "GET",
    "/classes/{class_id}/teaching-assignments",
    "查询授课关系",
    "TeachingAssignment",
    roles=TEACHER,
    access=COURSE,
    paged=True,
)
op(
    "C",
    "POST",
    "/classes/{class_id}/teaching-assignments",
    "分配授课教师",
    "TeachingAssignment",
    "TeachingWrite",
    roles=ADMIN,
    access=COURSE,
    owner="M1入口/M5表与service",
)
op(
    "C",
    "DELETE",
    "/classes/{class_id}/teaching-assignments/{teacher_user_id}",
    "撤销授课关系",
    roles=ADMIN,
    access=COURSE,
    owner="M1入口/M5表与service",
)
op(
    "C",
    "POST",
    "/classes/{class_id}/enrollment-requests",
    "学生申请加入班级",
    "EnrollmentRequest",
    "EnrollmentRequestCreate",
    roles=STUDENT,
    phase="S2",
    access="班级必须允许当前学校演示范围内申请；申请不等于授权。",
    owner="M1入口/M5管理实体",
    policy="同一学生/班级至多一个pending；新管理表未迁移前不开放此路由，不能以任意class_id直接授予课程访问权。",
)
op(
    "C",
    "GET",
    "/classes/{class_id}/enrollment-requests",
    "本班入班申请列表",
    "EnrollmentRequest",
    roles=TEACHER,
    phase="S2",
    access=COURSE,
    paged=True,
)
op(
    "C",
    "PATCH",
    "/enrollment-requests/{enrollment_request_id}",
    "审批入班申请",
    "EnrollmentRequest",
    "EnrollmentDecision",
    roles=TEACHER,
    phase="S2",
    access=COURSE,
    policy=WRITE + "仅pending可审核，批准才调用M5关系写服务，重复或竞争状态按幂等/409处理。",
)
op(
    "C",
    "POST",
    "/chapter-view-intents",
    "提交章节阅读意图",
    "LearningEventReceipt",
    "ChapterViewedIntent",
    roles=STUDENT,
    status=201,
    access=COURSE,
    owner="M1入口/M5事务",
    policy=WRITE
    + (
        "同用户/同幂等键同参数返回原回执，换参409；"
        "服务端生成event/user/time/trace，不接受通用event_type。"
    ),
)

op(
    "A",
    "GET",
    "/courses/{course_id}/assignments",
    "课程作业列表",
    "Assignment",
    paged=True,
    access=COURSE,
    legacy="contract-only",
    filters=("status",),
)
op(
    "A",
    "POST",
    "/courses/{course_id}/assignments",
    "教师创建作业",
    "Assignment",
    "AssignmentCreate",
    roles=TEACHER,
    access=COURSE,
    legacy="contract-only",
)
op(
    "A",
    "GET",
    "/assignments/{assignment_id}",
    "作业详情与公开选项",
    "Assignment",
    access=COURSE,
    legacy="contract-only",
)
op(
    "A",
    "PATCH",
    "/assignments/{assignment_id}",
    "教师编辑作业",
    "Assignment",
    "AssignmentPatch",
    roles=TEACHER,
    access=COURSE,
    policy=WRITE + "有提交后改答案须另建版本并显式重判，不能回改历史依据。",
)
op(
    "A",
    "GET",
    "/assignments/{assignment_id}/answer-key",
    "教师读取标准答案",
    "AnswerKey",
    roles=TEACHER,
    access=COURSE,
    policy="仅本班授课教师或明确授权管理员；学生403，资源不在教师范围404；单独审计，绝不并入学生列表。",
)
op(
    "A",
    "POST",
    "/assignments/{assignment_id}/submissions",
    "学生提交答案",
    "Submission",
    "SubmissionCreate",
    roles=STUDENT,
    access=COURSE,
    legacy="contract-only",
)
op(
    "A",
    "GET",
    "/assignments/{assignment_id}/submissions/me",
    "本人提交状态",
    "SubmissionStatus",
    roles=STUDENT,
    access=COURSE,
    legacy="contract-only",
)
op(
    "A",
    "GET",
    "/assignments/{assignment_id}/submissions",
    "教师查看本班提交",
    "Submission",
    roles=TEACHER,
    access=COURSE,
    paged=True,
    legacy="contract-only",
    filters=("graded",),
)
op(
    "A",
    "PATCH",
    "/submissions/{submission_id}",
    "截止前修改本人未批阅提交",
    "Submission",
    "SubmissionCreate",
    roles=STUDENT,
    policy=WRITE
    + (
        "已过截止或已批阅409；同键重复不重判，答案变化产生可追溯新事件，"
        "M6仍按submission_id计一次提交。"
    ),
)
op(
    "A",
    "PATCH",
    "/submissions/{submission_id}/grading",
    "教师批阅与改判",
    "Submission",
    "GradingPatch",
    roles=TEACHER,
    access=COURSE,
    legacy="contract-only",
)

op(
    "W",
    "POST",
    "/mistakes",
    "主动加入错题本",
    "Mistake",
    "MistakeCreate",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "W",
    "GET",
    "/mistakes",
    "个人错题列表",
    "Mistake",
    roles=STUDENT,
    paged=True,
    legacy="contract-only",
    filters=("course_id", "status"),
)
op(
    "W",
    "GET",
    "/mistakes/{mistake_id}",
    "本人错题详情",
    "Mistake",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "W",
    "PATCH",
    "/mistakes/{mistake_id}",
    "更新错题掌握状态",
    "Mistake",
    "MistakePatch",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "W",
    "DELETE",
    "/mistakes/{mistake_id}",
    "删除本人错题记录",
    roles=STUDENT,
    legacy="contract-only",
    policy="授权清理本人记录和派生引用，不删其他学生数据；成功204，重复删除仍204，未知/越权不泄露存在性。",
)
op(
    "W",
    "GET",
    "/mistakes/{mistake_id}/similar-questions",
    "推荐已授权同类习题",
    "Assignment",
    roles=STUDENT,
    paged=True,
    phase="S2",
    policy="只读已授权题库缓存，不在GET内触发收费模型或泄露answer_key；无候选返回空分页。",
)

op(
    "L",
    "POST",
    "/study-plans",
    "创建计划或保存答疑建议",
    "StudyPlan",
    "PlanCreate",
    roles=STUDENT,
    legacy="contract-only",
    policy=WRITE
    + "source=tutoring仅接受source_turn_id，M5调用M3受控取用函数取内容，拒绝浏览器伪造items。",
)
op(
    "L",
    "GET",
    "/study-plans",
    "本人计划列表",
    "StudyPlan",
    roles=STUDENT,
    paged=True,
    legacy="contract-only",
    filters=("status",),
)
op(
    "L",
    "GET",
    "/study-plans/{plan_id}",
    "计划详情",
    "StudyPlan",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "L",
    "PATCH",
    "/study-plans/{plan_id}",
    "修改计划",
    "StudyPlan",
    "PlanPatch",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "L",
    "POST",
    "/study-plans/{plan_id}/items",
    "新增计划项",
    "PlanItem",
    "PlanItemInput",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "L",
    "PATCH",
    "/study-plans/{plan_id}/items/{item_id}",
    "修改或完成计划项",
    "PlanItem",
    "PlanItemPatch",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "L",
    "DELETE",
    "/study-plans/{plan_id}/items/{item_id}",
    "删除计划项",
    roles=STUDENT,
    legacy="contract-only",
)
op(
    "L",
    "GET",
    "/reminders",
    "本人站内提醒",
    "Reminder",
    roles=STUDENT,
    paged=True,
    legacy="contract-only",
    filters=("is_read",),
)
op(
    "L",
    "PATCH",
    "/reminders/{reminder_id}",
    "标记提醒已读或未读",
    "Reminder",
    "ReminderPatch",
    roles=STUDENT,
    legacy="contract-only",
)

op(
    "T",
    "POST",
    "/tutoring/sessions",
    "创建私有答疑会话",
    "TutoringSession",
    "SessionCreate",
    roles=STUDENT,
)
op(
    "T",
    "GET",
    "/tutoring/sessions",
    "本人会话列表",
    "TutoringSession",
    roles=STUDENT,
    paged=True,
)
op(
    "T",
    "GET",
    "/tutoring/sessions/{session_id}",
    "读取本人会话",
    "TutoringSession",
    roles=STUDENT,
)
op(
    "T",
    "GET",
    "/tutoring/sessions/{session_id}/turns",
    "本人答疑轮次历史",
    "TutoringTurn",
    roles=STUDENT,
    paged=True,
)
op(
    "T",
    "GET",
    "/tutoring/turns/{turn_id}",
    "读取轮次完成或中断状态",
    "TutoringTurn",
    roles=STUDENT,
)
op(
    "T",
    "GET",
    "/tutoring/turns/{turn_id}/plan-suggestion",
    "受控读取本人完整建议",
    "PlanSuggestion",
    roles=STUDENT,
    policy="不存在、无权、未完成或无建议统一404；M5同进程用公开service一次完成owner校验与读取，前端不负责转存。",
)
op(
    "T",
    "POST",
    "/tutoring/sessions/{session_id}/messages",
    "流式引导答疑",
    "TutoringResponse",
    "MessageCreate",
    roles=STUDENT,
    status=200,
    media="sse",
    legacy="branch",
    policy="开流前鉴权与课程核验；同键已有轮次返回409和本人turn_id，绝不重复调用模型；新一轮须新键。started/delta/唯一终帧，失败不推进。",
)
op(
    "T",
    "POST",
    "/tutoring/sessions/{session_id}/turns/{turn_id}/stop",
    "停止本人答疑轮次",
    roles=STUDENT,
    status=204,
    legacy="branch",
    policy="已知本人轮次统一204空体，未知/越权404；保持SSE等stopped终帧，5秒兜底才断连。断连只做内部aborted结算，不伪造终帧。",
)

op(
    "K",
    "POST",
    "/courses/{course_id}/documents",
    "上传授权课件",
    "Document",
    "DocumentUpload",
    roles=TEACHER,
    access=COURSE,
    media="multipart",
    policy="流式上限20MiB，PDF/PPTX/DOCX魔数与解压比/页数上限；文件先检疫，非可信内容不得执行。文件落存储后登记，失败清理孤儿临时对象。",
)
op(
    "K",
    "GET",
    "/courses/{course_id}/documents",
    "当前授权文档列表",
    "Document",
    paged=True,
    access=COURSE,
)
op(
    "K",
    "GET",
    "/documents/{document_id}",
    "文档元数据与版本",
    "Document",
    access=COURSE,
)
op(
    "K",
    "POST",
    "/documents/{document_id}/import-jobs",
    "异步解析与切分课件",
    "Job",
    "ImportCreate",
    roles=TEACHER,
    access=COURSE,
    status=202,
)
op(
    "K",
    "GET",
    "/document-import-jobs/{job_id}",
    "查询本人或授权课程解析任务",
    "Job",
    access=COURSE,
)
op(
    "K",
    "GET",
    "/documents/{document_id}/content",
    "鉴权后下载原文件",
    access=COURSE,
    media="binary",
    policy="每次重新授权，Cache-Control:no-store，Content-Disposition:attachment并清洗文件名，存储key和长期签名URL不暴露。",
)
op(
    "K",
    "DELETE",
    "/documents/{document_id}",
    "撤回并清理课件",
    roles=TEACHER,
    access=COURSE,
    policy="先阻断新检索和下载，再清理对象/片段/引用派生内容，按批准保留策略执行；失败可审计重试，不以FK永久拒删。",
)
op(
    "K",
    "POST",
    "/documents/{document_id}/grants",
    "授权个人或本课程班级",
    "DocumentGrant",
    "DocumentGrantCreate",
    roles=TEACHER,
    access=COURSE,
)
op(
    "K",
    "GET",
    "/documents/{document_id}/grants",
    "文档授权记录",
    "DocumentGrant",
    roles=TEACHER,
    access=COURSE,
    paged=True,
)
op(
    "K",
    "DELETE",
    "/documents/{document_id}/grants/{grant_id}",
    "撤销文档授权",
    roles=TEACHER,
    access=COURSE,
)
op(
    "K",
    "POST",
    "/documents/{document_id}/summary-jobs",
    "生成课件重点提炼",
    "Job",
    "GenerateCreate",
    access=COURSE,
    status=202,
    phase="S2",
)
op(
    "K",
    "GET",
    "/documents/{document_id}/summary",
    "读取已生成课件提炼",
    "DocumentSummary",
    access=COURSE,
    phase="S2",
    policy="只读已授权派生内容；未生成404或生成未终结409，不在GET触发收费模型。",
)

op(
    "V",
    "POST",
    "/media-assets",
    "上传题目图片或已同意录音",
    "MediaAsset",
    "MediaUpload",
    media="multipart",
)
op("V", "GET", "/media-assets/{asset_id}", "本人媒体元数据", "MediaAsset")
op("V", "GET", "/media-assets/{asset_id}/content", "下载本人媒体文件", media="binary")
op(
    "V",
    "DELETE",
    "/media-assets/{asset_id}",
    "清理本人媒体与派生文本",
    policy="先撤回并禁止使用，再清理对象/派生文本/缓存；失败留审计重试，不在日志复制录音或正文。",
)
op(
    "V",
    "POST",
    "/media-jobs",
    "创建TTS或ASR或OCR任务",
    "Job",
    "MediaJobCreate",
    status=202,
)
op("V", "GET", "/media-jobs/{job_id}", "查询本人媒体任务", "Job")
op(
    "V",
    "GET",
    "/media-assets/{asset_id}/transcript",
    "读取本人转写与重点",
    "Transcript",
    phase="S2",
)
op("V", "GET", "/users/me/avatar-profile", "跨设备数字人偏好", "AvatarProfile")
op(
    "V",
    "PATCH",
    "/users/me/avatar-profile",
    "更新唯一语音偏好",
    "AvatarProfile",
    "AvatarProfilePatch",
)
op(
    "V",
    "POST",
    "/playback-records",
    "登记本人完整回答播报",
    "Playback",
    "PlaybackCreate",
)
op(
    "V",
    "PATCH",
    "/playback-records/{playback_id}",
    "提交唯一播报终态",
    "Playback",
    "PlaybackPatch",
)
op(
    "V",
    "POST",
    "/focus-sessions",
    "主动开启专注计时",
    "FocusSession",
    "FocusCreate",
    roles=STUDENT,
    phase="S2",
)
op(
    "V",
    "GET",
    "/focus-sessions",
    "本人专注记录",
    "FocusSession",
    roles=STUDENT,
    paged=True,
    phase="S2",
)
op(
    "V",
    "PATCH",
    "/focus-sessions/{focus_id}",
    "结束本人计时",
    "FocusSession",
    "FocusPatch",
    roles=STUDENT,
    phase="S2",
)

op(
    "R",
    "GET",
    "/analytics/classes/{class_id}/overview",
    "教师本班概览",
    "ClassOverview",
    roles=TEACHER,
    access=COURSE,
    legacy="main-module-unmounted",
    filters=("period", "from", "to", "timezone", "page", "page_size"),
    policy="当前main只有内存聚合内核，尚未挂主应用。真实PG摄取按反连接账本，不按最大时间补扫；同课程双班按事件class快照隔离。",
)
op(
    "R",
    "POST",
    "/report-jobs",
    "创建本人或本班周月报告",
    "Job",
    "ReportCreate",
    status=202,
    access="学生只可指定本人；教师只可指定当前授权班级；管理员也不能默认读取学生对话。",
)
op("R", "GET", "/report-jobs/{job_id}", "查询授权报告任务", "Job")
op(
    "R",
    "GET",
    "/learning-reports/{report_id}",
    "读取本人或授权班级报告",
    "LearningReport",
    access=REPORT_ACCESS,
)
op(
    "R",
    "GET",
    "/learning-reports",
    "授权成长报告列表",
    "LearningReport",
    paged=True,
    access=REPORT_ACCESS,
)
op(
    "R",
    "GET",
    "/admin/analytics/quarantined-events",
    "查询脱敏隔离事件",
    "QuarantinedEvent",
    roles=ADMIN,
    paged=True,
    filters=("status",),
)
op(
    "R",
    "POST",
    "/admin/analytics/quarantined-events/{quarantine_id}/replays",
    "授权重放隔离事件",
    "Job",
    "ReplayCreate",
    roles=ADMIN,
    status=202,
    policy="不改源事件；写retry_ready与操作者审计，成功时ledger/聚合/resolved同事务；open明确partial，不静默跳过。",
)

op(
    "M",
    "POST",
    "/admin/users",
    "管理员创建演示账号",
    "UserSummary",
    "AdminUserCreate",
    roles=ADMIN,
)
op(
    "M",
    "GET",
    "/admin/users",
    "管理范围内用户摘要",
    "UserSummary",
    roles=ADMIN,
    paged=True,
    filters=("role",),
)
op(
    "M",
    "PATCH",
    "/admin/users/{user_id}",
    "调整角色或停用账号",
    "UserSummary",
    "AdminUserPatch",
    roles=ADMIN,
)
op(
    "M",
    "GET",
    "/admin/config-versions",
    "配置版本目录",
    "ConfigVersion",
    roles=ADMIN,
    paged=True,
    filters=("status",),
)
op(
    "M",
    "POST",
    "/admin/config-versions",
    "创建配置草稿",
    "ConfigVersion",
    "ConfigCreate",
    roles=ADMIN,
)
op(
    "M",
    "PATCH",
    "/admin/config-versions/{config_id}/status",
    "发布或退役配置版本",
    "ConfigVersion",
    "ConfigStatusPatch",
    roles=ADMIN,
)
op(
    "M",
    "GET",
    "/admin/audit-logs",
    "读取脱敏审计目录",
    "AuditEntry",
    roles=ADMIN,
    paged=True,
    filters=("from", "to"),
)

op(
    "G",
    "POST",
    "/courses/{course_id}/guide-jobs",
    "生成预习复习或考点导学",
    "Job",
    "GuideJobRequest",
    roles=STUDENT,
    access=COURSE,
    status=202,
    phase="S2",
)
op(
    "G",
    "GET",
    "/guide-jobs/{job_id}",
    "查询本人导学生成任务",
    "Job",
    roles=STUDENT,
    phase="S2",
)
op(
    "G",
    "GET",
    "/courses/{course_id}/guides",
    "读取授权课程导学",
    "Guide",
    roles=STUDENT,
    access=COURSE,
    paged=True,
    phase="S2",
)

op(
    "E",
    "POST",
    "/exam-papers",
    "教师导入真题或模拟卷",
    "ExamPaper",
    "ExamPaperCreate",
    roles=TEACHER,
    access=COURSE,
    phase="S2",
)
op(
    "E",
    "GET",
    "/exam-papers",
    "授权备考试卷列表",
    "ExamPaper",
    paged=True,
    access=COURSE,
    phase="S2",
    filters=("course_id",),
)
op(
    "E",
    "GET",
    "/exam-papers/{paper_id}",
    "授权试卷目录",
    "ExamPaper",
    access=COURSE,
    phase="S2",
)
op(
    "E",
    "GET",
    "/exam-papers/{paper_id}/answer-keys",
    "授课教师读取试卷答案",
    "ExamQuestionKey",
    roles=TEACHER,
    access=COURSE,
    paged=True,
    phase="S2",
    policy="仅本课程有效授课教师或明确授权管理员；学生403，不混入公开试题接口。",
)
op(
    "E",
    "PATCH",
    "/exam-papers/{paper_id}",
    "教师确认并发布试卷",
    "ExamPaper",
    "ExamPaperPatch",
    roles=TEACHER,
    access=COURSE,
    phase="S2",
    policy=WRITE
    + "发布前逐题校验题型/选项/答案并人工确认；已有作答后题目与评分依据不可回改，需要新版本试卷。",
)
op(
    "E",
    "GET",
    "/exam-papers/{paper_id}/questions",
    "读取授权试卷公开题目",
    "ExamQuestion",
    paged=True,
    access=COURSE,
    phase="S2",
    policy="学生限已发布试卷和当前授权课程，授课教师可预览本人课程草稿；题目ID供作答引用，不含answer_key，答案另走answer-keys。",
)
op(
    "E",
    "POST",
    "/exam-papers/{paper_id}/attempts",
    "开始本人模拟考试",
    "ExamAttempt",
    "ExamAttemptCreate",
    roles=STUDENT,
    access=COURSE,
    phase="S2",
)
op(
    "E",
    "GET",
    "/exam-attempts/{attempt_id}",
    "读取本人考试进度",
    "ExamAttempt",
    roles=STUDENT,
    phase="S2",
)
op(
    "E",
    "PATCH",
    "/exam-attempts/{attempt_id}/answers",
    "保存本人逐题答案",
    "ExamAttempt",
    "ExamAnswerPatch",
    roles=STUDENT,
    phase="S2",
)
op(
    "E",
    "POST",
    "/exam-attempts/{attempt_id}/submissions",
    "交卷并触发受控判阅",
    "Job",
    "EmptyRequest",
    roles=STUDENT,
    status=202,
    phase="S2",
)
op(
    "E",
    "PATCH",
    "/exam-attempts/{attempt_id}/grading",
    "授课教师批阅已交卷试题",
    "ExamReport",
    "ExamGradingPatch",
    roles=TEACHER,
    access=COURSE,
    phase="S2",
    policy=WRITE
    + "学生不能调用；成绩变更留版本和审计，未全部批阅返回partial，不把未批阅视为零分或错误。",
)
op(
    "E",
    "GET",
    "/exam-attempts/{attempt_id}/report",
    "读取判阅结果与备考建议",
    "ExamReport",
    roles=STUDENT,
    phase="S2",
)

model(
    "ExamQuestionFeedback",
    "仅本人交卷后的逐题反馈",
    {
        "question_id": ID,
        "is_correct": nullable(boolean("未批阅为null")),
        "score": nullable(number("得分", 0, 10000)),
        "hints": array(text("思路与分步提示，不提前泄露答案键", 1000), "讲解", 10),
    },
    owner="M5/M3",
)
model(
    "ExamReport",
    "试卷结果，主观题未批阅时明确partial",
    {
        "attempt_id": ID,
        "paper_id": ID,
        "state": enum("结果状态", "partial", "graded"),
        "total_score": nullable(number("总分", 0, 2000000)),
        "questions": array(ref("ExamQuestionFeedback"), "逐题反馈", 200),
        "suggestions": array(text("应试时间或知识点建议", 500), "建议", 10),
        "is_mock": boolean("是否模拟生成"),
    },
    owner="M5/M3",
    db="S2新增考试作答/批阅结果",
)
SCHEMAS["JobResult"] = {
    "description": "完成任务的受控结果，不能读取任意存储文件",
    "oneOf": [
        ref(name)
        for name in (
            "Document",
            "DocumentSummary",
            "MediaAsset",
            "Transcript",
            "Guide",
            "LearningReport",
            "ExamReport",
            "QuarantinedEvent",
        )
    ],
    "x-owner": "实际任务领域",
}

# Configuration is a typed object, not a JSON-encoded string container.
model(
    "UploadLimitsConfig",
    "上传安全配置",
    {
        "schema_version": {"type": "string", "const": "1.0"},
        "max_upload_bytes": number("字节上限", 1, 20971520),
        "allowed_mime_types": {
            **array(
                enum(
                    "允许类型",
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "image/png",
                    "image/jpeg",
                    "audio/mpeg",
                    "audio/wav",
                ),
                "类型白名单",
                7,
                1,
            ),
            "uniqueItems": True,
        },
    },
)
model(
    "SessionPolicyConfig",
    "会话策略，不放密钥",
    {
        "schema_version": {"type": "string", "const": "1.0"},
        "session_ttl_seconds": number("Token有效秒数", 300, 86400),
    },
)
model(
    "AvatarStyleConfig",
    "教学风格配置",
    {
        "schema_version": {"type": "string", "const": "1.0"},
        "subject_style": enum("学科风格", "math", "physics", "chemistry", "english", "cs", "other"),
        "tone": enum("语气", "gentle", "neutral", "strict"),
        "avatar_asset_id": ID,
    },
)
model(
    "ConfigCreate",
    "配置值按键分别验证，API字段与DB结构需适配",
    {
        "config_key": enum("配置键", "upload_limits", "session_policy", "avatar_style"),
        "value": {
            "oneOf": [
                ref("UploadLimitsConfig"),
                ref("SessionPolicyConfig"),
                ref("AvatarStyleConfig"),
            ],
            "description": "受控JSON对象，不接受JSON字符串或密钥",
        },
    },
    oneOf=[
        {"properties": {"config_key": {"const": key}, "value": ref(schema)}}
        for key, schema in [
            ("upload_limits", "UploadLimitsConfig"),
            ("session_policy", "SessionPolicyConfig"),
            ("avatar_style", "AvatarStyleConfig"),
        ]
    ],
    db=(
        "system_config_versions/avatar_config_versions；"
        "wire snake_case经服务端映射为既有内部版本对象"
    ),
)

# Declarative parts of the state machines. Cross-row ACL and time comparisons
# remain service checks, never claimed to follow merely from OpenAPI.
SCHEMAS["Job"]["allOf"] = [
    {
        "if": {"properties": {"status": {"enum": ["succeeded", "failed", "cancelled"]}}},
        "then": {"properties": {"finished_at": TIME}},
    },
    {
        "if": {"properties": {"status": {"const": "failed"}}},
        "then": {"properties": {"error_code": text("脱敏失败码", 64)}},
    },
    {
        "if": {"properties": {"status": {"const": "running"}}},
        "then": {"properties": {"started_at": TIME}},
    },
]
SCHEMAS["TutoringTurn"]["allOf"] = [
    {"if": {"properties": {"status": {"const": state}}}, "then": {"properties": props}}
    for state, props in [
        (
            "active",
            {
                "is_complete": {"const": False},
                "settled_at": {"type": "null"},
                "response": {"type": "null"},
            },
        ),
        (
            "completed",
            {
                "is_complete": {"const": True},
                "response": ref("TutoringResponse"),
                "settled_at": TIME,
            },
        ),
        (
            "aborted",
            {
                "is_complete": {"const": False},
                "response": {"type": "null"},
                "settled_at": TIME,
                "abort_reason": enum(
                    "中断原因",
                    "client_stop",
                    "client_disconnect",
                    "model_error",
                    "retrieval_error",
                    "server_restart",
                ),
            },
        ),
    ]
]

# Event envelopes are contracts between domains, not a browser-selected POST.
PAYLOADS = {
    "assignment_submitted": (
        "SubmissionEventPayload",
        {
            "submission_id": ID,
            "assignment_id": ID,
            "question_type": SCHEMAS["Assignment"]["properties"]["question_type"],
            "is_correct": nullable(boolean("客观题判定或未批阅null")),
            "score": nullable(number("得分", 0, 10000)),
        },
    ),
    "assignment_graded": (
        "GradingEventPayload",
        {
            "submission_id": ID,
            "is_correct": boolean("最终结论"),
            "score": nullable(number("得分", 0, 10000)),
        },
    ),
    "mistake_recorded": (
        "MistakeRecordedPayload",
        {
            "mistake_id": ID,
            "source": enum("来源", "auto", "manual"),
            "chapter_id": nullable(ID),
        },
    ),
    "mistake_resolved": ("MistakeResolvedPayload", {"mistake_id": ID}),
    "study_plan_saved": (
        "PlanSavedPayload",
        {
            "plan_id": ID,
            "source": enum("来源", "manual", "tutoring", "imported"),
            "items_count": number("项目数", 1, 20),
        },
    ),
    "plan_item_completed": ("PlanItemCompletedPayload", {"plan_id": ID, "item_id": ID}),
    "reminder_triggered": (
        "ReminderTriggeredPayload",
        {
            "reminder_id": ID,
            "type": enum("类型", "plan_due", "assignment_due", "mistake_review_due"),
        },
    ),
    "chapter_viewed": ("ChapterViewedPayload", {"chapter_id": ID}),
}
for event_type, (payload_name, payload_fields) in PAYLOADS.items():
    model(payload_name, event_type + "事件特有数据", payload_fields, owner="M5")
model(
    "LearningEventV2",
    "领域事件2.0；不是开放给浏览器的任意事件写入口",
    {
        "event_id": ID,
        "event_type": enum("事件类型", *PAYLOADS),
        "user_id": ID,
        "course_id": nullable(ID),
        "class_id": nullable(ID),
        "occurred_at": TIME,
        "trace_id": text("生产请求号", 36, pattern=r"^req_[0-9a-f]{32}$"),
        "schema_version": {"type": "string", "const": "2.0"},
        "payload": {"oneOf": [ref(name) for name, _ in PAYLOADS.values()]},
    },
    owner="M5/M6",
    db="learning_events；现有#79 CHECK只允许1.0，2.0必须新迁移/明确适配后启用，不直接整包灌入旧库",
    allOf=[
        {
            "if": {"properties": {"event_type": {"const": kind}}},
            "then": {"properties": {"payload": ref(name)}},
        }
        for kind, (name, _) in PAYLOADS.items()
    ],
    rules=(
        "user/time/trace由生产方取得；class为发生时快照；source不可变；未处理/隔离事件不得先清理。",
    ),
)

INTERNAL_PORTS = [
    {
        "id": "INT01",
        "name": "verified_actor",
        "provider": "M1",
        "consumer": "全部服务端域",
        "input": "Bearer凭证，仅服务端验签入口读取",
        "output": "已验证user_id/当前role/授权上下文",
        "rules": (
            "验签、过期、撤销、账号停用均校验；浏览器自报角色无效；配置DB故障503不退回演示身份。"
        ),
    },
    {
        "id": "INT02",
        "name": "course_access_and_enrollment",
        "provider": "M5",
        "consumer": "M1/M3/M6",
        "input": "统一Session、verified_actor、course_id/class_id、目标学生（仅管理写）",
        "output": "访问结论或Enrollment/TeachingAssignment",
        "rules": (
            "M5唯一关系实体和公开读写service；M1负责HTTP身份和角色门禁。"
            "repository不commit，返回前验证父子和有效区间。"
        ),
    },
    {
        "id": "INT03",
        "name": "get_owned_plan_suggestion",
        "provider": "M3",
        "consumer": "M5",
        "input": "verified_actor、source_turn_id",
        "output": "PlanSuggestion或统一NotFound",
        "rules": (
            "一次完成owner/已完成/有建议校验，M5直接调用，不接收浏览器转存items；章节由M5匹配。"
        ),
    },
    {
        "id": "INT04",
        "name": "learning_event_feed",
        "provider": "M5",
        "consumer": "M6",
        "input": "共享Session中的只读feed视图；M6持有consumer_id/ledger",
        "output": "LearningEventV2批次",
        "rules": (
            "READ COMMITTED每轮新事务锁consumer，反连接未处理账本及open隔离；"
            "聚合/ledger同事务，不以最大id或时间永久排除旧提交。"
        ),
    },
    {
        "id": "SDK01",
        "name": "AvatarController.speak",
        "provider": "M4",
        "consumer": "M2",
        "input": "既有组件camelCase参数utteranceId/text/emotion/action",
        "output": "completed/stopped/error回调",
        "rules": (
            "组件不是HTTP API，不强行改成snake_case；M2从v2完整终帧适配，"
            "只播报is_complete=true的结果，非法情绪动作降级。"
        ),
    },
    {
        "id": "SDK02",
        "name": "AvatarController.stop",
        "provider": "M4",
        "consumer": "M2",
        "input": "当前utteranceId",
        "output": "停止当前播报，不删除文字",
        "rules": (
            "与后端答疑stop不同：此处仅停本地播报，不推断答疑成功或学习时长；"
            "组件卸载也清理播放资源。"
        ),
    },
]
