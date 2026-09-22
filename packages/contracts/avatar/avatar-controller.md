# 数字人播报控制器契约（M4 → M2）

`docs/code-standards.md:91` 规定 M4 → M2 的边界为「speak(text)、stop()、状态与错误回调；语音/文字降级」。
本文把它具体化为可实现的组件契约：`speak` 升级为**结构化输入**，并定义播放事件、
终止语义与降级规则。`speak(text)` 的简写以本文件为准。

本契约是**前端组件级契约**（TypeScript 接口 + 回调事件），不是 HTTP 接口，
没有 OpenAPI 快照；事件由组件按发生顺序同步分发给订阅者。

- 提供方：M4（`packages/avatar` 数字人组件）
- 调用方：M2（学生端页面宿主）
- 当前阶段：**Mock**——不接入真实 TTS/ASR，见「Mock 阶段」一节

## 接口形状

```ts
type AvatarEmotion = "neutral" | "encouraging" | "thinking" | "celebrating";
type AvatarAction = "idle" | "nod" | "point" | "write";
type AvatarPlaybackStatus = "idle" | "speaking" | "error";

interface SpeakInput {
  utteranceId: string;
  text: string;
  emotion: AvatarEmotion;
  action: AvatarAction;
}

interface AvatarError {
  code: string;
  message: string;
  requestId: string;
  details: Record<string, unknown>;
}

type AvatarPlaybackStoppedReason = "client_stop" | "replaced";

type AvatarPlaybackEvent =
  | { type: "avatar_playback_started"; utteranceId: string }
  | { type: "avatar_playback_completed"; utteranceId: string }
  | { type: "avatar_playback_stopped"; utteranceId: string; reason: AvatarPlaybackStoppedReason }
  | { type: "avatar_playback_error"; utteranceId: string; error: AvatarError };

interface AvatarController {
  speak(input: SpeakInput): void;
  stop(utteranceId?: string): void;
  getStatus(): AvatarPlaybackStatus;
  subscribe(listener: (event: AvatarPlaybackEvent) => void): () => void;
}
```

## speak 输入

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `utteranceId` | string | 是 | 本次播报标识，**由 M2 为每次播报生成；重新播报必须使用新 ID**。见「utteranceId 与 requestId」 |
| `text` | string | 是 | 要播报的完整文本，长度 ≥ 1。只应是 tutoring SSE `completed` 的完整回答，见「与 tutoring SSE 的衔接」 |
| `emotion` | string | 是 | `AvatarEmotion`。不在枚举内的取值降级为 `neutral`，见「降级规则」 |
| `action` | string | 是 | `AvatarAction`。不在枚举内的取值降级为 `idle`，见「降级规则」 |

`speak` 返回 `void`，播放进度通过事件通知。

结构性入参错误属于**调用方缺陷**，`speak` **同步抛错**，不产生任何事件：
`utteranceId` 缺失或与进行中/已终止的播报重复、`text` 为空、字段类型错误。
注意与「降级规则」的区别：emotion/action 的**非法取值不抛错**，只降级渲染。

## 枚举

### AvatarEmotion（M4 冻结全集）

取值：`neutral` | `encouraging` | `thinking` | `celebrating`

| 值 | 含义 | 典型教学情境（映射规则归 M3） |
| --- | --- | --- |
| `neutral` | 中性平静，默认 | 常规陈述、无明确情绪倾向的内容 |
| `encouraging` | 鼓励、支持 | 学生尝试后、遇到挫折时的引导 |
| `thinking` | 沉思、引导思考 | 抛出问题、启发思路 |
| `celebrating` | 庆祝、肯定 | 学生完成题目或达成阶段目标 |

### AvatarAction（M4 冻结全集）

取值：`idle` | `nod` | `point` | `write`

| 值 | 含义 | 典型教学情境（映射规则归 M3） |
| --- | --- | --- |
| `idle` | 无额外动作，默认 | 常规播报 |
| `nod` | 点头 | 肯定、认同 |
| `point` | 指向内容区 | 引导学生注意板书或引用 |
| `write` | 书写板书 | 演示步骤、演算 |

**枚举全集由 M4 定义并在本文件冻结（唯一来源）。**
教学情境到取值的映射、以及模型输出是否落在枚举内的运行时校验归 **M3**
（见 `docs/tasks/m4.md`「依赖与边界」）。增删取值按「变更流程」执行。

### AvatarPlaybackStatus

