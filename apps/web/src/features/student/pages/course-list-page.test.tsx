import { render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { CourseListPage } from './course-list-page'

function renderAt(search: string) {
  const router = createMemoryRouter([{ path: '/courses', element: <CourseListPage /> }], {
    initialEntries: [`/courses${search}`],
  })
  return render(<RouterProvider router={router} />)
}

describe('课程列表页', () => {
  it('正常场景渲染课程与学科展示名', async () => {
    renderAt('')
    await waitFor(() => {
      expect(screen.getByText('高等数学（上）')).toBeDefined()
    })
    // subject 枚举带展示名，页面不应显示原始值 math
    expect(document.body.textContent).toContain('学科：数学')
  })

  it('空列表走空态，不当作错误', async () => {
    renderAt('?mock=empty')
    await waitFor(() => {
      expect(screen.getByText('还没有课程')).toBeDefined()
    })
    // 空不是故障：不应出现错误提示
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('错误场景展示错误信息与问题编号', async () => {
    renderAt('?mock=error')
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
    })
    // 契约结构的错误体带 requestId，应当展示出来便于反馈
    expect(screen.getByRole('alert').textContent).toContain('问题编号')
  })
})
