import type { Chapter, Course } from '../types'
import type { Fixture } from './tutoring-fixtures'

/**
 * 课程与章节示意数据。
 *
 * 字段形状取自 `packages/contracts/learning/courses.md`（已合并进 main），
 * 取值参照 `packages/contracts/learning/samples/01-courses-list.json`，
 * 但该样例把三类响应包在命名键下，而真实 API 直接返回响应体，
 * 所以这里按契约的**端点响应**结构组织，不照搬样例的包装层。
 *
 * `_fixture: true` 表示这是示意数据，见 `tutoring-fixtures.ts` 的说明。
 */

/* ------------------------------------------------------------ 分页响应包装 */

export type FixturePage<T> = Fixture<{
  items: Array<Fixture<T>>
  total: number
  page: number
  pageSize: number
}>

/* ------------------------------------------------------------------ 学习班 */

export const COURSE_MATH: Fixture<Course> = {
  _fixture: true,
  id: 'course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6',
  title: '高等数学（上）',
  description: '极限、连续、一元微积分',
  subject: 'math',
  coverImageUrl: null,
  teacherId: 'user_9a2f4c3d5e6f7a8b9c0d1e2f3a4b5c6d',
  teacherName: '王老师',
  studentCount: 32,
  chapterCount: 2,
  createdAt: '2026-09-10T08:00:00Z',
  updatedAt: '2026-09-14T10:30:00Z',
}

export const COURSE_LINEAR_ALGEBRA: Fixture<Course> = {
  _fixture: true,
  id: 'course_c1a0f3e8d7b6a5c4e3f2d1a0b9c8d7e6',
  title: '线性代数',
  description: '行列式、矩阵、向量空间',
  subject: 'math',
  coverImageUrl: null,
  teacherId: 'user_9a2f4c3d5e6f7a8b9c0d1e2f3a4b5c6d',
  teacherName: '王老师',
  studentCount: 28,
  chapterCount: 2,
  createdAt: '2026-09-10T08:10:00Z',
  updatedAt: '2026-09-12T09:00:00Z',
}

/** 全部课程。分页响应与按 id 查找都从这一份派生，避免两处数据漂移。 */
export const ALL_COURSES: Array<Fixture<Course>> = [COURSE_MATH, COURSE_LINEAR_ALGEBRA]

/** 课程列表（分页响应）。 */
export const COURSES_PAGE: FixturePage<Course> = {
  _fixture: true,
  items: ALL_COURSES,
  total: ALL_COURSES.length,
  page: 1,
  pageSize: 20,
}

/* -------------------------------------------------------------------- 章节 */

/** 按 courseId 索引的章节列表，各课程内按 `order` 升序。 */
export const CHAPTERS_BY_COURSE: Record<string, Chapter[]> = {
  [COURSE_MATH.id]: [
    {
      id: 'chapter_2c9e1a3b4d5c6e7f8a9b0c1d2e3f4a5b',
      courseId: COURSE_MATH.id,
      title: '第一章 极限与连续',
      order: 1,
      description: '数列极限、函数极限、连续性',
      documentId: 'doc_9a2f4c3d5e6f7a8b9c0d1e2f3a4b5c6d',
      createdAt: '2026-09-10T08:05:00Z',
      updatedAt: '2026-09-10T08:05:00Z',
    },
    {
      id: 'chapter_3d0f2b1a4c5d6e7f8a9b0c1d2e3f4a5b',
      courseId: COURSE_MATH.id,
      title: '第二章 导数与微分',
      order: 2,
      description: '导数定义、求导法则、微分',
      documentId: 'doc_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6',
      createdAt: '2026-09-10T08:06:00Z',
      updatedAt: '2026-09-10T08:06:00Z',
    },
  ],
  [COURSE_LINEAR_ALGEBRA.id]: [
    {
      id: 'chapter_4e1a3c2b5d6e7f8a9b0c1d2e3f4a5b6c',
      courseId: COURSE_LINEAR_ALGEBRA.id,
      title: '第一章 行列式',
      order: 1,
      description: '二阶与三阶行列式、行列式的性质',
      documentId: null,
      createdAt: '2026-09-10T08:15:00Z',
      updatedAt: '2026-09-10T08:15:00Z',
    },
    {
      id: 'chapter_5f2b4d3c6e7f8a9b0c1d2e3f4a5b6c7d',
      courseId: COURSE_LINEAR_ALGEBRA.id,
      title: '第二章 矩阵',
      order: 2,
      description: '矩阵运算、逆矩阵、初等变换',
      documentId: null,
      createdAt: '2026-09-10T08:16:00Z',
      updatedAt: '2026-09-10T08:16:00Z',
    },
  ],
}
