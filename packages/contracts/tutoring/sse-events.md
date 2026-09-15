# 流式答疑 SSE 事件契约（M3 → M2）

`docs/code-standards.md:95` 要求流式答疑使用 SSE，并定义 `started` / `delta` / `completed` / `error`、
序号和停止行为。本文把这些规则具体化。

传输：`text/event-stream`，事件格式为标准 SSE `event:` + `data:` 行。
每个 `data:` 是**单行 JSON**，字段为 camelCase。

**传输方式已确认（M2，2026-09-15）：`fetch` + `ReadableStream`，不使用 `EventSource`。**

本接口需 POST 携带 JSON 请求体，且需携带 `Authorization` 头；
`EventSource` 只支持 GET、无法携带自定义请求头，**两个必要条件都不满足**，无选择余地。

由此产生的前端实现责任（由 M2 承担，记录在案）：

- 自行实现 SSE 帧解析：按空行切帧、解析 `event:` / `data:` 行、处理跨 chunk 的半截帧；
- 自行校验 `seq` 单调递增，跳号或重复视为协议错误；
- **不使用 `AbortController` 实现「停止」按钮** —— 原因见「停止行为」中
  `client_stop` 与 `client_disconnect` 的区分。

## 事件序列

```text
started  →  delta × N  →  completed        （正常完成）
                        →  stopped          （用户主动中断）
                        →  error            （失败）
```

规则：

1. **`started` 必定是第一个事件，`seq = 1`。**
2. **恰好一个终止事件**，且其 `seq` 为整个流的最大值。
3. **`seq` 从 1 开始严格递增，不跳号、不重复。**
4. 终止事件之后**不再有任何事件**。
5. 每个事件都带 `turnId`，便于多路复用与日志关联。

## started

```json
{
  "seq": 1,
  "turnId": "turn_7f3a9c21",
  "stage": "thought",
  "isMock": true
}
```

| 字段 | 说明 |
| --- | --- |
| `seq` | 恒为 1 |
| `turnId` | 本轮标识 |
| `stage` | 本轮**服务端已确定**的教学阶段 |
| `isMock` | 是否假模型。M2 据此显示标识 |

`stage` 在 `started` 就下发，让前端可以立刻渲染阶段指示器，不必等回答结束。

## delta

```json
{
  "seq": 2,
  "turnId": "turn_7f3a9c21",
  "textDelta": "我们先不急着算结果。"
}
```

`textDelta` 是**增量文本片段**，M2 按顺序拼接即为完整 `content`。

`delta` 只承载正文文本。`citations`、`followUps`、`emotion`、`action` 等结构化字段
**只在终止事件中给定**，避免前端在流中途处理半成品结构。

## completed

```json
{
  "seq": 9,
  "turnId": "turn_7f3a9c21",
  "isComplete": true,
  "response": { }
}
```

`response` 是完整的 [TutoringResponse](tutoring-response.md) 对象，字段与上文契约一致。
**终止事件携带完整结构**，前端可直接用它替换流式过程中拼出的临时文本，
以保证最终展示与校验通过的结构完全一致。

## stopped（用户中断）

```json
{
  "seq": 5,
  "turnId": "turn_7f3a9c21",
  "isComplete": false,
  "reason": "client_stop"
}
```

`reason` 取值：`client_stop`（前端调用停止）| `client_disconnect`（连接断开）。

**`stopped` 与 `completed` 必须区分，这是硬要求。**
`docs/code-standards.md:95`：「未经服务端确认完成的半截回答不当作完成记录」。
`docs/requirements.md:32` 也要求「不能伪造成功结果」。

服务端在 `stopped` 时的行为：

- 该轮持久化为 `aborted`，`isComplete = false`
- **教学阶段不推进** —— 半截回答不能让学生跳过 `thought`
- 已生成的部分文本可以保留供展示，但**不能被计入「已完成回答」**
- M2 展示时不得呈现为完整回答

## error

