import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTutoringClient, type TutoringSnapshot } from './tutoring-client'
import {
  answer,
  completed,
  controlledResponse,
  delta,
  frame,
  started,
  streamResponse,
} from './tutoring-test-utils'

afterEach(() => {
  vi.useRealTimers()
})

function normal() {
  return streamResponse([
    frame('started', started),
    frame('delta', delta),
    frame('completed', completed),
  ])
}

function sentJson(init: RequestInit | undefined): unknown {
  if (typeof init?.body !== 'string') throw new Error('expected JSON request body')
  return JSON.parse(init.body) as unknown
}

describe('SSE 网络客户端', () => {
  it('POST 仅发送允许字段，复用注入凭证，completed 替换临时正文', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(normal())
    const changes: TutoringSnapshot[] = []
    const client = createTutoringClient({
      fetch,
      getHeaders: () => new Headers({ Authorization: 'Bearer synthetic' }),
    })
    const input = { content: '合成问题', stage: 'summary', emotion: 'happy' }
    const result = await client.start('session_test', input, (state) => changes.push(state)).done
    expect(fetch.mock.calls[0]?.[0]).toBe('/api/v1/tutoring/sessions/session_test/messages')
    const options = fetch.mock.calls[0]?.[1]
    if (options === undefined) throw new Error('missing request')
    expect(options.method).toBe('POST')
    expect(sentJson(options)).toEqual({ content: '合成问题' })
    const headers = new Headers(options.headers)
    expect(headers.get('Authorization')).toBe('Bearer synthetic')
    expect(headers.get('Accept')).toBe('text/event-stream')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(changes.some((state) => state.content === '临时正文' && !state.isComplete)).toBe(true)
    expect(result).toMatchObject({
      status: 'completed',
      content: '最终回答',
      response: answer(),
      isComplete: true,
    })
  })

  it.each(['stopped', 'error'])('%s 保留部分正文且不给出完整 response', async (type) => {
    const terminal =
      type === 'stopped'
        ? { seq: 3, turnId: 'turn_test_1', isComplete: false, reason: 'client_stop' }
        : {
            seq: 3,
            turnId: 'turn_test_1',
            isComplete: false,
            error: {
              code: 'MODEL_TIMEOUT',
              message: '模型超时',
              requestId: 'req_synthetic',
              details: {},
            },
          }
    const client = createTutoringClient({
      fetch: vi
        .fn<typeof globalThis.fetch>()
        .mockResolvedValue(
          streamResponse([frame('started', started), frame('delta', delta), frame(type, terminal)]),
        ),
    })
    const result = await client.start('session_test', { content: '问题' }, () => {}).done
    expect(result).toMatchObject({
      status: type,
      content: '临时正文',
      response: null,
      isComplete: false,
    })
    if (type === 'error')
      expect(result.error).toMatchObject({ code: 'MODEL_TIMEOUT', requestId: 'req_synthetic' })
  })

  it('完整终帧后仍有事件时，不曾发布 completed', async () => {
    const changes: TutoringSnapshot[] = []
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(
        streamResponse([
          frame('started', started),
          frame('delta', delta),
          frame('completed', completed),
          frame('delta', { ...delta, seq: 4 }),
        ]),
      )
    const result = await createTutoringClient({ fetch }).start(
      'session_test',
      { content: '问题' },
      (state) => changes.push(state),
    ).done
    expect(result).toMatchObject({ status: 'error', response: null, isComplete: false })
    expect(changes.some((state) => state.isComplete)).toBe(false)
  })

  it('EOF 缺少终帧时按未完成失败', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(streamResponse([frame('started', started), frame('delta', delta)]))
    expect(
      await createTutoringClient({ fetch }).start('session_test', { content: '问题' }, () => {})
        .done,
    ).toMatchObject({ status: 'error', content: '临时正文', response: null, isComplete: false })
  })

  it('非 SSE 响应拒绝作为回答展示', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(new Response('not SSE', { status: 200 }))
    const result = await createTutoringClient({ fetch }).start(
      'session_test',
      { content: '问题' },
      () => {},
    ).done
    expect(result).toMatchObject({ status: 'error', isComplete: false, response: null })
  })

  it('HTTP 401 复用统一错误语义', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'TOKEN_REQUIRED',
          message: '需要登录',
          requestId: 'req_test',
          details: {},
        }),
        { status: 401 },
      ),
    )
    const result = await createTutoringClient({ fetch }).start(
      'session_test',
      { content: '问题' },
      () => {},
    ).done
    expect(result.error).toMatchObject({ kind: 'unauthorized', status: 401, requestId: 'req_test' })
  })

  it.each(['', 'x'.repeat(2001)])('拒绝超出长度范围的提问 %#', async (content) => {
    const fetch = vi.fn<typeof globalThis.fetch>()
    const result = await createTutoringClient({ fetch }).start(
      'session_test',
      { content },
      () => {},
    ).done
    expect(result.status).toBe('error')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('重试创建新请求，不传阶段推进指令或复用旧 turn', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(streamResponse([frame('started', started), frame('delta', delta)]))
      .mockResolvedValueOnce(
        streamResponse([
          frame('started', { ...started, turnId: 'turn_test_2' }),
          frame('completed', {
            seq: 2,
            turnId: 'turn_test_2',
            isComplete: true,
            response: answer({ turnId: 'turn_test_2' }),
          }),
        ]),
      )
    const client = createTutoringClient({ fetch })
    await client.start('session_test', { content: '问题' }, () => {}).done
    const result = await client.start('session_test', { content: '问题' }, () => {}).done
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls.map((call) => sentJson(call[1]))).toEqual([
      { content: '问题' },
      { content: '问题' },
    ])
    expect(result.turnId).toBe('turn_test_2')
  })
})

