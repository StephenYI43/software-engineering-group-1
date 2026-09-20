import { createBrowserRouter, Navigate } from 'react-router'
import { studentRoutes } from '../features/student/routes'
import { teacherRoutes } from '../features/teacher/routes'
import { AppLayout } from './app-layout'

/**
 * 应用级根路由。
 *
 * **组合式**：根 router 只把各 feature 导出的路由数组摊开，不硬编码任何具体页面。
 * 分工依据是 M1 在 Issue #11 的裁定——根路由由 M2 维护，M6 在
 * `features/teacher/` 内声明自己的路由，无需修改本文件。
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/courses" replace /> },
      ...studentRoutes,
      ...teacherRoutes,
    ],
  },
])
