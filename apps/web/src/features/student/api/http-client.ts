import type { ApiErrorBody } from '../types'

/**
 * 面向用户的错误语义分类。
 *
 * 依据是 M1 在 Issue #11 给定的 HTTP 语义映射：错误契约冻结前，前端只按 HTTP
 * 语义做基础处理，不猜测具体业务 `code`。
 */
export type ApiErrorKind =
  | 'unauthorized' // 401 未登录 / 会话失效
  | 'forbidden' // 403 角色级禁止操作
  | 'notFound' // 404 未找到（不区分「不存在」与「存在但无权访问」）
  | 'validation' // 422 输入校验失败
  | 'rateLimited' // 429 限流
  | 'server' // 5xx 服务异常
  | 'network' // 请求未到达服务端
  | 'unknown' // 其他

/**
 * 按 kind 的兜底文案。
 *
 * 两处刻意的措辞约束：
 * - `notFound` 一律「未找到」。平台契约要求 404 防枚举，**不得**出现「无权限」
 *   这类区分性文案，否则会把「存在但无权」暴露给用户。
 * - `forbidden` 才允许表达角色级禁止——它不含资源存在性信息。
 */
const FALLBACK_MESSAGE: Record<ApiErrorKind, string> = {
  unauthorized: '登录状态已失效，请重新登录',
  forbidden: '当前账号无权执行该操作',
  notFound: '未找到',
  validation: '提交的内容有误，请检查后重试',
  rateLimited: '操作过于频繁，请稍后重试',
  server: '服务暂时不可用，请稍后重试',
  network: '网络连接失败，请检查网络后重试',
  unknown: '请求失败，请稍后重试',
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  /** HTTP 状态码；请求未到达服务端时为 null。 */
  readonly status: number | null
  /**
   * 服务端返回的 requestId，用于问题反馈。
   * **客户端不自行伪造**：服务端没给就是 undefined。
   */
  readonly requestId: string | undefined
  /** 服务端返回的业务错误码；错误体不符合契约结构时为 undefined。 */
  readonly code: string | undefined

  constructor(init: {
    kind: ApiErrorKind
    status: number | null
    message: string
    requestId?: string | undefined
    code?: string | undefined
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.kind = init.kind
    this.status = init.status
    this.requestId = init.requestId
    this.code = init.code
  }
}

function kindFromStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'notFound'
  if (status === 422) return 'validation'
  if (status === 429) return 'rateLimited'
  if (status >= 500) return 'server'
  return 'unknown'
}

/**
 * 尝试把响应体读成契约规定的错误结构。
 *
 * 平台的统一错误封装尚未实现（packages/contracts/platform/README.md:14
 * 「客户端暂勿假定所有错误已经符合下方草案」），所以不符合结构是预期内的情况：
 * 此时返回 null，由调用方走兜底文案。
 *
 * 不符合结构时**不解析内部结构**——不猜字段、不把任意文本当 message 展示。
 */
function parseErrorBody(raw: unknown): ApiErrorBody | null {
  if (typeof raw !== 'object' || raw === null) return null
  const obj = raw as Record<string, unknown>
  if (typeof obj.code !== 'string' || typeof obj.message !== 'string') return null
  if (typeof obj.requestId !== 'string') return null
  const details = obj.details
  return {
    code: obj.code,
    message: obj.message,
    requestId: obj.requestId,
    details:
      typeof details === 'object' && details !== null ? (details as Record<string, unknown>) : {},
  }
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    // 代理、网关或 HTML 错误页会返回非 JSON。这里不是异常路径，是预期内的情况。
    return null
  }
}

/**
 * 统一的请求入口。所有对外请求都应经过它，以取得一致的错误语义。
 */
export async function request<T>(input: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(input, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    // fetch 抛错 = 请求根本没发出去或连接中断，与服务端返回的错误不同类。
    throw new ApiError({ kind: 'network', status: null, message: FALLBACK_MESSAGE.network })
  }

  if (response.ok) {
    return (await readJsonSafely(response)) as T
  }

  const kind = kindFromStatus(response.status)
  const body = parseErrorBody(await readJsonSafely(response))

  throw new ApiError({
    kind,
    status: response.status,
    // 契约结构可用时优先用服务端文案；否则用兜底文案。
    message: body?.message ?? FALLBACK_MESSAGE[kind],
    requestId: body?.requestId,
    code: body?.code,
  })
}
