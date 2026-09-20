import type { RouteObject } from 'react-router'
import { CourseDetailPage } from '../pages/course-detail-page'
import { CourseListPage } from '../pages/course-list-page'
import { TutoringPage } from '../pages/tutoring-page'

/**
 * 学生端路由。
 *
 * 只导出路由声明，**不构造自己的 router**——根 router（`src/app/router.tsx`）
 * 负责组合各 feature 导出的路由。这样 M6 挂教师端路由时不需要修改根 router 文件。
 */
export const studentRoutes: RouteObject[] = [
  { path: 'courses', element: <CourseListPage /> },
  { path: 'courses/:courseId', element: <CourseDetailPage /> },
  { path: 'tutoring/:sessionId', element: <TutoringPage /> },
]