```json
{
  "seq": 3,
  "turnId": "turn_7f3a9c21",
  "isComplete": false,
  "error": {
    "code": "MODEL_OUTPUT_INVALID",
    "message": "模型输出无法通过结构校验",
    "requestId": "example-request-id",
    "details": {}
  }
}
```

`error` 沿用 `docs/code-standards.md:74-80` 的错误结构。

本契约定义的流内错误码：

| code | 场景 |
| --- | --- |
| `MODEL_OUTPUT_INVALID` | 模型输出无法解析或未通过结构校验（含重试后仍失败） |
| `MODEL_REFUSED` | 模型拒绝作答 |
| `MODEL_TIMEOUT` | 模型调用超时 |
| `RETRIEVAL_UNAVAILABLE` | 检索服务不可用 |
| `TURN_ABORTED` | 服务端内部中断 |

`error` 与 `stopped` 的区别：`stopped` 是**用户意图**，`error` 是**系统失败**。
两者都 `isComplete = false`，但前端提示文案与重试策略不同。

### `error` 时教学阶段同样不推进

与 `stopped` 一致。理由相同：失败的轮次没有产生可用的教学结果，
半截文本不能让学生跳过当前阶段（对照上文 `stopped` 的处理）。

因此**前端在重试产生新轮后不需要重置阶段指示器**——它从未推进。
新轮的 `stage` 由服务端状态机在**同一个未推进的状态**上重算。

一点边界：`stage` 的**推进算法**不在本契约范围内（`tutoring-response.md:98`
「推进规则由服务端状态机决定，本契约只定义取值」）。
此处确定的是**不变量**：失败轮（`stopped` / `error`）一律不推进。

## 停止行为

`POST /api/v1/tutoring/sessions/{sessionId}/turns/{turnId}/stop`

- 幂等：对同一轮重复调用返回相同结果，不会产生第二个终止事件
- 停止后服务端关闭上游模型流（不继续计费）
- 已发出的事件保留有效，前端据 `stopped` 收尾
- **服务端在发起上游取消后立即下发 `stopped`，不等供应商确认关闭。**
  这是前端兜底超时不会被误触发的前提。

### 前端侧约定（M2，2026-09-15）

- 用户点停止 → 调本接口 → **保持 SSE 连接打开**，继续读取直到收到 `stopped` 终止事件，
  收到后收尾并关闭连接；
- **兜底超时为 5 秒**（双方共同约定）。超时仍未收到终止事件才 `abort()`，
  并按「结果未知」提示，**不得**把已收到的半截文本展示为完成结果。

### 为什么停止不能靠 `AbortController` 实现

`reason` 的取值 `client_stop` 与 `client_disconnect` 区分的是**用户意图**与**连接断开**。
前端若用 `AbortController.abort()` 实现停止按钮，服务端观察到的是连接断开，
会被记为 `client_disconnect`，而不是用户意图的 `client_stop`，语义丢失。

因此停止必须走本接口；`abort()` 只作为兜底超时后的最后手段。

## 断连行为

客户端断开连接（关闭页面、网络中断）时：

- 服务端将该轮记为 `aborted`，`isComplete = false`
- 阶段不推进
- **不重试**、不自动续传

S1 **只支持整轮重试，不支持断点续传**。前端拿到半截内容后如需继续，应重新发起一轮提问。
`seq` 的设计为将来可能的续传留出了扩展空间（可用 `Last-Event-ID`），但 S1 不实现。

> **已由 M2 确认（2026-09-15）。** 前端在 `stopped` / `error` 后的交互是
> 「重新发起一轮提问」，不做续传 UI。

## 隐私

SSE 事件中**不得**包含：

- 模型内部推理过程（`thinking` 类增量一律不透传）
- 系统提示词内容
- 未授权文档的片段
- 其他学生的数据

服务端日志按 `docs/code-standards.md:105` 记录 `requestId` / 模型 / 提示词版本 / token 用量，
但**不记录完整对话文本**。