取值：`idle` | `speaking` | `error`

| 值 | 含义 |
| --- | --- |
| `idle` | 无进行中播报（初始状态；`completed` / `stopped` 之后） |
| `speaking` | 有进行中的播报（`started` 之后、终止事件之前） |
| `error` | 上一次播报以 `avatar_playback_error` 终止，且之后没有新的 `speak` |

状态迁移由事件隐式推进，订阅事件即可推导状态；`getStatus()` 供未订阅期间查询。
`error` 状态下调用 `speak` 正常开始新播报并回到 `speaking`；调用 `stop()` 是 no-op
（上一个播报已经终止，见「stop() 幂等」）。

## 播放事件

事件 `type` 取值为小写 snake_case（`docs/code-standards.md:52`）。
**所有事件都携带 `utteranceId`**，M2 据此把事件关联到具体某次播报。

### avatar_playback_started

```json
{
  "type": "avatar_playback_started",
  "utteranceId": "utt_5e2b8a01"
}
```

该 `utteranceId` 的第一个事件，表示组件已接受输入并开始播报。

### avatar_playback_completed（终止事件）

```json
{
  "type": "avatar_playback_completed",
  "utteranceId": "utt_5e2b8a01"
}
```

播报自然播完。此后该 `utteranceId` 对应的状态回到 `idle`。

### avatar_playback_stopped（终止事件）

```json
{
  "type": "avatar_playback_stopped",
  "utteranceId": "utt_1c7d94f2",
  "reason": "client_stop"
}
```

`reason` 取值：`client_stop`（M2 调 `stop()` 主动停止）| `replaced`（被新的 `speak` 替换）。

### avatar_playback_error（终止事件）

```json
{
  "type": "avatar_playback_error",
  "utteranceId": "utt_3d9c52e7",
  "error": {
    "code": "AVATAR_PLAYBACK_FAILED",
    "message": "播放失败，文字回答已保留",
    "requestId": "req_6f2a91c4",
    "details": {}
  }
}
```

`error` 沿用 `docs/code-standards.md:74-80` 的错误结构，见「错误结构」一节。

本契约定义的错误码：

| code | 场景 |
| --- | --- |
| `AVATAR_PLAYBACK_FAILED` | 播放过程失败（Mock 阶段用于模拟失败路径；未来含音频/渲染失败） |
| `AVATAR_TTS_UNAVAILABLE` | （S1 预留）真实 TTS 不可用；触发语音→文字降级，播报不开始 |

## utteranceId 与 requestId

两者含义不同，**不得混用**：

| 标识 | 含义 | 生成方与规则 | 出现位置 |
| --- | --- | --- | --- |
| `utteranceId` | 标识**一次播报** | **M2 每次调用 `speak` 前新生成；重新播报必须用新 ID** | 所有播放事件 |
| `requestId` | **错误追踪** | 见下方规则 | 仅 `avatar_playback_error` 的 `error` 内 |

- `utteranceId` 是前端生成的播放标识，不是服务端实体 ID。样例使用 `utt_` + 不透明后缀的写法；
  **ID 形态待 M1 统一约定**，与 `packages/contracts/tutoring/tutoring-response.md` 的
  「ID 约定」一节同样处于待确认状态，确认前不要据此写解析逻辑。
- `error.requestId`：错误与某次后端请求相关时（如未来 TTS 调用失败），使用该请求的
  `requestId`（M1 `req_` 格式）；Mock/纯前端阶段无对应后端请求，由组件生成本地追踪 ID
  （样例写作 `req_` 前缀，同样待 M1 确认），仅供前端日志关联，不代表服务端请求。

## 核心语义规则

### 单一播报与替换

同一时间至多一个进行中播报。播报中再次调用 `speak`：

1. 旧 `utteranceId` **恰好产生一次** `avatar_playback_stopped`，`reason` 为 `replaced`；
2. 随后新 `utteranceId` 产生 `avatar_playback_started`，开始新播报；
3. 旧的 `stopped` 事件**先于**新的 `started` 事件分发；
4. 此后旧 `utteranceId` 不再产生任何事件。

### stop() 幂等

- `stop()` 停止当前播报；`stop(utteranceId)` 仅当该 ID 仍在播报时才停止
  （用于避免替换竞态下误停新播报）。两种形式都遵守以下不变量。
