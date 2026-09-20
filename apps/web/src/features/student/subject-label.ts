/**
 * subject 展示名。取自 `packages/contracts/learning/courses.md` 的枚举表。
 *
 * 契约明确要求：**收到枚举外的值时回退展示原值字符串，不报错也不隐藏**。
 * 所以查找失败时返回原值，而不是显示「未知」或空白。
 *
 * 契约同时规定该枚举「由 M3 / M5 共同维护」，新增学科时这里会暂时失配——
 * 回退分支保证那时界面仍然可用，只是显示英文标识而已。
 */
const SUBJECT_LABEL: Record<string, string> = {
  math: '数学',
  physics: '物理',
  chemistry: '化学',
  english: '英语',
  cs: '计算机',
  other: '其他',
}

export function subjectLabel(subject: string): string {
  return SUBJECT_LABEL[subject] ?? subject
}
