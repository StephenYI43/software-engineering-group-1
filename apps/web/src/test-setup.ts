import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

/**
 * 测试环境准备。
 *
 * **这里必须有 `cleanup`。** `@testing-library/react` 的自动清理依赖全局
 * `afterEach`，而 Vitest 默认不开 `globals`，于是它注册不上——每个用例渲染的
 * DOM 会残留在 `document` 里累积到下个用例。
 *
 * 后果不是「测试少跑一点」，而是**测试变成假的**：查询会命中上一个用例的元素，
 * 出现 `Found multiple elements`，或者更糟——断言通过但验证的是别的用例的数据。
 * 所以这里显式注册，而不是打开 `globals: true` 去依赖隐式行为。
 */
afterEach(() => {
  cleanup()
})
