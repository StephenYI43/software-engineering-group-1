import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  TeacherRequestError,
  getClassOverview,
  requestClassOverview,
} from './class-overview-client'

const OK_BODY = {
  classId: 'class_mock_c01',
  period: {
    from: '2026-09-09T16:00:00Z',
    to: '2026-09-16T16:00:00Z',
    timezone: 'Asia/Shanghai',
    days: 7,
  },
  dataThrough: null,
  generatedAt: '2026-09-17T01:00:00Z',
  summary: {
    totalDurationSeconds: { state: 'unknown', reason: 'no_events_in_period' },
    activeStudentCount: { state: 'unknown', reason: 'no_events_in_period' },
    submissionCount: { state: 'unknown', reason: 'no_events_in_period' },
    coverage: { studentCount: 3, studentsWithData: 0, studentsWithoutData: 3 },
  },
  weakPoints: { byQuestionType: [], byChapter: [] },
  students: [],
}

function stubFetch(response: Response | Error) {
  vi.stubGlobal('fetch', () =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('班级概览客户端（示意数据分支）', () => {
  it('开发环境返回带示意标记的契约样例数据', async () => {
    const overview = await getClassOverview('class_mock_c01', '')

    expect('_fixture' in overview).toBe(true)
    expect(overview.summary.totalDurationSeconds).toEqual({
      state: 'known',
      value: 3540,
      algorithm: 'session_inference_v1',
    })
  })

  it('按 ?mock= 选择场景，error 场景抛契约错误体', async () => {
    await expect(getClassOverview('class_mock_c01', '?mock=error')).rejects.toThrow('未找到班级')
  })
})

describe('班级概览客户端（真实请求分支）', () => {
  it('请求契约端点并返回响应体', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(OK_BODY), { status: 200 })),
    )
    vi.stubGlobal('fetch', fetchMock)

    const overview = await requestClassOverview('class_mock_c01')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/analytics/classes/class_mock_c01/overview', {
      headers: { Accept: 'application/json' },
    })
    expect(overview.classId).toBe('class_mock_c01')
  })

  it('契约错误体：使用服务端 message 与 requestId', async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          code: 'CLASS_NOT_FOUND',
          message: '未找到班级',
          requestId: 'req_real_0001',
          details: {},
        }),
        { status: 404 },
      ),
    )

    const error = await requestClassOverview('class_mock_c01').catch((thrown: unknown) => thrown)

    expect(error).toBeInstanceOf(TeacherRequestError)
    expect((error as TeacherRequestError).message).toBe('未找到班级')
    expect((error as TeacherRequestError).requestId).toBe('req_real_0001')
  })

  it('非契约错误体（网关 HTML）：用兜底文案，不伪造 requestId', async () => {
    stubFetch(new Response('<html>502 Bad Gateway</html>', { status: 502 }))

    const error = (await requestClassOverview('class_mock_c01').catch(
      (thrown: unknown) => thrown,
    )) as TeacherRequestError

    expect(error.message).toBe('请求失败，请稍后重试')
    expect(error.requestId).toBeUndefined()
  })

  it('404 统一表述为「未找到」，不透露资源存在性', async () => {
    stubFetch(new Response('', { status: 404 }))

    const error = (await requestClassOverview('class_mock_c01').catch(
      (thrown: unknown) => thrown,
    )) as TeacherRequestError

    expect(error.message).toBe('未找到')
  })

  it('503 使用契约文案', async () => {
    stubFetch(new Response('', { status: 503 }))

    const error = (await requestClassOverview('class_mock_c01').catch(
      (thrown: unknown) => thrown,
    )) as TeacherRequestError

    expect(error.message).toBe('统计服务暂时不可用，请稍后重试')
  })

  it('请求未到达服务端时提示网络问题', async () => {
    stubFetch(new Error('connect ECONNREFUSED'))

    const error = (await requestClassOverview('class_mock_c01').catch(
      (thrown: unknown) => thrown,
    )) as TeacherRequestError

    expect(error.message).toBe('网络连接失败，请检查网络后重试')
    expect(error.requestId).toBeUndefined()
  })
})