describe('停止与连接生命周期', () => {
  it('停止调用端点但保持连接；重复停止不重复发送，正常 stopped 清除兜底', async () => {
    vi.useFakeTimers()
    const source = controlledResponse()
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(source.response)
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    const run = createTutoringClient({ fetch }).start('session_test', { content: '问题' }, () => {})
    source.send('started', started)
    source.send('delta', delta)
    await vi.advanceTimersByTimeAsync(0)
    await Promise.all([run.stop(), run.stop()])
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1]?.[0]).toBe(
      '/api/v1/tutoring/sessions/session_test/turns/turn_test_1/stop',
    )
    expect(fetch.mock.calls[1]?.[1]?.method).toBe('POST')
    await vi.advanceTimersByTimeAsync(4999)
    expect(source.cancelled).toBe(false)
    expect(fetch.mock.calls[0]?.[1]?.signal?.aborted).toBe(false)
    source.send('stopped', {
      seq: 3,
      turnId: 'turn_test_1',
      isComplete: false,
      reason: 'client_stop',
    })
    source.close()
    expect(await run.done).toMatchObject({
      status: 'stopped',
      isComplete: false,
      content: '临时正文',
    })
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetch.mock.calls[0]?.[1]?.signal?.aborted).toBe(false)
    await run.stop()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('5 秒未确认才 abort 并提示结果未知', async () => {
    vi.useFakeTimers()
    const source = controlledResponse()
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(source.response)
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    const run = createTutoringClient({ fetch }).start('session_test', { content: '问题' }, () => {})
    source.send('started', started)
    source.send('delta', delta)
    await vi.advanceTimersByTimeAsync(0)
    await run.stop()
    await vi.advanceTimersByTimeAsync(4999)
    expect(source.cancelled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await run.done).toMatchObject({
      status: 'unknown',
      isComplete: false,
      response: null,
      content: '临时正文',
    })
    expect(fetch.mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    expect(source.cancelled).toBe(true)
  })

  it('stop 请求失败也不立即切断 SSE，仍等待服务端终帧', async () => {
    vi.useFakeTimers()
    const source = controlledResponse()
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(source.response)
      .mockResolvedValueOnce(new Response('failure', { status: 503 }))
    const run = createTutoringClient({ fetch }).start('session_test', { content: '问题' }, () => {})
    source.send('started', started)
    await vi.advanceTimersByTimeAsync(0)
    await run.stop()
    expect(source.cancelled).toBe(false)
    source.send('completed', { ...completed, seq: 2 })
    source.close()
    expect(await run.done).toMatchObject({ status: 'completed', isComplete: true })
  })

  it('卸载取消释放连接，不发布完成状态或后续回调', async () => {
    const source = controlledResponse()
    const changes: TutoringSnapshot[] = []
    const run = createTutoringClient({
      fetch: vi.fn<typeof globalThis.fetch>().mockResolvedValue(source.response),
    }).start('session_test', { content: '问题' }, (state) => changes.push(state))
    source.send('started', started)
    await vi.waitFor(() => expect(changes.at(-1)?.turnId).toBe('turn_test_1'))
    const count = changes.length
    run.cancel()
    expect(await run.done).toMatchObject({ status: 'error', isComplete: false })
    expect(source.cancelled).toBe(true)
    expect(changes).toHaveLength(count)
  })
})
