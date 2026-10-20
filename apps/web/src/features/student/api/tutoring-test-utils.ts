import type { TutoringResponse } from '../types'

export function answer(overrides: Partial<TutoringResponse> = {}): TutoringResponse {
  return {
    turnId: 'turn_test_1',
    sessionId: 'session_test',
    stage: 'thought',
    content: '最终回答',
    citations: [
      {
        citationId: 'c1',
        documentId: 'doc_test',
        documentTitle: '合成课件.pdf',
        pageNumber: 1,
        snippet: '合成依据',
      },
    ],
    hasEvidence: true,
    followUps: ['你会怎么尝试？'],
    emotion: 'encouraging',
    action: 'nod',
    isMock: true,
    promptVersion: 'guided-tutoring.v1',
    createdAt: '2026-10-20T00:00:00Z',
    ...overrides,
  }
}

export const started = { seq: 1, turnId: 'turn_test_1', stage: 'thought', isMock: true }
export const delta = { seq: 2, turnId: 'turn_test_1', textDelta: '临时正文' }
export const completed = { seq: 3, turnId: 'turn_test_1', isComplete: true, response: answer() }

export function frame(event: string, data: unknown, newline = '\n'): string {
  return `event: ${event}${newline}data: ${JSON.stringify(data)}${newline}${newline}`
}

/** 真正的 ReadableStream；测试只替换网络边界，保留解析和流生命周期。 */
export function streamResponse(parts: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        for (const part of parts) controller.enqueue(encoder.encode(part))
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  )
}

export function controlledResponse() {
  let controller: ReadableStreamDefaultController<Uint8Array>
  let cancelled = false
  const encoder = new TextEncoder()
  const response = new Response(
    new ReadableStream<Uint8Array>({
      start(value) {
        controller = value
      },
      cancel() {
        cancelled = true
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
  return {
    response,
    send(event: string, data: unknown) {
      controller.enqueue(encoder.encode(frame(event, data)))
    },
    close() {
      controller.close()
    },
    get cancelled() {
      return cancelled
    },
  }
}
