import { render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TeacherDashboardPage } from './teacher-dashboard-page'

function renderAt(search: string) {
  const router = createMemoryRouter(
    [{ path: '/teacher/dashboard', element: <TeacherDashboardPage /> }],
    {
      initialEntries: [`/teacher/dashboard${search}`],
    },
  )
  return render(<RouterProvider router={router} />)
}

describe('教师端班级概览页', () => {
  it('正常场景渲染汇总、口径、覆盖率与示意数据标记', async () => {
    renderAt('')
    await waitFor(() => {
      expect(screen.getByText('班级学习时长')).toBeDefined()
    })

    const text = document.body.textContent ?? ''
    expect(text).toContain('59 分钟') // 3540 秒
    expect(text).toContain('2 人')
    expect(text).toContain('3 次')
    expect(text).toContain('3 名学生中 2 名有数据')
    // 时长口径必须可见，避免把过渡口径当成测量值
    expect(text).toContain('会话推断口径')
    // 示意数据必须有显式标识
    expect(screen.getByRole('note').textContent).toContain('示意数据')
  })

  it('无事件的学生时长显示「暂无数据」，不显示 0', async () => {
    renderAt('')
    await waitFor(() => {
      expect(screen.getByText('班级学习时长')).toBeDefined()
    })

    expect(screen.getByText('合成学生 03')).toBeDefined()
    expect(screen.getAllByText('暂无数据').length).toBeGreaterThan(0)
    // 未知不得被渲染成 0（`docs/tasks/m6.md:29` 验收）；时长缺乏观测，
    // 必须显示「暂无数据」。提交数是已知 0，如实显示「0 次」（无活动 ≠ 未知）。
    expect(document.body.textContent ?? '').not.toContain('0 分钟')
    const s03Row = screen
      .getAllByRole('row')
      .find((row) => row.textContent?.includes('合成学生 03'))
    expect(s03Row?.textContent).toContain('0 次')
    expect(s03Row?.textContent).toContain('暂无数据')
  })

  it('区分「无数据」与「本周期无错题」两种不同结论', async () => {
    renderAt('')
    await waitFor(() => {
      expect(screen.getByText('班级学习时长')).toBeDefined()
    })

    // s02 有数据但没有错题：显示「本周期无错题」，而不是「暂无数据」
    const rows = screen.getAllByRole('row')
    const s02Row = rows.find((row) => row.textContent?.includes('合成学生 02'))
    expect(s02Row?.textContent).toContain('本周期无错题')

    const s03Row = rows.find((row) => row.textContent?.includes('合成学生 03'))
    expect(s03Row?.textContent).toContain('暂无数据')
  })

  it('样本不足的薄弱点条目给出显式提示', async () => {
    renderAt('')
    await waitFor(() => {
      expect(screen.getByText('答题薄弱点')).toBeDefined()
    })

    // 题型 2 条 + 章节 1 条，三条样本量都低于 MIN_SAMPLE_SIZE，必须逐条提示
    expect(screen.getAllByText('样本不足，不足以据此下结论').length).toBe(3)
    expect(document.body.textContent ?? '').toContain('样本 2')
  })

  it('全班无活动场景：计数如实显示 0，时长为「暂无数据」', async () => {
    renderAt('?mock=no-data')
    await waitFor(() => {
      expect(screen.getByText('班级学习时长')).toBeDefined()
    })

    const text = document.body.textContent ?? ''
    // 计数类指标是已知 0（无活动 ≠ 不可判断），必须如实显示
    expect(text).toContain('0 人')
    expect(text).toContain('0 次')
    // 时长缺乏观测依据，显示「暂无数据」而不是 0
    expect(screen.getAllByText('暂无数据').length).toBeGreaterThan(3)
    expect(text).not.toContain('0 分钟')
    expect(text).toContain('本周期未纳入任何学习事件')
  })

  it('错误场景展示错误信息与问题编号', async () => {
    renderAt('?mock=error')
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
    })

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('未找到班级')
    expect(alert.textContent).toContain('问题编号：req_mock_9001')
  })
})
