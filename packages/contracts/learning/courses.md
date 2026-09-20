# 课程、班级与章节契约（M5 → M2 / M3 / M6）

学生选课、查看章节；教师创建课程、班级与章节；M3 用 `courseId` / `chapterId` 限定答疑检索范围
（见 [tutoring-response.md](../tutoring/tutoring-response.md) 的请求字段 `courseId`）；
M6 通过本接口在教师后台管理课程。

> **课程与班级分离**（M1 在 PR #26 评审第 1 条要求）：`course` 描述课程内容，`class` 描述教学班。
> 学生看到的是自己所在班级的作业与提交。S1 单班演示允许 `classId` 为空或默认单班。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。ID 形态为 `<前缀>_<32 位小写 hex>`
（见 [README.md](README.md)「ID 形态」），对调用方是不透明字符串，不得解析前缀做权限判断。

## 资源：Course

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6` |
| `title` | string | 是 | 课程名，1—100 字符 |
| `description` | string \| null | 否 | 课程简介，≤ 2000 字符 |
| `subject` | string | 是 | 学科标识，枚举见下方（含展示名） |
| `coverImageUrl` | string \| null | 否 | 封面图 URL，由调用方净化后再渲染 |
| `teacherId` | string | 是 | 主讲教师用户 ID，引用 M1 用户身份 |
| `teacherName` | string \| null | 否 | 展示用教师姓名。M5 不在 `courses` 表存储姓名，按需通过 M1 用户接口解析后回填 |
| `studentCount` | integer \| null | 否 | 选课人数，列表接口可回填；详情接口可不返回 |
| `chapterCount` | integer \| null | 否 | 章节数，同上 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

### subject 枚举（含展示名）

S1 范围（`docs/requirements.md:18` F09 首版只覆盖单门高数示范课）：

| 值 | 展示名 | 含义 |
| --- | --- | --- |
| `math` | 数学 | 数学（含高数） |
| `physics` | 物理 | 物理 |
| `chemistry` | 化学 | 化学 |
| `english` | 英语 | 英语 |
| `cs` | 计算机 | 计算机 |
| `other` | 其他 | 其他学科 |

> 学科扩容由 M3 负责「每新增一科补课程结构、评测与资料」（F09 后续扩展）。
> 本枚举的**取值集合由 M3 / M5 共同维护**，新增需同步本契约与 M3 评测集。
> **未知取值的回退策略**：M2 收到枚举外的 `subject` 值时，回退展示**原值字符串**，不报错也不隐藏该课程。

## 资源：Class（教学班）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `class_f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6` |
| `courseId` | string | 是 | 所属课程 |
| `title` | string | 是 | 班级名，1—100 字符（如「2026 级高数 A 班」） |
| `teacherId` | string | 是 | 授课教师用户 ID |
| `semester` | string \| null | 否 | 学期标识，如 `2026-fall` |
| `studentCount` | integer \| null | 否 | 班级人数，列表可回填 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

> `classes` 表由 M5 写入、访问关系由 M1 维护（code-standards.md:88 把课程/班级访问规则划给 M1）。
> **course 不是 class**：同一门课程可开多个教学班，作业与提交的访问边界落到 `classId`。

## 资源：Chapter

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b` |
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

列出**当前用户有权访问的**课程。学生看到自己所在班级对应的课；教师看到自己主讲的课。

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
      "id": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
      "title": "高等数学（上）",
      "description": "极限、连续、一元微积分",
      "subject": "math",
      "coverImageUrl": null,
      "teacherId": "user_9a2f4c3d5e6f7a8b9c0d1e2f3a4b5c6d",
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

### `GET /api/v1/courses/{courseId}/classes`

列出该课程下的教学班。学生只看到自己所在的班；教师看到自己主讲的班。

### `GET /api/v1/courses/{courseId}/chapters`

返回该课程的章节列表，按 `order` 升序。**支持分页**（章节数可能超过 100，不可静默截断）。

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | integer | 1 | ≥ 1 |
| `pageSize` | integer | 50 | 1—100 |

