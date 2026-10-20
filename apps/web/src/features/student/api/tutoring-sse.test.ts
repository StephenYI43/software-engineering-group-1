import { describe, expect, it } from 'vitest'
import { createSseDecoder, createTutoringProtocol, SseProtocolError } from './tutoring-sse'
import { answer, completed, delta, frame, started } from './tutoring-test-utils'

function decode(parts: string[]) {
  const decoder = createSseDecoder()
  return [
    ...parts.flatMap((part) => decoder.push(new TextEncoder().encode(part))),
    ...decoder.finish(),
  ]
}

describe('SSE 帧与结构校验', () => {
  it.each(['\n', '\r\n'])('支持帧边界 %j 与跨 chunk', (newline) => {
    const text = frame('started', started, newline) + frame('delta', delta, newline)
    expect(decode([text.slice(0, 7), text.slice(7, -1), text.slice(-1)])).toEqual([
      { type: 'started', ...started },
      { type: 'delta', ...delta },
    ])
  })

  it('UTF-8 汉字跨字节边界时不会损坏', () => {
    const decoder = createSseDecoder()
    const events = Array.from(new TextEncoder().encode(frame('delta', delta))).flatMap((byte) =>
      decoder.push(new Uint8Array([byte])),
    )
    expect([...events, ...decoder.finish()]).toEqual([{ type: 'delta', ...delta }])
  })

  it('支持 completed、stopped 和契约错误', () => {
    const error = {
      code: 'MODEL_TIMEOUT',
      message: '生成超时',
      requestId: 'req_synthetic',
      details: {},
    }
    const events = decode([
      frame('completed', completed),
      frame('stopped', { seq: 3, turnId: 'turn_test_1', isComplete: false, reason: 'client_stop' }),
      frame('error', { seq: 3, turnId: 'turn_test_1', isComplete: false, error }),
    ])
    expect(events.map((event) => event.type)).toEqual(['completed', 'stopped', 'error'])
  })

  it('忽略 SSE 注释心跳', () => {
    expect(decode([': keepalive\n\n', frame('started', started)])).toEqual([
      { type: 'started', ...started },
    ])
  })

  it.each([
    'data: {}\n\n',
    'event: unknown\ndata: {}\n\n',
    'event: started\ndata: nope\n\n',
    'event: started\ndata: {}\ndata: {}\n\n',
    'event: started\nevent: delta\ndata: {}\n\n',
    frame('started', { ...started, seq: '1' }),
    frame('started', { ...started, stage: 'reasoning' }),
    frame('started', { ...started, isMock: 'false' }),
    frame('delta', { ...delta, textDelta: 2 }),
    frame('completed', { ...completed, isComplete: false }),
    frame('stopped', { seq: 3, turnId: 'turn_test_1', isComplete: false, reason: 'other' }),
    frame('error', {
      seq: 3,
      turnId: 'turn_test_1',
      isComplete: false,
      error: { code: 'MODEL_TIMEOUT', message: 'x', requestId: 'req_x', details: [] },
    }),
  ])('拒绝非法帧 %#', (text) => {
    expect(() => decode([text])).toThrow(SseProtocolError)
  })

  it.each([
    answer({
      citations: [
        { citationId: 'c1', documentId: 'd', documentTitle: 'x', snippet: 'x', pageNumber: 0 },
      ],
    }),
    answer({ hasEvidence: false }),
    answer({ followUps: ['1', '2', '3', '4'] }),
    answer({ followUps: ['x'.repeat(201)] }),
    { ...answer(), citations: null },
    { ...answer(), emotion: 'happy' },
    { ...answer(), emotion: ['neutral'] },
    { ...answer(), action: ['idle'] },
    { ...answer(), action: 'dance' },
    { ...answer(), createdAt: 'invalid date' },
  ])('拒绝不符合完整响应契约的数据 %#', (response) => {
    expect(() => decode([frame('completed', { ...completed, response })])).toThrow(SseProtocolError)
  })

  it('拒绝 EOF 时残帧', () => {
    expect(() => decode([frame('started', started).slice(0, -1)])).toThrow(SseProtocolError)
  })

  it('拒绝损坏或截断的 UTF-8', () => {
    const decoder = createSseDecoder()
    decoder.push(new Uint8Array([0xe4]))
    expect(() => decoder.finish()).toThrow(SseProtocolError)
  })
})

function protocol(...parts: string[]) {
  const state = createTutoringProtocol('session_test')
  for (const event of decode(parts)) state.accept(event)
  state.finish()
}

describe('流式协议状态机', () => {
  it('接受 started → delta → completed', () => {
    expect(() =>
      protocol(frame('started', started), frame('delta', delta), frame('completed', completed)),
    ).not.toThrow()
  })

  it.each([
    [frame('delta', { ...delta, seq: 1 })],
    [frame('started', { ...started, seq: 2 })],
    [frame('started', started)],
    [frame('started', started), frame('delta', { ...delta, seq: 3 })],
    [frame('started', started), frame('delta', { ...delta, seq: 1 })],
    [frame('started', started), frame('delta', { ...delta, turnId: 'other' })],
    [frame('started', started), frame('started', { ...started, seq: 2 })],
    [
      frame('started', started),
      frame('delta', delta),
      frame('completed', completed),
      frame('delta', { ...delta, seq: 4 }),
    ],
    [
      frame('started', started),
      frame('delta', delta),
      frame('completed', { ...completed, response: answer({ sessionId: 'other' }) }),
    ],
    [
      frame('started', started),
      frame('delta', delta),
      frame('completed', { ...completed, response: answer({ turnId: 'other' }) }),
    ],
    [
      frame('started', started),
      frame('delta', delta),
      frame('completed', { ...completed, response: answer({ stage: 'summary' }) }),
    ],
    [
      frame('started', started),
      frame('delta', delta),
      frame('completed', { ...completed, response: answer({ isMock: false }) }),
    ],
  ])('拒绝违反顺序、身份或终止唯一性的不完整流 %#', (...parts) => {
    expect(() => protocol(...parts)).toThrow(SseProtocolError)
  })
})
