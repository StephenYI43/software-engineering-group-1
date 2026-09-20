# 错题本契约（M5 → M2 / M6）

学生错题本的查询、主动收录与移除。**本契约的核心硬约束：禁止把所有问题默认当错题收录**
（`docs/tasks/m5.md:13`、`docs/team-plan.md:61`）。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。ID 形态为 `<前缀>_<32 位小写 hex>`
（见 [README.md](README.md)「ID 形态」）。

## 收录触发路径（**只有这两条**）

按 `docs/tasks/m5.md:13`「基于错误提交/主动确认幂等收录错题」与
`docs/team-plan.md:61`「只有用户提交错误答案或明确标记错题时才收录」：

| 路径 | 触发方 | 入口 | 收录条件 |
| --- | --- | --- | --- |
| **错答自动收录** | 服务端 | 作业提交被判为 `isCorrect = false` 的瞬间 | 见下方不变量 1 |
| **学生主动标记** | 学生 | `POST /api/v1/mistakes`（带 `source: "manual"`） | 学生在答疑或作业详情页点击「加入错题本」 |

**禁止路径**（视为缺陷，应被服务端校验或测试拦截）：

- ❌ 作业**未提交**就自动收录题干
- ❌ 学生**未答错**就由系统默认收录（如「这题看起来难，先收着」）
- ❌ M3 答疑结束后**默认**把问题写入错题本（学生没主动标记时）
- ❌ 教师**批量**把全班学生作业加入错题本（学生未错答也未标记）

> 这条约束是产品规则（`docs/requirements.md` F04「错题本」与 F03「多轮辅导」分离），
> 不是性能优化。违反它会让错题本失去「学生专属待复习集合」的语义。

## 资源：Mistake

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 形如 `mistake_9c4b2e5f6a7b8c9d0e1f2a3b4c5d6e7f` |
| `studentId` | string | 是 | 错题所属学生 |
| `courseId` | string | 是 | 关联课程 |
| `chapterId` | string \| null | 否 | 关联章节 |
| `assignmentId` | string \| null | 否 | 关联作业；主动标记且非作业场景为 null |
| `submissionId` | string \| null | 否 | 触发收录的提交；手动标记时为 null |
| `sourceTurnId` | string \| null | 否 | 关联 M3 答疑 turnId；从答疑后主动标记时填，其他为 null |
| `source` | string | 是 | 见下方枚举 |
| `question` | object | 是 | 题目快照，见下方 |
| `studentAnswer` | object \| string \| null | 否 | 学生答错时的答案快照；手动从答疑标记时可缺失 |
| `note` | string \| null | 否 | 学生备注，≤ 500 字符 |
| `status` | string | 是 | 见下方枚举 |
| `createdAt` | string | 是 | UTC ISO 8601 |
| `updatedAt` | string | 是 | UTC ISO 8601 |

### source 枚举

| 值 | 含义 | 入口 |
| --- | --- | --- |
| `wrong_submission` | 错答自动收录 | 服务端在 `submission.isCorrect` 翻转为 false 时写入 |
| `manual` | 学生主动标记 | `POST /api/v1/mistakes` 带 `source: "manual"` |

**只有这两个值**。`docs/tasks/m5.md:13` 写「基于错误提交/主动确认」，本契约据此封死其他来源。

### status 枚举

| 值 | 含义 |
| --- | --- |
| `active` | 待复习 |
| `resolved` | 学生标记为已掌握，移出待复习 |
| `archived` | 归档（学期结束等） |

> `resolved` 不删除记录，只是从默认列表（`status=active`）中隐藏。
> 这是 M6 统计「错题已掌握率」的依据，删除会让统计失真。

### question 结构（题目快照，按来源差异化）

