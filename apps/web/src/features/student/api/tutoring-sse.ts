import type { ApiErrorBody, Citation, TutoringResponse, TutoringStage } from '../types'

type EventBase = { seq: number; turnId: string }
export type TutoringEvent = EventBase &
  (
    | { type: 'started'; stage: TutoringStage; isMock: boolean }
    | { type: 'delta'; textDelta: string }
    | { type: 'completed'; isComplete: true; response: TutoringResponse }
    /**
     * `reason` 只有 `client_stop`。#62（96a6304）修订后的契约把 `client_disconnect`
     * 收进服务端内部状态与日志、**不再作为事件下发**：连接已断，没有接收方。
     * 因此收到 `client_disconnect` 属于协议违约，按 SseProtocolError 处理，
     * 不再当成合法的停止原因静默接受。
     */
    | { type: 'stopped'; isComplete: false; reason: 'client_stop' }
    | { type: 'error'; isComplete: false; error: ApiErrorBody }
  )

export class SseProtocolError extends Error {
  constructor(message = '答疑流格式异常，本轮未完成，请重试') {
    super(message)
    this.name = 'SseProtocolError'
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function stage(value: unknown): value is TutoringStage {
  return value === 'thought' || value === 'hint' || value === 'step' || value === 'summary'
}

function citation(value: unknown): value is Citation {
  return (
    record(value) &&
    text(value.citationId) &&
    text(value.documentId) &&
    text(value.documentTitle) &&
    typeof value.snippet === 'string' &&
    typeof value.pageNumber === 'number' &&
    Number.isSafeInteger(value.pageNumber) &&
    value.pageNumber >= 1
  )
}

function response(value: unknown): value is TutoringResponse {
  if (!record(value)) return false
  return (
    text(value.turnId) &&
    text(value.sessionId) &&
    stage(value.stage) &&
    typeof value.content === 'string' &&
    Array.isArray(value.citations) &&
    value.citations.every(citation) &&
    typeof value.hasEvidence === 'boolean' &&
    value.hasEvidence === value.citations.length > 0 &&
    Array.isArray(value.followUps) &&
    value.followUps.length <= 3 &&
    value.followUps.every(
      (item: unknown) => typeof item === 'string' && Array.from(item).length <= 200,
    ) &&
    typeof value.emotion === 'string' &&
    ['neutral', 'encouraging', 'thinking', 'celebrating'].includes(value.emotion) &&
    typeof value.action === 'string' &&
    ['idle', 'nod', 'point', 'write'].includes(value.action) &&
    typeof value.isMock === 'boolean' &&
    text(value.promptVersion) &&
    text(value.createdAt) &&
    /(?:Z|\+00:00)$/.test(value.createdAt) &&
    Number.isFinite(Date.parse(value.createdAt))
  )
}

function parseFrame(frame: string): TutoringEvent | null {
  let name: string | undefined
  let data: string | undefined
  for (const line of frame.replaceAll('\r\n', '\n').split('\n')) {
    if (line === '' || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = line.slice(0, colon)
    const value = line.slice(colon + 1).replace(/^ /, '')
    if (colon < 0) throw new SseProtocolError()
    if (field === 'event' && name === undefined) name = value
    else if (field === 'data' && data === undefined) data = value
    else throw new SseProtocolError()
  }
  if (name === undefined && data === undefined) return null
  if (name === undefined || data === undefined) throw new SseProtocolError()
  let raw: unknown
  try {
    raw = JSON.parse(data)
  } catch {
    throw new SseProtocolError()
  }
  if (!record(raw) || !Number.isSafeInteger(raw.seq) || Number(raw.seq) < 1 || !text(raw.turnId)) {
    throw new SseProtocolError()
  }
  let fields: string[]
  let valid: boolean
  switch (name) {
    case 'started':
      fields = ['stage', 'isMock']
      valid = stage(raw.stage) && typeof raw.isMock === 'boolean'
      break
    case 'delta':
      fields = ['textDelta']
      valid = typeof raw.textDelta === 'string'
      break
    case 'completed':
      fields = ['isComplete', 'response']
      valid = raw.isComplete === true && response(raw.response)
      break
    case 'stopped':
      fields = ['isComplete', 'reason']
      // 只接受 client_stop：client_disconnect 是服务端内部状态，下发即协议违约（#62/96a6304）。
      valid = raw.isComplete === false && raw.reason === 'client_stop'
      break
    case 'error':
      fields = ['isComplete', 'error']
      valid =
        raw.isComplete === false &&
        record(raw.error) &&
        text(raw.error.code) &&
        typeof raw.error.message === 'string' &&
        text(raw.error.requestId) &&
        record(raw.error.details)
      break
    default:
      throw new SseProtocolError()
  }
  if (!valid || Object.keys(raw).some((key) => !['seq', 'turnId', ...fields].includes(key))) {
    throw new SseProtocolError()
  }
  // 上面逐字段校验后才将不可信数据收窄为封闭事件联合。
  return { ...raw, type: name } as TutoringEvent
}

/** 增量 UTF-8 解码；只有收到完整空行边界才解析事件。 */
export function createSseDecoder() {
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  function drain(onEvent?: (event: TutoringEvent) => void): TutoringEvent[] {
    const events: TutoringEvent[] = []
    let boundary: RegExpExecArray | null
    while ((boundary = /\r?\n\r?\n/.exec(buffer)) !== null) {
      if (boundary.index > 1_048_576) throw new SseProtocolError('答疑流单帧过大，本轮未完成')
      const event = parseFrame(buffer.slice(0, boundary.index))
      buffer = buffer.slice(boundary.index + boundary[0].length)
      if (event !== null) {
        // 有效前缀立即交付；同一网络 chunk 后续坏帧不能抹掉此前正文。
        onEvent?.(event)
        events.push(event)
      }
    }
    if (buffer.length > 1_048_576) throw new SseProtocolError('答疑流单帧过大，本轮未完成')
    return events
  }
  return {
    push(chunk: Uint8Array, onEvent?: (event: TutoringEvent) => void): TutoringEvent[] {
      try {
        buffer += decoder.decode(chunk, { stream: true })
      } catch {
        throw new SseProtocolError()
      }
      return drain(onEvent)
    },
    finish(onEvent?: (event: TutoringEvent) => void): TutoringEvent[] {
      try {
        buffer += decoder.decode()
      } catch {
        throw new SseProtocolError()
      }
      const events = drain(onEvent)
      if (buffer.trim() !== '') throw new SseProtocolError('答疑流提前结束，本轮未完成')
      return events
    },
  }
}

/** 不依赖 UI 的协议状态机；终止后继续到达的数据一律拒绝。 */
export function createTutoringProtocol(sessionId: string) {
  let first: Extract<TutoringEvent, { type: 'started' }> | undefined
  let nextSeq = 1
  let terminal = false
  return {
    accept(event: TutoringEvent): void {
      if (terminal || event.seq !== nextSeq) throw new SseProtocolError()
      if (first === undefined) {
        if (event.type !== 'started') throw new SseProtocolError()
        first = event
      } else if (event.type === 'started' || event.turnId !== first.turnId)
        throw new SseProtocolError()
      if (
        event.type === 'completed' &&
        (event.response.sessionId !== sessionId ||
          event.response.turnId !== first.turnId ||
          event.response.stage !== first.stage ||
          event.response.isMock !== first.isMock)
      )
        throw new SseProtocolError()
      terminal = event.type === 'completed' || event.type === 'stopped' || event.type === 'error'
      nextSeq += 1
    },
    finish(): void {
      if (!terminal) throw new SseProtocolError('答疑流缺少终止事件，本轮未完成')
    },
  }
}
