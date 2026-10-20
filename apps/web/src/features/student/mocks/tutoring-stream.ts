import { parseScenario, parseTutoringTurnKind } from './index'
import { noEvidence, summaryAfterAttempt, thoughtWithCitation } from './tutoring-fixtures'

/** 只由开发环境动态加载，模拟真正 SSE 字节流；无模型、RAG 或真实音频。 */
export function createMockTutoringFetch(search: string): typeof globalThis.fetch {
  const scenario = parseScenario(search)
  const kind = parseTutoringTurnKind(search)
  const turns = new Map<string, () => void>()
  return (input, init) => {
    if (init?.signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'))
    const url = new URL(
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
      'http://mock.invalid',
    )
    const stop = /\/turns\/([^/]+)\/stop$/.exec(url.pathname)
    if (stop !== null) {
      const known = turns.get(decodeURIComponent(stop[1] ?? ''))
      if (known === undefined) return Promise.resolve(new Response(null, { status: 404 }))
      known()
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    const match = /\/sessions\/([^/]+)\/messages$/.exec(url.pathname)
    if (match === null || init?.method !== 'POST')
      return Promise.resolve(new Response(null, { status: 404 }))
    if (scenario === 'error-raw')
      return Promise.resolve(
        new Response('<html>synthetic gateway failure</html>', { status: 502 }),
      )
    if (scenario === 'error')
      return Promise.resolve(
        Response.json(
          {
            code: 'TUTORING_SESSION_NOT_FOUND',
            message: '未找到答疑会话',
            requestId: 'req_0123456789ab4def8123456789abcdef',
            details: {},
          },
          { status: 404 },
        ),
      )
    const fixture =
      scenario === 'empty' || kind === 'noEvidence'
        ? noEvidence
        : kind === 'summary'
          ? summaryAfterAttempt
          : thoughtWithCitation
    const { _fixture, ...payload } = fixture
    const turnId = `turn_${crypto.randomUUID().replaceAll('-', '')}`
    const sessionId = decodeURIComponent(match[1] ?? '')
    const response = { ...payload, turnId, sessionId }
    const encoder = new TextEncoder()
    let timers: ReturnType<typeof setTimeout>[] = []
    let closed = false
    const clear = () => {
      for (const timer of timers) clearTimeout(timer)
      timers = []
    }
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        let seq = 1
        const send = (event: string, data: object) =>
          controller.enqueue(
            encoder.encode(
              `event: ${event}\ndata: ${JSON.stringify({ seq: seq++, turnId, ...data })}\n\n`,
            ),
          )
        turns.set(turnId, () => {
          if (closed) return
          clear()
          send('stopped', { isComplete: false, reason: 'client_stop' })
          controller.close()
          closed = true
        })
        // 演示只保留最近 32 轮的停止幂等记录。
        if (turns.size > 32) turns.delete(turns.keys().next().value ?? '')
        send('started', { stage: response.stage, isMock: response.isMock })
        const middle = Math.ceil(response.content.length / 2)
        timers = [
          setTimeout(
            () => {
              if (!closed) send('delta', { textDelta: response.content.slice(0, middle) })
            },
            scenario === 'slow' ? 1000 : 40,
          ),
          setTimeout(
            () => {
              if (closed) return
              send('delta', { textDelta: response.content.slice(middle) })
              send('completed', { isComplete: true, response })
              controller.close()
              closed = true
              clear()
            },
            scenario === 'slow' ? 2500 : 80,
          ),
        ]
      },
      cancel() {
        closed = true
        clear()
      },
    })
    return Promise.resolve(
      new Response(body, {
        headers: { 'Content-Type': 'text/event-stream', 'X-Demo-Fixture': String(_fixture) },
      }),
    )
  }
}
