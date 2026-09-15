# 课程与章节契约（M5 → M2 / M3 / M6）

学生选课、查看章节；教师创建课程与章节；M3 用 `courseId` / `chapterId` 限定答疑检索范围
（见 [tutoring-response.md](../tutoring/tutoring-response.md) 的请求字段 `courseId`）；
M6 通过本接口在教师后台管理课程。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。

## 资源：Course

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `course_b3f1c2d4`，ID 形态待 M1 冻结（见 [README.md](README.md) 待拍板第 1 条） |
| `title` | string | 是 | 课程名，1—100 字符 |
| `description` | string \| null | 否 | 课程简介，≤ 2000 字符 |
| `subject` | string | 是 | 学科标识，枚举见下方 |
| `coverImageUrl` | string \| null | 否 | 封面图 URL，由调用方净化后再渲染 |
| `teacherId` | string | 是 | 主讲教师用户 ID，引用 M1 用户身份 |
| `teacherName` | string \| null | 否 | 展示用教师姓名。M5 不在 `courses` 表存储姓名，按需通过 M1 用户接口解析后回填 |
| `studentCount` | integer \| null | 否 | 选课人数，列表接口可回填；详情接口可不返回 |
| `chapterCount` | integer \| null | 否 | 章节数，同上 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

### subject 枚举

S1 范围（`docs/requirements.md:18` F09 首版只覆盖单门高数示范课）：

| 值 | 含义 |
| --- | --- |
| `math` | 数学（含高数） |
| `physics` | 物理 |
| `chemistry` | 化学 |
| `english` | 英语 |
| `cs` | 计算机 |
| `other` | 其他学科 |

> 学科扩容由 M3 负责「每新增一科补课程结构、评测与资料」（F09 后续扩展）。
> 本枚举的**取值集合由 M3 / M5 共同维护**，新增需同步本契约与 M3 评测集。

## 资源：Chapter

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `chapter_2c9e1a` |
| `courseId` | string | 是 | 所属课程 |
| `title` | string | 是 | 章节名，1—100 字符 |
| `order` | integer | 是 | 课程内排序，**从 1 开始**，必须 ≥ 1 |
| `description` | string \| null | 否 | 章节简介 |
| `documentId` | string \| null | 否 | 关联课件 ID（由 M3 知识库解析后回填；本字段只是引用，不存放文档内容） |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

`order` 是整数排序键，**不允许为 0 或负数**。前端按 `order` 升序展示。

## 端点

### `GET /api/v1/courses`

列出**当前用户有权访问的**课程。学生看到自己选的课；教师看到自己主讲的课。

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | integer | 1 | ≥ 1 |
| `pageSize` | integer | 20 | 1—100 |
| `subject` | string \| null | null | 按学科过滤 |
| `q` | string \| null | null | 标题模糊搜索，≤ 100 字符 |

响应 200：

```json
{
  "items": [
    {
      "id": "course_b3f1c2d4",
      "title": "高等数学（上）",
      "description": "极限、连续、一元微积分",
      "subject": "math",
      "coverImageUrl": null,
      "teacherId": "user_9a2f4c",
      "teacherName": "王老师",
      "studentCount": 32,
      "chapterCount": 12,
      "createdAt": "2026-09-10T08:00:00Z",
      "updatedAt": "2026-09-14T10:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "pageSize": 20
}
```

分页结构遵循 `docs/code-standards.md:71`。`items` 可能为空数组，**不得为 null**。

### `GET /api/v1/courses/{courseId}`

返回单门课程详情。**越权访问返回 404**（防枚举，code-standards.md:82）。

### `GET /api/v1/courses/{courseId}/chapters`

返回该课程的章节列表，按 `order` 升序。无需分页（章节总数有限，预期 ≤ 100）。

响应 200：

```json
{
  "items": [
    {
      "id": "chapter_2c9e1a",
      "courseId": "course_b3f1c2d4",
      "title": "第一章 极限与连续",
      "order": 1,
      "description": "数列极限、函数极限、连续性",
      "documentId": "doc_9a2f4c",
      "createdAt": "2026-09-10T08:05:00Z",
      "updatedAt": "2026-09-10T08:05:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "pageSize": 100
}
```

> 章节列表虽然不分页，仍返回 `page` / `pageSize` 以保持响应结构一致（code-standards.md:71）。

### `POST /api/v1/courses`

教师/管理员创建课程。**学生角色调用返回 403**（鉴权由 M1 实现，M5 只声明要求）。

请求：

```json
{
  "title": "高等数学（上）",
  "description": "极限、连续、一元微积分",
  "subject": "math",
  "coverImageUrl": null
}
```

响应 201：返回完整 Course 对象，`teacherId` 取自当前会话用户。

### `POST /api/v1/courses/{courseId}/chapters`

教师为课程添加章节。`order` 由服务端**自动续编**（取当前最大 order + 1），
请求体**不得**包含 `order`，包含则返回 422。

请求：

```json
{
  "title": "第二章 导数与微分",
  "description": "导数定义、求导法则、微分"
}
```

## 不变量

1. **学生只能看到已选或被授权的课程。** `courses` 表不存取 ACL，授权关系由 M1 维护
   （code-standards.md:88 把课程/班级访问规则划给 M1）；M5 在 service 层调用 M1 的鉴权接口判定。
2. **章节的 `courseId` 必须存在且当前用户有权访问该课程。** 越权返回 404。
3. **`order` ≥ 1，且同一课程内 `order` 唯一。** 删除章节不重排其余 `order`（避免并发改写）。
4. **`coverImageUrl` 是不可信输入。** 文件名由上传者决定，展示前需净化
   （code-standards.md:105；与 tutoring-response.md:113 一致）。
5. **`teacherName` 不持久化在 `courses` 表。** 它是 M1 用户接口解析后的回填，
   契约字段允许为 null。

## 错误响应

与 `docs/code-standards.md:74-80` 一致：

```json
{
  "code": "COURSE_NOT_FOUND",
  "message": "未找到课程",
  "requestId": "example-request-id",
  "details": {}
}
```

本领域已定义的错误码：

| code | HTTP | 场景 |
| --- | --- | --- |
| `COURSE_NOT_FOUND` | 404 | 课程不存在，**或当前用户无权访问**（防枚举） |
| `CHAPTER_NOT_FOUND` | 404 | 章节不存在或不属于该课程 |
| `VALIDATION_ERROR` | 422 | 请求体含禁止字段（如章节创建请求中的 `order`） |
| `FORBIDDEN_ROLE` | 403 | 学生调用教师专属端点（如 `POST /courses`） |
| `RATE_LIMITED` | 429 | 列表接口超限 |

**越权一律返回 404 而非 403**（除「角色不符」这种不暴露资源存在性的场景返回 403），
与 `docs/code-standards.md:82` 与 tutoring-response.md:194 一致。
