import type { ReactNode } from 'react'

export type EmptyStateProps = {
  title: string
  description?: string
  action?: ReactNode
}

/**
 * 空态。「没有数据」是正常状态，不是错误——不要用错误文案渲染它。
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="ui-state ui-state--empty">
      <p className="ui-state__title">{title}</p>
      {description !== undefined && <p className="ui-state__description">{description}</p>}
      {action !== undefined && <div className="ui-state__action">{action}</div>}
    </div>
  )
}
