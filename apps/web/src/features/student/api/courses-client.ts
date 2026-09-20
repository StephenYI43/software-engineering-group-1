import type { Chapter, Course, Paginated } from '../types'
import type { Fixture } from '../mocks/tutoring-fixtures'
import type { MockScenario } from '../mocks'
import {
  fetchChapters as mockFetchChapters,
  fetchCourse as mockFetchCourse,
  fetchCourses as mockFetchCourses,
} from '../mocks'

/**
 * 课程与章节的数据入口。
 *
 * **S0 阶段全部走 Mock。** 这一层是页面与数据来源之间的唯一边界：接入真实后端时
 * 只改本文件，页面不动。
 *
 * 真实端点（`packages/contracts/learning/courses.md`，已合并进 main）：
 * - `GET /api/v1/courses`                      分页参数 page / pageSize / subject / q
 * - `GET /api/v1/courses/{courseId}`           越权返回 404 防枚举
 * - `GET /api/v1/courses/{courseId}/chapters`  分页，按 order 升序
 *
 * 接入时改用 `request()`（`./http-client`）发起请求——错误语义映射与兜底分支
 * 已经在那里统一处理，页面无需感知。届时 `scenario` 参数随 Mock 层一起移除。
 */

export function getCourses(scenario: MockScenario): Promise<Fixture<Paginated<Course>>> {
  return mockFetchCourses(scenario)
}

export function getCourse(courseId: string, scenario: MockScenario): Promise<Fixture<Course>> {
  return mockFetchCourse(courseId, scenario)
}

export function getChapters(
  courseId: string,
  scenario: MockScenario,
): Promise<Fixture<Paginated<Chapter>>> {
  return mockFetchChapters(courseId, scenario)
}
