import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TutoringPage } from './tutoring-page'
import { createTutoringClient, type TutoringClient } from '../api/tutoring-client'
import {
  answer,
  completed,
  controlledResponse,
  delta,
  frame,
  started,
  streamResponse,
} from '../api/tutoring-test-utils'

/**
 * 场景通过 **router 的 location** 注入，而不是 `window.location`——
 * `createMemoryRouter` 有自己的 history，不改 `window`。页面读的是
 * `useLocation().search`，所以这里传 `initialEntries` 即可生效。
 */
function renderAt(search: string, client?: TutoringClient) {
  const router = createMemoryRouter(
    [{ path: '/tutoring/:sessionId', element: <TutoringPage client={client} /> }],
    {
      initialEntries: [`/tutoring/sess_4b8d1e02${search}`],
    },
  )
  const view = render(<RouterProvider router={router} />)
  fireEvent.change(screen.getByLabelText('问题'), { target: { value: '函数的极限是什么？' } })
  fireEvent.click(screen.getByRole('button', { name: '发送' }))
  return { ...view, router }
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

describe('流式页面交互', () => {
  it('增量只显示未完成正文，终帧确认后才展示引用与追问', async () => {
    const source = controlledResponse()
    renderAt('', createTutoringClient({ fetch: () => Promise.resolve(source.response) }))
    source.send('started', started)
    source.send('delta', delta)
    await waitFor(() =>
      expect(screen.getByTestId('partial-answer').textContent).toContain('临时正文'),
    )
    expect(screen.getByTestId('stage').textContent).toContain('思路')
    expect(screen.queryByTestId('citations')).toBeNull()
    expect(screen.queryByTestId('answer-content')).toBeNull()
    expect(screen.getByRole('button', { name: '发送' }).hasAttribute('disabled')).toBe(true)
    source.send('completed', { ...completed, response: answer({ sessionId: 'sess_4b8d1e02' }) })
    source.close()
    await waitFor(() => expect(screen.getByTestId('answer-content').textContent).toBe('最终回答'))
    expect(screen.getByTestId('citations').textContent).toContain('合成课件.pdf')
  })

  it('停止后保留半截文字并显示未完成，不显示完整回答', async () => {
    const source = controlledResponse()
    const fetch: typeof globalThis.fetch = (input) => {
      if (typeof input !== 'string') throw new Error('expected URL string')
      return Promise.resolve(
        input.endsWith('/stop') ? new Response(null, { status: 204 }) : source.response,
      )
    }
    renderAt('', createTutoringClient({ fetch }))
    source.send('started', started)
    source.send('delta', delta)
    await waitFor(() =>
      expect(screen.getByTestId('partial-answer').textContent).toContain('临时正文'),
    )
    fireEvent.click(screen.getByRole('button', { name: '停止' }))
    expect(source.cancelled).toBe(false)
    source.send('stopped', {
      seq: 3,
      turnId: 'turn_test_1',
      isComplete: false,
      reason: 'client_stop',
    })
    source.close()
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('已停止，本轮未完成'),
    )
    expect(screen.getByTestId('partial-answer').textContent).toContain('临时正文')
    expect(screen.queryByTestId('citations')).toBeNull()
    expect(screen.queryByTestId('answer-content')).toBeNull()
    expect(screen.getByRole('button', { name: '重试本轮' })).toBeDefined()
  })

  it('错误后重试新建请求，恢复完整回答', async () => {
    let attempts = 0
    const fetch: typeof globalThis.fetch = () => {
      attempts += 1
      return Promise.resolve(
        attempts === 1
          ? streamResponse([frame('started', started), frame('delta', delta)])
          : streamResponse([
              frame('started', { ...started, turnId: 'turn_retry' }),
              frame('completed', {
                seq: 2,
                turnId: 'turn_retry',
                isComplete: true,
                response: answer({ sessionId: 'sess_4b8d1e02', turnId: 'turn_retry' }),
              }),
            ]),
      )
    }
    renderAt('', createTutoringClient({ fetch }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: '重试本轮' }))
    await waitFor(() => expect(screen.getByTestId('answer-content').textContent).toBe('最终回答'))
    expect(attempts).toBe(2)
  })

  it('路由变化取消旧流并清空旧轮显示', async () => {
    const source = controlledResponse()
    const { router } = renderAt(
      '',
      createTutoringClient({ fetch: () => Promise.resolve(source.response) }),
    )
    source.send('started', started)
    source.send('delta', delta)
    await waitFor(() => expect(screen.getByTestId('partial-answer')).toBeDefined())
    await act(() => router.navigate('/tutoring/session_other'))
    expect(source.cancelled).toBe(true)
    expect(screen.queryByTestId('partial-answer')).toBeNull()
    expect(screen.queryByTestId('stage')).toBeNull()
  })

  it('组件卸载释放正在读取的流', async () => {
    const source = controlledResponse()
    const { unmount } = renderAt(
      '',
      createTutoringClient({ fetch: () => Promise.resolve(source.response) }),
    )
    source.send('started', started)
    await waitFor(() => expect(screen.getByTestId('stage')).toBeDefined())
    unmount()
    expect(source.cancelled).toBe(true)
  })
})
