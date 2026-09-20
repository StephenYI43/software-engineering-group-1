import type { ClassOverview } from '../types'

/**
 * 班级概览客户端（M6 → M2 契约的消费方）。
 *
 * 端点是 M6 自己的契约：`packages/contracts/analytics/statistics-api.md`（PR #37）——
 * `GET /api/v1/analytics/classes/{classId}/overview`。
 * 后端实现在 `apps/api/app/domains/analytics`（PR #38），**路由挂载由 M1 在
 * app factory 完成**；在那之前生产环境会走到明确的错误态，不显示任何伪造数字。
 */

const OVERVIEW_PATH = '/api/v1/analytics/classes'

/** 按 HTTP 状态给出的兜底文案；服务端给了 message 时以服务端为准。 */
const FALLBACK_MESSAGE: Record<number, string> = {
  401: '登录状态已失效，请重新登录',
  // 404 统一表述为「未找到」：平台契约要求不区分「不存在」与「存在但无权访问」。
  404: '未找到',
  422: '统计周期参数不合法',
  503: '统计服务暂时不可用，请稍后重试',
}

/**
 * 教师端请求错误。
 *
 * 刻意不复用 `features/student/api/http-client`：那是学生端的 feature 内部模块，
 * 跨 feature import 会让教师端依赖学生端的实现（该耦合已在 PR #36 评审中提出，
 * 建议 M2 把它提到 `src/app` 共享层；届时本类可删除并改为复用）。
 */
export class TeacherRequestError extends Error {
  readonly requestId: string | undefined

  constructor(message: string, requestId?: string) {
    super(message)
    this.name = 'TeacherRequestError'
    this.requestId = requestId
  }
}

/**
 * 读取班级概览。
 *
 * `demoSearch` 只在开发环境用于选择示意场景（`?mock=`）；生产分支忽略它，
 * 也**不会**把示意数据打进产物——示意数据经由 `import.meta.env.DEV` 守卫的
 * 动态 import 加载，生产构建会连同该分支一起剥离。
 */
export async function getClassOverview(
  classId: string,
  demoSearch: string,
): Promise<ClassOverview> {
  if (import.meta.env.DEV) {
    const mocks = await import('../mocks')
    try {
      return await mocks.fetchClassOverview(mocks.parseMockScenario(demoSearch))
    } catch (thrown: unknown) {
      // 示意数据抛的是契约错误体，必须归一成页面认识的错误类型，
      // 否则真实响应里能看到的 message / requestId 在演示时会被吞掉。
      if (thrown instanceof mocks.MockContractError) {
        throw new TeacherRequestError(thrown.body.message, thrown.body.requestId)
      }
      throw thrown
    }
  }
  return requestClassOverview(classId)
}

/** 真实请求分支（生产构建使用）。 */
export async function requestClassOverview(classId: string): Promise<ClassOverview> {
  const url = `${OVERVIEW_PATH}/${encodeURIComponent(classId)}/overview`

  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new TeacherRequestError('网络连接失败，请检查网络后重试')
  }

  if (!response.ok) {
    const body = await readContractError(response)
    throw new TeacherRequestError(
      body?.message ?? FALLBACK_MESSAGE[response.status] ?? '请求失败，请稍后重试',
      body?.requestId,
    )
  }

  return (await response.json()) as ClassOverview
}

type ContractErrorBody = {
  code: string
  message: string
  requestId: string | undefined
  details: Record<string, unknown>
}

/**
 * 解析契约错误体；不符合契约结构（代理或网关的 HTML 错误页）时返回 null，
 * 由调用方使用兜底文案，**不伪造 requestId**。
 */
async function readContractError(response: Response): Promise<ContractErrorBody | null> {
  try {
    const parsed: unknown = await response.json()
    if (typeof parsed !== 'object' || parsed === null) return null
    const body = parsed as Partial<ContractErrorBody>
    if (typeof body.message !== 'string') return null
    return {
      code: typeof body.code === 'string' ? body.code : 'UNKNOWN',
      message: body.message,
      requestId: typeof body.requestId === 'string' ? body.requestId : undefined,
      details: typeof body.details === 'object' && body.details !== null ? body.details : {},
    }
  } catch {
    return null
  }
}