- **同一 `utteranceId` 最多产生一次 `avatar_playback_stopped`。**
- 已终止（`completed` / `stopped` / `error`）或本无播报时调用 `stop()`：no-op，
  **不产生新的终止事件**。

### 终止事件互斥

`avatar_playback_completed` / `avatar_playback_stopped` / `avatar_playback_error`
**互斥**：同一 `utteranceId` 产生其中任意一个后，不得再产生其他终止事件，
也不再产生该 ID 的任何事件。

## 与 tutoring SSE 的衔接（调用方 M2 的约束）

1. **只播报 tutoring SSE `completed`（`isComplete: true`）的完整回答**：
   `text` 取 `response.content`，`emotion` / `action` 取 `response.emotion` / `response.action`
   （结构见 `packages/contracts/tutoring/tutoring-response.md`）。
2. `stopped` / `error`（`isComplete: false`）的半截内容**只保留文字展示**：
   不调用 `speak`，也不为它补造 `emotion` / `action`。
   依据 `docs/code-standards.md:95`「未经服务端确认完成的半截回答不当作完成记录」。
3. 同一轮回答重新播报时，M2 生成**新** `utteranceId`。

时序示例：

```text
tutoring SSE completed (isComplete: true)
  → M2 生成 utteranceId
  → speak({ utteranceId, text, emotion, action })
  → avatar_playback_started → avatar_playback_completed
```

## 降级规则

1. `emotion` 不在 `AvatarEmotion` 内 → 按 `neutral` 渲染；
   `action` 不在 `AvatarAction` 内 → 按 `idle` 渲染。
2. 降级只影响展示元数据：`text` **完整保留**、播报照常进行，
   **不得因 emotion/action 非法让整轮回答失败**。
3. 校验的第一责任在 **M3**（服务端校验模型输出落在枚举内并完成教学情境映射）；
   本条是组件层**兜底**，防联调期脏数据直接进入渲染。
4. 降级不改写调用方入参：组件内部按降级值渲染即可；
   是否记录告警日志由实现决定，契约不强制。

## 错误结构

`avatar_playback_error` 的 `error` 字段沿用 `docs/code-standards.md:74-80`：

```json
{
  "code": "AVATAR_PLAYBACK_FAILED",
  "message": "播放失败，文字回答已保留",
  "requestId": "req_6f2a91c4",
  "details": {}
}
```

`message` 面向排查，不暴露堆栈与内部细节；面向学生的提示文案由 M2 决定。
错误码见「播放事件」一节的表。

## Mock 阶段

- 当前阶段（S0）组件为 **Mock 实现**：**不接入真实 TTS/ASR**。
  阶段归属以 `docs/tasks/m4.md`「第一阶段」为准：**真实 TTS 播报属 S1 后续实现**
  （2D 形象、播报、停止）；**ASR、录音文件转写属 S2**。
- Mock 按文本长度模拟播报时长后发出 `completed`；具体计时策略是实现细节，
  契约只保证本文件的事件语义。
- Mock 实现必须**明确标记**（`AGENTS.md:8`），不能作为生产完成证据；
  演示与评测记录须区分 Mock 与真实服务。
- 语音/文字降级路径（`docs/code-standards.md:91`）：语音不可用或失败时，
  文字回答始终保留展示。

## 不变量

组件实现违反以下任意一条即为缺陷（应被单元测试拦截）：

1. 每个 `utteranceId` 至多一个 `avatar_playback_started`，且是该 ID 的第一个事件。
2. 每个 `utteranceId` 至多一个终止事件（`completed` / `stopped` / `error` 三选一），
   终止事件之后不再有该 ID 的任何事件。
3. 同一 `utteranceId` 内，`started` 先于终止事件。
4. 替换场景：旧 ID 的 `stopped`（`reason` = `replaced`）先于新 ID 的 `started`。
5. `stop()` 幂等：同一 `utteranceId` 最多一次 `stopped`；已终止后重复 `stop()` 无事件。
6. 所有事件携带 `utteranceId`。
7. 非法 `emotion` / `action` 降级为 `neutral` / `idle`，且 `text` 完整保留。
8. 「只播报 `completed` 完整回答」由调用方 M2 保证；组件对空 `text` 同步抛错作为兜底。

## 变更流程

本契约是**公共接口**。按 `CONTRIBUTING.md:37`，变更需要至少 2 名评审人，
且必须包含 M2（调用方）与 M4（提供方）负责人。变更时同步：本文件、
[README.md](README.md) 与 [samples/](samples/)。
