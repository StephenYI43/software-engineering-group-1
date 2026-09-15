# TutoringResponse 契约

一次答疑回答的完整数据结构。由 M3 提供，M2 展示、M4 播报、M5 读取导学建议。

所有 JSON 字段为 **camelCase**（`docs/code-standards.md:48`）。服务端内部使用 snake_case，
通过 schema 别名转换（`docs/code-standards.md:55`）。

## 请求

`POST /api/v1/tutoring/sessions/{sessionId}/messages`

> 路径形状待 M2 确认，见 README.md「仍待团队拍板」第 2 条。

```json
{
  "content": "函数在一点的极限定义是什么？",
  "requestedStage": "thought",
  "courseId": "course_b3f1c2d4"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content` | string | 是 | 学生本轮提问，长度 1—2000 字符 |
| `requestedStage` | string \| null | 否 | 学生主动请求的阶段，只能是 stage 枚举值。**服务端有权钳制，不是命令** |
| `courseId` | string \| null | 否 | 限定本轮检索范围。**只能收窄服务端已授权的集合，不能放宽** |

### 关键约束：请求体禁止出现 `stage`

客户端**不得**自行指定教学阶段。服务端 schema 使用 `extra="forbid"`，
请求体中出现 `stage`、`emotion`、`action` 等字段一律返回 **422**。

原因：`docs/code-standards.md:95` 要求「客户端不能自行推进教学状态绕过后端校验」。
如果允许客户端传 `stage`，学生就能直接跳到 `summary` 拿到完整答案。

## 响应

