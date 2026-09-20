import { Link, Outlet } from 'react-router'

/**
 * 应用外壳。导航与 `<Outlet />` 是根路由挂载子路由的位置。
 */
export function AppLayout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/courses" className="app-header__brand">
          AI 学习助教
        </Link>
        <nav className="app-header__nav">
          <Link to="/courses">课程</Link>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
