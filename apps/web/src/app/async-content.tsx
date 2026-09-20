import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ErrorState, LoadingState } from '@pkg/ui'
import { ApiError } from '../features/student/api/http-client'

/**
 * 数据加载状态。
 *
 * 「空」不在这里——空态是**加载成功但数据为空**，属于 `ready` 分支，
 * 由各页面自行判断与渲染。把空态混进错误态会让「还没有数据」被渲染成故障。
 */
export type AsyncState<T> =
  { status: 'loading' } | { status: 'error'; error: ApiError } | { status: 'ready'; data: T }

/** 把任意抛出物归一成 ApiError，避免页面里出现 `unknown` 类型的错误处理分支。 */
export function toApiError(thrown: unknown): ApiError {
  if (thrown instanceof ApiError) return thrown
  return new ApiError({
    kind: 'unknown',
    status: null,
    message: '请求失败，请稍后重试',
    requestId: undefined,
    code: undefined,
  })
}

/**
 * 加载异步数据的通用 hook。
 *
 * `key` 变化时重新加载；组件卸载或 key 变化后到达的结果会被丢弃，
 * 避免把过期响应写回状态。
 */
export function useAsyncData<T>(key: string, load: () => Promise<T>): AsyncState<T> {
  const loadRef = useRef(load)
  loadRef.current = load

  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    loadRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data })
      })
      .catch((thrown: unknown) => {
        if (!cancelled) setState({ status: 'error', error: toApiError(thrown) })
      })
    return () => {
      cancelled = true
    }
  }, [key])

  return state
}

export type AsyncContentProps<T> = {
  state: AsyncState<T>
  children: (data: T) => ReactNode
}

/**
 * 按加载状态渲染。
 *
 * 集中在这里的原因：错误文案有硬约束——404 必须统一表述为「未找到」，
 * 不得出现「无权限」这类区分性文案（平台契约的防枚举要求）。写在一处才不会漏。
 * `requestId` 只在服务端真的返回时才展示，客户端不伪造。
 */
export function AsyncContent<T>({ state, children }: AsyncContentProps<T>) {
  if (state.status === 'loading') return <LoadingState />
  if (state.status === 'error') {
    return <ErrorState message={state.error.message} requestId={state.error.requestId} />
  }
  return <>{children(state.data)}</>
}
