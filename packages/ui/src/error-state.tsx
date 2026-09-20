import type { ReactNode } from 'react'

export type ErrorStateProps = {
  /** 面向用户的错误说明。不得包含堆栈、内部字段或凭证。 */
  message: string
  /**
   * 服务端返回的 requestId，用于问题反馈。
   * 客户端**不得**自行伪造；没有可用值时不渲染。
   */
  requestId?: string | undefined
  action?: ReactNode
}

/**
 * 错误态。
 *
 * 注意：不要把「未找到」以外的语义写进 message——平台契约要求 404 统一表述为
 * 「未找到」，不得区分「不存在」与「存在但无权访问」（防枚举）。
 */
export function ErrorState({ message, requestId, action }: ErrorStateProps) {
  return (
    <div className="ui-state ui-state--error" role="alert">
      <p className="ui-state__title">{message}</p>
      {requestId !== undefined && requestId !== '' && (
        <p className="ui-state__meta">问题编号：{requestId}</p>
      )}
      {action !== undefined && <div className="ui-state__action">{action}</div>}
    </div>
  )
}