> 上一版曾固定 `pageSize=100` 且不接受分页参数，已被 M2 评审（PR #26 第 F 条）指出会让超 100 的章节
> 无法获取。本版改为真正分页。`pageSize` 上限 100，超出按 100 截断并在响应中保持 `total` 真实总数。

响应 200：

```json
{
  "items": [
    {
      "id": "chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b",
      "courseId": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
      "title": "第一章 极限与连续",
      "order": 1,
      "description": "数列极限、函数极限、连续性",
      "documentId": "doc_9a2f4c3d5e6f7a8b9c0d1e2f3a4b5c6d",
      "createdAt": "2026-09-10T08:05:00Z",
      "updatedAt": "2026-09-10T08:05:00Z"
    }
  ],
  "total": 12,
  "page": 1,
  "pageSize": 50
}
```

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

### `POST /api/v1/courses/{courseId}/classes`

教师为课程创建教学班。请求体：

```json
{
  "title": "2026 级高数 A 班",
  "semester": "2026-fall"
}
```

响应 201：返回 Class 对象，`teacherId` 取自当前会话。

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

## 选课与班级 ACL

> 选课 / 加入班级端点**不归 M5**。

`courses` / `assignments` 列表返回「学生看到自己选的课 / 所在班级的作业」，
但**选课（加入教学班）是访问关系写入**，属 M1 的鉴权与访问规则域
（`docs/code-standards.md:88` 把课程/班级访问规则划给 M1）。

- **M5 不实现选课端点**；M2 的「课程选择」入口调 M1 提供的接口。
- M1 冻结选课端点路径后，本契约在此处同步引用，避免 M2 对一个未定义的目标实现。
- 当前 M5 在 service 层调用 M1 的鉴权接口判定学生对 `classId` 的访问权（越权返回 404 防枚举）。

## 不变量

1. **学生只能看到已选或被授权的班级对应的课程。** `courses` / `classes` 表不存取 ACL，
   授权关系由 M1 维护（code-standards.md:88 把课程/班级访问规则划给 M1）；
   M5 在 service 层调用 M1 的鉴权接口判定。
2. **章节的 `courseId` 必须存在且当前用户有权访问该课程。** 越权返回 404。
3. **`order` ≥ 1，且同一课程内 `order` 唯一。** 删除章节不重排其余 `order`（避免并发改写）。
4. **`coverImageUrl` 是不可信输入。** 文件名由上传者决定，展示前需净化
   （code-standards.md:105；与 tutoring-response.md:113 一致）。
5. **`teacherName` 不持久化在 `courses` 表。** 它是 M1 用户接口解析后的回填，
   契约字段允许为 null。
6. **`classId` 在 `assignments` / `submissions` 上可空。** S1 单班演示可为空或默认单班；
   ACL 落到班级后，无 `classId` 的作业视为对所有有权学生可见。

## 错误响应

与 `docs/code-standards.md:74-80` 一致：

```json
{
  "code": "COURSE_NOT_FOUND",
  "message": "未找到课程",
  "requestId": "req_8d1f0c335e6f7a8b9c0d1e2f3a4b5c6d",
  "details": {}
}
```

本领域已定义的错误码：

| code | HTTP | 场景 |
| --- | --- | --- |
| `COURSE_NOT_FOUND` | 404 | 课程不存在，**或当前用户无权访问**（防枚举） |
| `CLASS_NOT_FOUND` | 404 | 班级不存在或无权访问 |
| `CHAPTER_NOT_FOUND` | 404 | 章节不存在或不属于该课程 |
| `VALIDATION_ERROR` | 422 | 请求体含禁止字段（如章节创建请求中的 `order`） |
| `FORBIDDEN_ROLE` | 403 | 学生调用教师专属端点（如 `POST /courses`） |
| `RATE_LIMITED` | 429 | 列表接口超限 |

**越权一律返回 404 而非 403**（除「角色不符」这种不暴露资源存在性的场景返回 403），
与 `docs/code-standards.md:82` 与 tutoring-response.md:194 一致。
