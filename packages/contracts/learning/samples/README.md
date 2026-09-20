# Learning 契约样例

本目录是 [learning 契约](../) 的手写样例，供 M2 / M3 / M6 对照实现与编写 Mock。
样例**不是**真实数据，所有 ID、用户名、token 均为合成值。

| 文件 | 覆盖契约 | 场景 |
| --- | --- | --- |
| [01-courses-list.json](01-courses-list.json) | courses.md | 课程列表与章节列表响应 |
| [02-submission-single-choice.json](02-submission-single-choice.json) | homework.md | 单选题作业与提交（自动判分正确） |
| [03-submission-short-answer-pending.json](03-submission-short-answer-pending.json) | homework.md | 简答题作业与提交（待教师批阅） |
| [04-mistake-auto-from-wrong.json](04-mistake-auto-from-wrong.json) | mistakes.md | 错答自动收录 + 关联学习事件 |
| [05-mistake-manual.json](05-mistake-manual.json) | mistakes.md | 学生从答疑后主动标记 |
| [06-study-plan-from-tutoring.json](06-study-plan-from-tutoring.json) | study-plans.md | M3 建议转存的计划 + 站内提醒 |
| [07-learning-events-batch.json](07-learning-events-batch.json) | learning-events.md | 多种事件类型样例 |
| [errors.md](errors.md) | 全部 | 错误响应样例（404/409/422/403） |

## 使用约定

- 样例中所有 `requestId` 字段在真实环境由 M1 生成（code-standards.md:88）
- 所有 `userId` / `teacherId` / `studentId` 引用 M1 用户身份，M5 不存储姓名
- 样例标注 `isMock` 字段的地方表示该样例**本身**是 Mock 数据，
  实现侧在真实接口响应中**不应**添加 `isMock`（学习业务无 Mock 概念，
  Mock 标记只用于 M3 的 TutoringResponse，见 [tutoring-response.md](../../tutoring/tutoring-response.md) 第 77 行）
