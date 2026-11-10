# v1 选课与教师展示名候选契约

状态为待评审。关联 [#47](https://github.com/StephenYI43/software-engineering-group-1/issues/47)、[#16](https://github.com/StephenYI43/software-engineering-group-1/issues/16) 与 [#42](https://github.com/StephenYI43/software-engineering-group-1/issues/42)。请 M2 确认页面消费行为，M5 确认关系服务、入班资格来源和事务约束。样例均为合成数据。本批交付契约与 schema。

## 学生加入教学班

`PUT /api/v1/classes/{classId}/enrollments/me` 表示让当前学生加入一个指定教学班。M1 负责 HTTP 入口和已验证身份，M5 负责课程与班级、唯一的选课关系、入班资格查询及事务内读写。入口使用 `Authorization: Bearer <sessionToken>`，从会话取得用户 ID 和角色。`classId` 采用 [课程契约](../learning/courses.md#资源class教学班) 的 ID 形态。请求无正文，课程 ID 由服务端根据教学班取得。

首次加入要求服务端已有针对该学生和该班的入班资格。资格来源由 M5 确认，通过受控服务查询。仅有班级 ID 或过去参加过该班均不足以入班。资格服务未配置时拒绝执行。已选课程列表仍只返回当前有权访问的课程，待选班级发现、教师代加与退班走各自的后续契约。

```http
PUT /api/v1/classes/class_22222222222222222222222222222222/enrollments/me
Authorization: Bearer <sessionToken>
```

首次加入和已有效加入时均返回 HTTP 200，响应符合 [ClassEnrollmentResponse](enrollment-response.schema.json)。`joinedAt` 使用 UTC ISO 8601，末尾为 Z。响应加 `Cache-Control: no-store`。

```json
{
  "enrollmentId": "enroll_11111111111111111111111111111111",
  "classId": "class_22222222222222222222222222222222",
  "courseId": "course_33333333333333333333333333333333",
  "joinedAt": "2026-11-10T08:00:00Z"
}
```

### 权限与幂等

1. 校验凭证、当前账号状态与学生角色，再进入班级关系服务。正文不能指定学生 ID、课程 ID、角色或入班时间。
2. 活动关系以当前学生、当前班级且未退班为准。已有活动关系时返回原记录与原 `joinedAt`，不重复写入。
3. 新增关系时，M5 在同一事务中校验资格并写入，通过活动关系唯一约束或等价并发控制保证两次请求只得到一条记录。竞争中的第二次请求在确认首条已提交后返回同一条关系。数据库失败时回滚。
4. 退班记录保留历史，重新入班需要新的有效资格，成功后建立新关系。教师访问权限仍来自 M5 的有效授课关系。入班资格查询与课后访问查询分别由对应服务负责。

### 错误响应

沿用 v1 的 `code/message/requestId/details`。班级不存在与学生没有入班资格返回相同的 404 错误码和消息，`details` 为空对象。

| HTTP | code | 场景 |
| --- | --- | --- |
| 401 | `TOKEN_REQUIRED` | 缺少 Bearer 凭证 |
| 401 | `INVALID_TOKEN` | 凭证无效、过期或撤销，或账号已停用 |
| 403 | `FORBIDDEN_ROLE` | 已登录，但当前角色不是学生 |
| 404 | `CLASS_NOT_FOUND` | 班级不存在或当前学生无有效关系和入班资格 |
| 422 | `VALIDATION_ERROR` | 班级 ID 格式错误或请求携带正文 |
| 503 | `SERVICE_UNAVAILABLE` | 入班资格查询尚未接入或暂不可用 |
| 503 | `DATABASE_UNAVAILABLE` | 数据库暂不可用 |

```json
{
  "code": "CLASS_NOT_FOUND",
  "message": "未找到教学班",
  "requestId": "req_0123456789ab4def8123456789abcdef",
  "details": {}
}
```

联调至少覆盖首次加入、同学生同班重复与并发请求、其他学生无资格、同课程下另一班无资格、退班后重试、教师角色拒绝、资格服务不可用及持久化失败。成功响应需在事务提交后返回。

## 服务端批量解析教师展示名

M5 在课程或班级数据完成授权裁剪后，提取当前页最多 100 个主讲教师 ID，调用 M1 的进程内查询服务。候选调用形态为 `resolve_teacher_names(user_ids, *, authorized_teacher_ids) -> dict[str, str]`。授权集合由服务端从调用方已获准查看的课程和班级生成。该服务没有公开 HTTP 路径，M2 在现有课程响应的 `teacherName` 字段取值。

服务端输入样例：

```json
{
  "userIds": [
    "user_44444444444444444444444444444444",
    "user_55555555555555555555555555555555"
  ],
  "authorizedTeacherIds": ["user_44444444444444444444444444444444"]
}
```

返回 ID 到展示名的映射，符合 [TeacherDisplayNames](teacher-display-names.schema.json)。请求与授权集合求交后去重，空输入返回空映射。不存在、停用、超出授权范围或无可用姓名的 ID 不出现在映射中。调用方为未命中条目填 `teacherName: null`。超过 100 项的批次由服务端调用方拆分，数据源不可用沿用 503。

```json
{
  "user_44444444444444444444444444444444": "王老师"
}
```

核对时应覆盖重复 ID、未授权 ID、不存在或停用的用户、空批次及超限。响应仅包含姓名，手机号、学号、邮箱和权限信息不属于此契约。
