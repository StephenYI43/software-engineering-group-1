import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

/**
 * 测试环境准备。与 apps/web/src/test-setup.ts 同一约定：
 * Vitest 默认不开 globals，`@testing-library/react` 的自动清理注册不上，
 * 必须显式注册，否则上个用例的 DOM 残留会让后续断言命中错误元素。
 */
afterEach(() => {
  cleanup()
})