```json
{
  "stem": "求极限 lim(x→0) sin(x)/x",
  "questionType": "short_answer",
  "options": null,
  "attachmentUrl": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `stem` | string | 题干文本，≤ 4000 字符 |
| `questionType` | string | 见下方取值 |
| `options` | array \| null | 选择题选项；其他题型为 null |
| `attachmentUrl` | string \| null | 题目附图等附件 URL，需净化后渲染 |

**`questionType` 取值**（M2 在 PR #26 第 A 条要求区分答疑来源）：

| 来源 | questionType | 说明 |
| --- | --- | --- |
| 作业场景（`source=wrong_submission` 或从作业详情 `source=manual`） | 复用 [homework.md](homework.md) 作业题型：`single_choice` / `multiple_choice` / `fill_blank` / `short_answer` / `proof` | 题型来自作业 |
| 答疑场景（从 M3 答疑后 `source=manual`） | `tutoring_question` | 题目是自由文本，不属于作业题型；`options` 为 null |

> 上一版 `questionType` 全部复用作业题型，被 M2 指出答疑页的自由文本没有对应题型。
> 本版新增 `tutoring_question` 专用于答疑后主动标记场景；作业场景仍用作业题型。

**`question` 是收录时刻的快照**。后续教师修订作业题面不影响已收录的错题记录。
这是为了让学生复习时看到的是「我当时答错的题」，而非教师最新版本。

## 端点

### `POST /api/v1/mistakes`

学生主动标记错题。**服务端校验 source 必须为 `manual`**，禁止客户端伪造 `wrong_submission`
（那只能由服务端在判分时触发）。

请求（作业场景）：

```json
{
  "courseId": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "chapterId": "chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b",
  "assignmentId": "assignment_4d8e2b3c4d5e6f7a8b9c0d1e2f3a4b5c",
  "submissionId": "submission_7a3c1d4e5f6a7b8c9d0e1f2a3b4c5d6e",
  "sourceTurnId": null,
  "source": "manual",
  "question": {
    "stem": "求极限 lim(x→0) sin(x)/x",
    "questionType": "short_answer",
    "options": null,
    "attachmentUrl": null
  },
  "studentAnswer": { "text": "1" },
  "note": "极限的等价无穷小没记住"
}
```

请求（答疑场景，`questionType = tutoring_question`）：

```json
{
  "courseId": "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "chapterId": null,
  "assignmentId": null,
  "submissionId": null,
  "sourceTurnId": "turn_7f3a9c214d5e6f7a8b9c0d1e2f3a4b5c",
  "source": "manual",
  "question": {
    "stem": "函数在一点的极限定义是什么？",
    "questionType": "tutoring_question",
    "options": null,
    "attachmentUrl": null
  },
  "studentAnswer": null,
  "note": "答疑时没记住 ε-δ 定义"
}
```

响应 201：返回完整 Mistake 对象。

### 幂等：重复收录不重复创建

服务端按 `(studentId, assignmentId, question.stem)` 去重：
- 同一作业、同一题干（stem 规范化后比较）已有 `active` 状态错题时，
  重复 `POST /api/v1/mistakes` 返回**已有记录**，HTTP 200（而非 201）
- 自动收录路径同理：教师重新批阅导致 `isCorrect` 再次翻转为 false 时不重复收录

> 答疑场景（`assignmentId = null`）的去重键退化为 `(studentId, sourceTurnId, normalizedStem)`，
> 同一答疑 turn 对同一 stem 只保留一条 active 记录。

`docs/tasks/m5.md:29` 的验收标准「重复请求不重复收录」即指此规则。

### `GET /api/v1/mistakes`

学生列出自己的错题。

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | integer | 1 | ≥ 1 |
| `pageSize` | integer | 20 | 1—100 |
| `courseId` | string \| null | null | 按课程过滤 |
| `chapterId` | string \| null | null | 按章节过滤 |
| `source` | string \| null | null | 按来源过滤（`wrong_submission` / `manual`） |
| `status` | string | `active` | `active` / `resolved` / `archived` / `all` |

响应 200：分页列表。

### `GET /api/v1/mistakes/{mistakeId}`

错题详情。越权返回 404。

### `PATCH /api/v1/mistakes/{mistakeId}`

学生修改自己的错题（仅 `note` 与 `status` 可改）。

```json
{
  "note": "已复习 3 次，下次再做对就 resolved",
  "status": "resolved"
}
```

### `DELETE /api/v1/mistakes/{mistakeId}`

> **本端点不实现**。错题本只允许 `status` 转移到 `resolved` 或 `archived`，不允许物理删除。
> 这保证 M6 的「错题已掌握率」统计有完整时间序列。如需删除学生资料，
> 走 M1 的数据删除流程（`docs/requirements.md` 数据采集/录音须有删除途径）。

## 不变量

1. **`source` 字段服务端校验。** 客户端只能传 `manual`；`wrong_submission` 由服务端
   在判分翻转时内部写入。客户端传 `wrong_submission` 返回 422。
2. **`wrong_submission` 路径只在 `isCorrect: null → false` 的翻转瞬间触发一次。**
   后续重新批阅（`false → true`）不删除已收录错题，但 `mistake.submissionId` 指向的
   submission 状态可被前端用于显示「后来重做对了」。
3. **去重键：作业场景 `(studentId, assignmentId, normalizedStem)`；答疑场景
   `(studentId, sourceTurnId, normalizedStem)`。** `normalizedStem` 是题干去除首尾空白
   与多余空白后的形式。同一去重键只保留一条 `active` 记录。
4. **`question` 是快照，不随后续修订更新。** 见上文。
5. **学生只能读写自己的错题。** 任何端点对他人错题的访问返回 404。
6. **教师不能直接读写学生错题。** 教师后台看到的是 M6 聚合统计（按学生匿名汇总），
   不暴露单条错题。这一条与 code-standards.md:33「跨领域走公开服务函数或事件」一致。
7. **`mistakes` 表不存储题目原文附件二进制。** `attachmentUrl` 是引用，附件由 M3 知识库或
   M1 文件服务托管。

## 学习事件

错题收录、状态转移均发布学习事件，见 [learning-events.md](learning-events.md)。

| 事件 | 触发时机 | 关键 payload |
| --- | --- | --- |
| `mistake_recorded` | 自动或手动收录成功（含幂等命中已有记录） | `mistakeId`, `source`, `assignmentId?`, `chapterId?` |
| `mistake_resolved` | `status` 翻转到 `resolved` | `mistakeId` |

## 错误响应

| code | HTTP | 场景 |
| --- | --- | --- |
| `MISTAKE_NOT_FOUND` | 404 | 错题不存在或不属于当前用户 |
| `MISTAKE_DUPLICATE` | 200 | 重复收录命中已有记录（**非错误**，返回已有对象） |
| `VALIDATION_ERROR` | 422 | 客户端传了不允许的 `source` 值，或修改了只读字段 |
| `FORBIDDEN_ROLE` | 403 | 教师角色调用学生错题端点 |

`MISTAKE_DUPLICATE` 是**非错误响应**，HTTP 200 返回已有记录，
不写入新行也不发布 `mistake_recorded` 事件（避免统计重复计数）。
