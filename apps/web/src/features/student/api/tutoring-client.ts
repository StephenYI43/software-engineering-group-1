import type { Fixture } from '../mocks/tutoring-fixtures'
import type { MockScenario, TutoringTurnKind } from '../mocks'
import type { TutoringResponse } from '../types'
import { fetchTutoringTurn } from '../mocks'

/**
 * 答疑数据入口。
 *
 * **S0 阶段全部走 Mock**，且只取「完整的一轮回答」——不实现流式。
 *
 * 流式答疑（SSE）不属于本子 Issue 的范围，留给下一个子 Issue。届时需要在此层
 * 实现（依据 `packages/contracts/tutoring/sse-events.md`）：
 *
 * - 用 `fetch` + `ReadableStream`，**不用** `EventSource`（需 POST 体与 Authorization 头）
 * - 自行按空行切帧、解析 `event:` / `data:` 行、处理跨 chunk 的半截帧
 * - 校验 `seq` 从 1 严格递增，跳号或重复视为协议错误
 * - 停止按钮走 `POST .../turns/{turnId}/stop` 并**保持连接打开**直到收到 `stopped`
 *   事件（兜底超时 5s）；**不得**用 `AbortController` 实现停止，否则服务端会记为
 *   `client_disconnect` 而非 `client_stop`
 * - `stopped` / `error` 均不推进教学阶段，重试产生新轮后无需重置阶段指示器
 *
 * 真实端点：`POST /api/v1/tutoring/sessions/{sessionId}/messages`
 */
export function getTutoringTurn(
  kind: TutoringTurnKind,
  scenario: MockScenario,
): Promise<Fixture<TutoringResponse>> {
  return fetchTutoringTurn(kind, scenario)
}
