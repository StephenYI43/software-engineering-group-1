import { render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TutoringPage } from './tutoring-page'

/**
 * 场景通过 **router 的 location** 注入，而不是 `window.location`——
 * `createMemoryRouter` 有自己的 history，不改 `window`。页面读的是
 * `useLocation().search`，所以这里传 `initialEntries` 即可生效。
 */
function renderAt(search: string) {
  const router = createMemoryRouter([{ path: '/tutoring/:sessionId', element: <TutoringPage /> }], {
    initialEntries: [`/tutoring/sess_4b8d1e02${search}`],
  })
  return render(<RouterProvider router={router} />)
}

describe('答疑页', () => {
  it('有依据时渲染引用，且引用含文件名与页码', async () => {
    renderAt('?turn=thought')
    await waitFor(() => {
      expect(screen.getByTestId('citations')).toBeDefined()
    })
    expect(screen.getByTestId('citations').textContent).toContain('高等数学-上册-第1章.pdf')
    expect(screen.getByTestId('citations').textContent).toContain('第 12 页')
    expect(screen.queryByTestId('no-evidence')).toBeNull()
  })

  it('hasEvidence=false 时不渲染引用区，也不显示占位引用', async () => {
    renderAt('?turn=noEvidence')
    await waitFor(() => {
      expect(screen.getByTestId('no-evidence')).toBeDefined()
    })
    // 契约不变量：hasEvidence=false ⟺ citations 为空数组，不得展示任何引用
    expect(screen.queryByTestId('citations')).toBeNull()
  })

  it('始终展示「示意数据」标识（AGENTS.md:8）', async () => {
    renderAt('?turn=thought')
    await waitFor(() => {
      expect(screen.getByTestId('answer-content')).toBeDefined()
    })
    expect(document.body.textContent).toContain('示意数据')
  })

  it('isMock 作为运行时来源单独标注，不与「示意数据」混为一谈', async () => {
    renderAt('?turn=thought')
    await waitFor(() => {
      expect(screen.getByTestId('runtime-source')).toBeDefined()
    })
    expect(screen.getByTestId('runtime-source').textContent).toContain('离线假模型')
  })

  it('阶段标签用「思路」而非「思考过程」——thought 不是模型内部推理', async () => {
    renderAt('?turn=thought')
    await waitFor(() => {
      expect(screen.getByTestId('stage')).toBeDefined()
    })
    expect(screen.getByTestId('stage').textContent).toBe('当前阶段：思路')
  })

  it('错误态展示错误信息，且不渲染任何回答内容', async () => {
    renderAt('?turn=thought&mock=error')
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
    })
    // 关键：错误时绝不能显示半截或伪造的回答
    expect(screen.queryByTestId('answer-content')).toBeNull()
    expect(screen.queryByTestId('citations')).toBeNull()
  })

  it('非契约结构的错误走兜底文案，且不展示问题编号', async () => {
    renderAt('?turn=thought&mock=error-raw')
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
    })
    expect(screen.getByRole('alert').textContent).toContain('服务暂时不可用')
    // 客户端不伪造 requestId，拿不到就不渲染「问题编号」
    expect(screen.getByRole('alert').textContent).not.toContain('问题编号')
  })
})
