import type { ReactNode } from 'react'

export type CardProps = {
  title?: ReactNode
  children: ReactNode
}

export function Card({ title, children }: CardProps) {
  return (
    <section className="ui-card">
      {title !== undefined && <h2 className="ui-card__title">{title}</h2>}
      <div className="ui-card__body">{children}</div>
    </section>
  )
}
