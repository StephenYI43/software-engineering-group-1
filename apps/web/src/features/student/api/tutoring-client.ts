import type { TutoringResponse } from '../types'
import type { TutoringStage } from '../types'
import { ApiError, requestHeaders, responseError } from './http-client'
import {
  createSseDecoder,
  createTutoringProtocol,
  SseProtocolError,
  type TutoringEvent,
} from './tutoring-sse'

export type TutoringInput = {
  content: string
  requestedStage?: TutoringStage | null
  courseId?: string | null
}
export type TutoringSnapshot = {
  status: 'connecting' | 'streaming' | 'stopping' | 'completed' | 'stopped' | 'error' | 'unknown'
  turnId: string | null
  stage: TutoringStage | null
  isMock: boolean | null
  content: string
  response: TutoringResponse | null
  error: Error | null
  isComplete: boolean
}
export type TutoringRun = { done: Promise<TutoringSnapshot>; stop(): Promise<void>; cancel(): void }
type ClientOptions = {
  fetch?: typeof globalThis.fetch
  getHeaders?: () => HeadersInit | Promise<HeadersInit>
}
export type TutoringClient = ReturnType<typeof createTutoringClient>

function networkError(error: unknown): Error {
  return error instanceof ApiError || error instanceof SseProtocolError
    ? error
    : new ApiError({ kind: 'network', status: null, message: '连接已断开，本轮未完成，请重试' })
}

/** 凭证由宿主注入；此模块不存储 token，不自动续传或推进教学阶段。 */
export function createTutoringClient(options: ClientOptions = {}) {
  const fetch = options.fetch ?? globalThis.fetch.bind(globalThis)
  return {
    start(
      sessionId: string,
      input: TutoringInput,
      onChange: (state: TutoringSnapshot) => void,
    ): TutoringRun {
      const controller = new AbortController()
      const path = `/api/v1/tutoring/sessions/${encodeURIComponent(sessionId)}`
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
      let state: TutoringSnapshot = {
        status: 'connecting',
        turnId: null,
        stage: null,
        isMock: null,
        content: '',
        response: null,
        error: null,
        isComplete: false,
      }
      let settled = false
      let terminal: TutoringEvent | undefined
      let stopRequest: Promise<void> | undefined
      let stopTimer: ReturnType<typeof setTimeout> | undefined
      let resolveDone: (value: TutoringSnapshot) => void = () => {}
      const done = new Promise<TutoringSnapshot>((resolve) => {
        resolveDone = resolve
      })
      const publish = (next: TutoringSnapshot) => {
        state = next
        if (!settled) onChange(next)
      }
      const finish = (next: TutoringSnapshot, notify = true) => {
        if (settled) return
        state = next
        settled = true
        clearTimeout(stopTimer)
        if (notify) onChange(next)
        resolveDone(next)
      }
      const disconnect = () => {
        controller.abort()
        void reader?.cancel().catch(() => {
          /* 已断开的连接无需再次报告取消失败。 */
        })
      }
      publish(state)

      async function execute() {
        try {
          if (
            !sessionId.trim() ||
            !input.content.trim() ||
            Array.from(input.content).length > 2000 ||
            (input.requestedStage != null &&
              !['thought', 'hint', 'step', 'summary'].includes(input.requestedStage)) ||
            (input.courseId != null &&
              (typeof input.courseId !== 'string' || !input.courseId.trim()))
          ) {
            throw new SseProtocolError('请输入 1—2000 字的问题，并检查课程与阶段参数')
          }
          const headers = requestHeaders(await options.getHeaders?.(), 'text/event-stream')
          if (settled) return
          headers.set('Content-Type', 'application/json')
          // 显式白名单，不把调用方附带的 stage/emotion/action 等字段传给服务端。
          const body = {
            content: input.content,
            ...(input.requestedStage !== undefined && { requestedStage: input.requestedStage }),
            ...(input.courseId !== undefined && { courseId: input.courseId }),
          }
          const response = await fetch(`${path}/messages`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            signal: controller.signal,
          })
          if (settled) {
            void response.body?.cancel()
            return
          }
          if (!response.ok) throw await responseError(response)
          if (
            response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase() !==
              'text/event-stream' ||
            response.body === null
          ) {
            throw new SseProtocolError('服务未返回答疑流，本轮未完成')
          }
          reader = response.body.getReader()
          const decoder = createSseDecoder()
          const protocol = createTutoringProtocol(sessionId)
          const accept = (event: TutoringEvent) => {
            protocol.accept(event)
            if (event.type === 'started')
              publish({
                ...state,
                status: 'streaming',
                turnId: event.turnId,
                stage: event.stage,
                isMock: event.isMock,
              })
            else if (event.type === 'delta')
              publish({ ...state, content: state.content + event.textDelta })
            else {
              terminal = event
              clearTimeout(stopTimer)
            }
          }
          while (!settled) {
            const chunk = await reader.read()
            if (settled) return
            if (chunk.done) break
            for (const event of decoder.push(chunk.value)) accept(event)
          }
          for (const event of decoder.finish()) accept(event)
          protocol.finish()
          // 完成态等 EOF 验证后发布，避免多终帧/尾部垃圾曾触发完整回答 UI。
          if (terminal?.type === 'completed')
            finish({
              ...state,
              status: 'completed',
              content: terminal.response.content,
              response: terminal.response,
              error: null,
              isComplete: true,
            })
          else if (terminal?.type === 'stopped')
            finish({ ...state, status: 'stopped', error: null })
          else if (terminal?.type === 'error')
            finish({
              ...state,
              status: 'error',
              error: new ApiError({ kind: 'server', status: null, ...terminal.error }),
            })
        } catch (error) {
          if (!settled) {
            finish({
              ...state,
              status: 'error',
              response: null,
              isComplete: false,
              error: networkError(error),
            })
            disconnect()
          }
        } finally {
          reader?.releaseLock()
        }
      }
      void execute()
      return {
        done,
        stop(): Promise<void> {
          if (settled || terminal !== undefined || state.turnId === null) return Promise.resolve()
          if (stopRequest !== undefined) return stopRequest
          const turnId = state.turnId
          publish({ ...state, status: 'stopping' })
          stopTimer = setTimeout(() => {
            finish({
              ...state,
              status: 'unknown',
              error: new Error('停止确认超时，结果未知；本轮未完成'),
            })
            disconnect()
          }, 5000)
          stopRequest = (async () => {
            try {
              const headers = requestHeaders(await options.getHeaders?.())
              if (settled || terminal !== undefined) return
              const response = await fetch(`${path}/turns/${encodeURIComponent(turnId)}/stop`, {
                method: 'POST',
                headers,
                signal: controller.signal,
              })
              if (!response.ok) throw await responseError(response)
              // 兼容旧 200 与已裁定的 204；只认 SSE 终帧，不解析内部状态枚举。
            } catch (error) {
              if (!settled && terminal === undefined)
                publish({ ...state, error: networkError(error) })
            }
          })()
          return stopRequest
        },
        cancel(): void {
          if (settled) return
          finish(
            {
              ...state,
              status: 'error',
              response: null,
              isComplete: false,
              error: networkError(null),
            },
            false,
          )
          disconnect()
        },
      }
    },
  }
}
