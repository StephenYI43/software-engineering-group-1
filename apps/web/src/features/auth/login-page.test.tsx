import { StrictMode } from 'react'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { LoginPage } from './login-page'

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
  window.history.replaceState(null, '', '/')
})

function renderLogin(path: string) {
  const router = createMemoryRouter([{ path: '/login/:provider?', element: <LoginPage /> }], {
    initialEntries: [path],
  })
  render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  )
  return router
}

it('only shows login methods enabled by the API', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => Response.json({ methods: ['sms'] })),
  )
  renderLogin('/login')
  expect(await screen.findByRole('button', { name: '发送验证码' })).toBeDefined()
  expect(screen.queryByText('用户名与密码')).toBeNull()
  expect(screen.queryByText('使用GitHub登录')).toBeNull()
})

it('exchanges a callback exactly once and clears the code from the address', async () => {
  const path = '/login/github?code=oauth-code&state=oauth-state'
  window.history.replaceState(null, '', path)
  const exchange = vi.fn<(url: string, init: RequestInit) => Response>(() =>
    Response.json({
      token: 'api-session',
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
      user: { name: '测试学生', role: 'student' },
    }),
  )
  vi.stubGlobal('fetch', (url: string, init: RequestInit) =>
    url.endsWith('/exchange') ? exchange(url, init) : Response.json({ methods: ['github'] }),
  )
  const router = renderLogin(path)
  expect(await screen.findByText('已登录为 测试学生')).toBeDefined()
  expect(router.state.location.pathname).toBe('/login')
  expect(window.location.search).toBe('')
  expect(exchange).toHaveBeenCalledTimes(1)
  expect(exchange).toHaveBeenCalledWith(
    '/api/v1/auth/oauth/github/exchange',
    expect.objectContaining({
      body: JSON.stringify({ code: 'oauth-code', state: 'oauth-state' }),
    }),
  )
})
