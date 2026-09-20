export type LoadingStateProps = {
  message?: string
}

/**
 * 加载态。`aria-busy` 让屏幕阅读器知道该区域仍在加载，
 * 而不是读到一个空区域。
 */
export function LoadingState({ message = '加载中…' }: LoadingStateProps) {
  return (
    <div className="ui-state ui-state--loading" role="status" aria-busy="true">
      {message}
    </div>
  )
}
