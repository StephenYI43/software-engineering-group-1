import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './http-client'

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function textResponse(body: string, status: number): Response {
  return new Response(body, { status, headers: { 'Content-Type': 'text/html' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('成功时返回解析后的响应体', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ ok: true }, 200)))
    await expect(request<{ ok: boolean }>('/api/v1/x')).resolves.toEqual({ ok: true })
  })

  it('错误体符合契约结构时，采用服务端文案与 requestId', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            code: 'COURSE_NOT_FOUND',
            message: '未找到课程',
            requestId: 'req_0123456789ab4def8123456789abcdef',
            details: {},
          },
          404,
        ),
      ),
    )

    const error = await request('/api/v1/courses/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.kind).toBe('notFound')
    expect(apiError.status).toBe(404)
    expect(apiError.message).toBe('未找到课程')
    expect(apiError.requestId).toBe('req_0123456789ab4def8123456789abcdef')
    expect(apiError.code).toBe('COURSE_NOT_FOUND')
  })

  it('错误体不符合契约结构时（网关 HTML），走兜底文案且不伪造 requestId', async () => {
    // 平台的统一错误封装尚未实现，代理/网关返回 HTML 是预期内的情况。
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(textResponse('<html><body>502 Bad Gateway</body></html>', 502)),
    )

    const error = (await request('/api/v1/courses').catch((e: unknown) => e)) as ApiError
    expect(error.kind).toBe('server')
    expect(error.status).toBe(502)
    expect(error.message).toBe('服务暂时不可用，请稍后重试')
    // 关键：不得自己造一个 requestId
    expect(error.requestId).toBeUndefined()
    expect(error.code).toBeUndefined()
    // 也不得把 HTML 正文当成 message 展示
    expect(error.message).not.toContain('<html>')
  })

  it('缺少 requestId 的错误体视为不符合契约结构', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ code: 'X', message: '服务端消息' }, 404)),
    )

    const error = (await request('/api/v1/x').catch((e: unknown) => e)) as ApiError
    // 结构不完整 → 不采信服务端文案，改走兜底
    expect(error.message).toBe('未找到')
    expect(error.requestId).toBeUndefined()
  })

  it('401/403/404/422/429/5xx 映射到对应语义', async () => {
    const cases: Array<[number, string]> = [
      [401, 'unauthorized'],
      [403, 'forbidden'],
      [404, 'notFound'],
      [422, 'validation'],
      [429, 'rateLimited'],
      [503, 'server'],
    ]

    for (const [status, kind] of cases) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(textResponse('nope', status)))
      const error = (await request('/api/v1/x').catch((e: unknown) => e)) as ApiError
      expect(error.kind).toBe(kind)
    }
  })

  it('404 的兜底文案统一是「未找到」，不含「无权限」这类区分性措辞', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(textResponse('missing', 404)))
    const error = (await request('/api/v1/x').catch((e: unknown) => e)) as ApiError
    // 防枚举：不得让用户从文案推断出「资源存在但无权访问」
    expect(error.message).toBe('未找到')
    expect(error.message).not.toMatch(/无权限|禁止|不属于你/)
  })

  it('请求未发出时归类为 network，status 为 null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = (await request('/api/v1/x').catch((e: unknown) => e)) as ApiError
    expect(error.kind).toBe('network')
    expect(error.status).toBeNull()
  })
})