```json
{
  "turnId": "turn_7f3a9c21",
  "sessionId": "sess_4b8d1e02",
  "stage": "thought",
  "content": "我们先不急着算结果。你想想，说「当 x 靠近 a 时 f(x) 趋近 L」，",
  "citations": [
    {
      "citationId": "c1",
      "documentId": "doc_9a2f4c",
      "documentTitle": "高等数学-上册-第1章.pdf",
      "pageNumber": 12,
      "snippet": "设函数 f(x) 在点 a 的某个去心邻域内有定义……"
    }
  ],
  "hasEvidence": true,
  "followUps": [
    "那 ε 和 δ 哪个先给定？",
    "如果只在一边趋近，结论还成立吗？"
  ],
  "emotion": "encouraging",
  "action": "nod",
  "isMock": true,
  "promptVersion": "guided-tutoring.v1",
  "createdAt": "2026-09-14T08:00:00Z"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `turnId` | string | 是 | 本轮唯一标识 |
| `sessionId` | string | 是 | 会话标识 |
| `stage` | string | 是 | 教学阶段，见下方枚举。**由服务端状态机计算，非模型输出** |
| `content` | string | 是 | 本轮回答文本 |
| `citations` | array | 是 | 引用列表，无依据时为空数组 `[]`，**不得为 null** |
| `hasEvidence` | boolean | 是 | 是否检索到依据 |
| `followUps` | array[string] | 是 | 建议追问，最多 3 条，每条最多 200 字符 |
| `emotion` | string | 是 | 数字人情绪，供 M4 消费 |
| `action` | string | 是 | 数字人动作，供 M4 消费 |
| `isMock` | boolean | 是 | 是否由离线假模型生成 |
| `promptVersion` | string | 是 | 产生本轮回答的提示词版本 |
| `createdAt` | string | 是 | UTC ISO 8601（`docs/code-standards.md:55`） |

## stage 枚举

取值：`thought` | `hint` | `step` | `summary`（`docs/code-standards.md:95`）

| 值 | 含义 | 何时出现 |
| --- | --- | --- |
| `thought` | 面向学生的解题思路 | 首轮回答，或新题目的第一轮 |
| `hint` | 在思路上更进一步的关键提示 | 学生已尝试但仍未解决 |
| `step` | 具体步骤拆解 | 学生尝试后仍需分步引导 |
| `summary` | 总结与教学解释 | 学生完成、答错、或明确标记错题之后 |

**`thought` 是面向学生的解题思路，不是模型的内部推理过程。**
`docs/requirements.md:24` 明确「不要求模型暴露内部推理过程」。
实现上模型适配器**不得转发** `thinking_delta` 一类的内部推理增量。
若后续有人想在界面上「展示思考过程」，那是新需求，需重新评审本契约。

枚举中**不存在** `answer`、`solution`、`cot`、`reasoning` 等值。
`stage` 的推进规则由服务端状态机决定，本契约只定义取值，不定义推进算法。

## citation 结构

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `citationId` | string | 本轮内的引用标签，从 `c1` 开始递增 |
| `documentId` | string | 文档标识 |
| `documentTitle` | string | 展示用文件名 |
| `pageNumber` | integer | 页码，**从 1 开始**，必须 ≥ 1 |
| `snippet` | string | 支持该结论的原文片段 |

`pageNumber` 不允许为 0 或负数 —— 解析层的页码必须是 1 基的。

`documentTitle` 是**不可信输入**（文件名由上传者决定），展示前需净化，
且不得直接拼进模型提示词（见 `docs/requirements.md:26` 的注入要求）。

## 不变量

以下条件由服务端强制，违反即为缺陷（应被 Pydantic validator 或测试拦截）：

1. **`hasEvidence = false` ⟺ `citations` 为空数组。**
   找不到依据时明确说明，**绝不编造引用**（`docs/requirements.md:26`）。
2. **每条 citation 的 `documentId` 必须属于本轮授权检索结果。**
   模型给出的、不在本轮白名单内的引用标签一律丢弃。
   这使得「伪造引用」和「引用别班资料」在结构上不可能发生。
3. **`citations` 不为 null**，无依据时用空数组。
4. **`pageNumber` ≥ 1**。
5. **`followUps` 至多 3 条，每条至多 200 字符。**
6. **`isMock` 必须如实反映数据来源。**
   `AGENTS.md:8` 要求 Mock 必须明确标记、不能当生产完成证据。
   M2 在 `isMock=true` 时应显示明确标识，不得呈现为真实模型结果。
7. **`stage` 不得由模型输出决定**，只能由服务端状态机计算。

## emotion / action 取值（占位，待 M4 冻结）

> 这两组值**尚未确定**。`docs/tasks/m3.md:23` 与 `docs/tasks/m4.md:23` 对定义权互相矛盾。
> 下表仅为占位，用于让样例可读。**M4 给出正式枚举前，本契约不是最终版。**

| 字段 | 占位取值 |
| --- | --- |
| `emotion` | `neutral` / `encouraging` / `thinking` / `celebrating` |
| `action` | `idle` / `nod` / `point` / `write` |

建议的分工（待确认）：**M4 定义枚举取值**（他们知道形象能渲染什么），
**M3 定义教学情境到取值的映射**并校验模型输出是否落在 M4 的枚举内。

## ID 约定（待 M1 的共享基础契约确认）

本契约中所有**实体 ID** 采用 `<实体前缀>_<不透明后缀>` 形式：

| ID | 示例 | 归谁定义 |
| --- | --- | --- |
| `turnId` | `turn_7f3a9c21` | M3 |
| `sessionId` | `sess_4b8d1e02` | M3 |
| `documentId` | `doc_9a2f4c` | M3 |
| `courseId` | `course_b3f1c2d4` | M5 |
| `requestId` | `req_8d1f0c33` | M1 |

`citationId`（`c1`、`c2`）是**例外**：它不是实体 ID，而是**单次回答内的引用标签**，
从 `c1` 起递增，不跨请求稳定，也不应被持久化或当作实体主键使用。

> **本节待确认，不要据此实现。**
> ID 的具体形态（是否带前缀、后缀用 UUID 还是短随机串）属于横切约定，
> 应由 M1 在共享基础契约中统一规定 —— `docs/code-standards.md:88` 把
> 「用户身份、角色、课程/班级访问规则、requestId」划给 M1，但**未覆盖 ID 形态本身**。
>
> 为什么单独写这一节：ID 格式是全系统最容易各自为政的地方。
> M3、M5、M6 都要引用 `courseId`，只要有一方写成裸 UUID、另一方写成带前缀，
> 前端就得写两套解析逻辑。本契约先给出一种自洽的写法供讨论，
> **不替代 M1 的统一规定**。

## 错误响应

与 `docs/code-standards.md:74-80` 一致：

```json
{
  "code": "TUTORING_SESSION_NOT_FOUND",
  "message": "未找到答疑会话",
  "requestId": "example-request-id",
  "details": {}
}
```

本领域已定义的错误码：

| code | HTTP | 场景 |
| --- | --- | --- |
| `TUTORING_SESSION_NOT_FOUND` | 404 | 会话不存在，**或不属于当前用户** |
| `TUTORING_TURN_IN_PROGRESS` | 409 | 同一会话已有进行中的回答 |
| `TUTORING_NO_EVIDENCE` | — | 不是错误响应用，见下方说明 |
| `MODEL_OUTPUT_INVALID` | — | 模型输出无法通过校验，以 `error` 事件下发 |
| `RATE_LIMITED` | 429 | 超出并发流上限 |
| `VALIDATION_ERROR` | 422 | 请求体含禁止字段（如 `stage`） |

**越权访问返回 404 而非 403**，与 `docs/code-standards.md:82` 的防枚举策略一致：
不让攻击者通过状态码区分「会话不存在」和「会话存在但不属于你」。

`TUTORING_NO_EVIDENCE` **不是错误**。找不到依据是正常的业务结果，
通过 `hasEvidence=false` + 空 `citations` 表达，HTTP 仍是 200。
