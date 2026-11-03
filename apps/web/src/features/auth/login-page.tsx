import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { request } from '../student/api/http-client'

const authPath = '/api/v1/auth'
const sessionKey = 'learning-assistant-session'
const providerNames = { github: 'GitHub', wechat: '微信', school: '学校统一认证' } as const
type Provider = keyof typeof providerNames
type LoginMethod = Provider | 'password' | 'sms'
type Session = {
  token: string
  expiresAt: string
  user: { name: string; role: 'student' | 'teacher' | 'admin' }
}

function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(sessionKey)
    const session = raw ? (JSON.parse(raw) as Session) : null
    if (session && Date.parse(session.expiresAt) > Date.now()) return session
  } catch {
    // Missing browser storage is equivalent to having no restored session.
  }
  return null
}

function post<T>(path: string, body?: Record<string, string>): Promise<T> {
  return request<T>(authPath + path, {
    method: 'POST',
    ...(body && { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : '登录请求失败，请重试'
}

export function LoginPage() {
  const navigate = useNavigate()
  const { provider } = useParams()
  const [methods, setMethods] = useState<LoginMethod[]>([])
  const [session, setSession] = useState(readSession)
  const [busy, setBusy] = useState(Boolean(provider))
  const [message, setMessage] = useState('')
  const [phone, setPhone] = useState('')
  const callbackStarted = useRef(false)

  function saveSession(value: Session) {
    sessionStorage.setItem(sessionKey, JSON.stringify(value))
    setSession(value)
  }

  useEffect(() => {
    if (!provider) {
      void request<{ methods: LoginMethod[] }>(authPath + '/methods')
        .then((result) => setMethods(result.methods))
        .catch((error: unknown) => setMessage(describe(error)))
      return
    }
    if (callbackStarted.current) return
    callbackStarted.current = true
    const query = new URLSearchParams(window.location.search)
    window.history.replaceState(window.history.state, '', window.location.pathname)
    const code = query.get('code')
    const state = query.get('state')
    async function finish() {
      try {
        if (!provider || !Object.hasOwn(providerNames, provider) || !code || !state) {
          throw new Error('授权未完成，请重新登录')
        }
        saveSession(await post<Session>(`/oauth/${provider}/exchange`, { code, state }))
      } catch (error) {
        setMessage(describe(error))
      } finally {
        setBusy(false)
        void navigate('/login', { replace: true })
      }
    }
    void finish()
  }, [navigate, provider])

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setMessage('')
    try {
      await action()
    } catch (error) {
      setMessage(describe(error))
    } finally {
      setBusy(false)
    }
  }

  function submit(event: FormEvent<HTMLFormElement>, method: 'password' | 'sms') {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const get = (key: string) => {
      const value = fields.get(key)
      return typeof value === 'string' ? value : ''
    }
    void run(async () => {
      const value =
        method === 'password'
          ? await post<Session>('/login', { username: get('username'), password: get('password') })
          : await post<Session>('/sms/login', { phone, code: get('code') })
      saveSession(value)
    })
  }

  return (
    <section aria-labelledby="login-heading" aria-busy={busy}>
      <h1 id="login-heading">登录 AI 学习助教</h1>
      {message && <p role="status">{message}</p>}
      {session ? (
        <>
          <p>已登录为 {session.user.name}</p>
          <Link to="/courses">进入课程</Link>{' '}
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await request(authPath + '/logout', {
                  method: 'POST',
                  headers: { Authorization: `Bearer ${session.token}` },
                })
                sessionStorage.removeItem(sessionKey)
                setSession(null)
              })
            }
          >
            退出登录
          </button>
        </>
      ) : (
        <>
          {provider && <p>正在验证授权</p>}
          {methods.includes('password') && (
            <form onSubmit={(event) => submit(event, 'password')}>
              <h2>用户名与密码</h2>
              <label>
                用户名 <input name="username" autoComplete="username" required />
              </label>{' '}
              <label>
                密码{' '}
                <input name="password" type="password" autoComplete="current-password" required />
              </label>{' '}
              <button disabled={busy}>登录</button>
            </form>
          )}
          {methods.includes('sms') && (
            <form onSubmit={(event) => submit(event, 'sms')}>
              <h2>手机验证码</h2>
              <label>
                手机号（含区号）{' '}
                <input
                  type="tel"
                  autoComplete="tel"
                  placeholder="+86"
                  required
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </label>{' '}
              <button
                type="button"
                disabled={busy || !/^\+[1-9][0-9]{7,14}$/.test(phone)}
                onClick={() =>
                  void run(async () => {
                    await post('/sms/send', { phone })
                    setMessage('若手机号已绑定，请查收验证码')
                  })
                }
              >
                发送验证码
              </button>{' '}
              <label>
                验证码{' '}
                <input name="code" inputMode="numeric" autoComplete="one-time-code" required />
              </label>{' '}
              <button disabled={busy}>验证并登录</button>
            </form>
          )}
          {(Object.keys(providerNames) as Provider[])
            .filter((item) => methods.includes(item))
            .map((item) => (
              <button
                key={item}
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    const result = await post<{ authorizationUrl: string }>(`/oauth/${item}/start`)
                    const destination = new URL(result.authorizationUrl)
                    if (destination.protocol !== 'https:') throw new Error('登录地址无效')
                    window.location.assign(destination)
                  })
                }
              >
                使用{providerNames[item]}登录
              </button>
            ))}
        </>
      )}
    </section>
  )
}
