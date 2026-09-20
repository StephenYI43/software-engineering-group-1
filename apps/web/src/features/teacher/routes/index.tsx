import type { RouteObject } from 'react-router'
import { TeacherDashboardPage } from '../pages/teacher-dashboard-page'

/**
 * 教师端路由。
 *
 * **本目录归 M6**（`.github/CODEOWNERS`：`/apps/web/src/features/teacher/ @xk1024`）。
 * M2 在这里只留下挂载点，不实现任何教师端页面。
 *
 * M6 的接入方式：在本文件追加自己的路由对象即可，**不需要修改根 router**
 * （`src/app/router.tsx` 只做 `...teacherRoutes` 组合）。若确需改动根 router，
 * 按 `docs/team-plan.md:27` 先与 M2 确认。
 *
 * 已挂载：
 * - `teacher/dashboard` — 班级概览（S1），消费 M6 的统计契约
 *   `packages/contracts/analytics/statistics-api.md`
 *
 * 待挂载（S1 后续，依赖未就绪）：
 * - `teacher/courses` — 课件上传与解析进度：依赖 M3 的解析 API（202 + jobId，
 *   `docs/code-standards.md:81`）与 M5 的课程契约；接口未冻结前不实现，
 *   以免按猜测的字段写页面。
 */
export const teacherRoutes: RouteObject[] = [
  { path: 'teacher/dashboard', element: <TeacherDashboardPage /> },
]