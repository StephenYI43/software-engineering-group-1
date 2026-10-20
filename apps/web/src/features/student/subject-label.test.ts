import { describe, expect, it } from 'vitest'
import { subjectLabel } from './subject-label'

describe('学科展示名', () => {
  it('已知学科显示契约中的中文名称', () => {
    expect(subjectLabel('math')).toBe('数学')
  })

  it.each(['biology', '__proto__', 'toString', 'constructor'])(
    '未知学科 %s 返回原值字符串，供页面直接展示',
    (subject) => {
      const label = subjectLabel(subject)

      expect(label).toBeTypeOf('string')
      expect(label).toBe(subject)
    },
  )
})
