import type { RouteObject } from 'react-router'

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
 * 示例：
 * ```tsx
 * { path: 'teacher/courses', element: <TeacherCourseListPage /> }
 * ```
 */
export const teacherRoutes: RouteObject[] = []
