import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary'

export type ButtonProps = {
  variant?: ButtonVariant
  children: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'ui-button ui-button--primary',
  secondary: 'ui-button ui-button--secondary',
}

/**
 * 基础按钮。使用原生 <button>，键盘可达性与焦点行为由浏览器提供，
 * 不自行实现键盘处理。
 */
export function Button({ variant = 'primary', children, ...rest }: ButtonProps) {
  return (
    <button className={VARIANT_CLASS[variant]} {...rest}>
      {children}
    </button>
  )
}
