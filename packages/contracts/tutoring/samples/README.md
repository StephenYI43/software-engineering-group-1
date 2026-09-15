# 样例说明

手写样例，供 M2 / M4 / M5 对照实现、编写前端 Mock 与测试。
**均为人工构造的示意数据，不是真实模型输出，也不是已实现功能的证据。**

所有样例的 `isMock` 字段按实际来源如实标注；若 M2 的 Mock 数据取自本目录，
**必须在界面上标明这是示意数据**（`AGENTS.md:8`）。

| 文件 | 场景 |
| --- | --- |
| [01-thought-with-citation.json](01-thought-with-citation.json) | 首轮回答，`thought` 阶段，带页码引用 |
| [02-summary-after-attempt.json](02-summary-after-attempt.json) | 学生尝试后，`summary` 阶段给出教学解释 |
| [03-no-evidence.json](03-no-evidence.json) | 检索不到依据，明确说明且不编造引用 |
| [04-error-model-output-invalid.json](04-error-model-output-invalid.json) | 模型输出未通过校验的错误响应 |
| [05-sse-stream.txt](05-sse-stream.txt) | 一次完整的 SSE 事件流（三个变体） |

## 注意事项

**`emotion` / `action` 的取值是占位值。**
凡例见 [../README.md](../README.md) 的「仍待团队拍板」第 1 条。
M4 冻结正式枚举后，本目录所有样例需同步替换。

样例中的 UUID 与会话标识均为示例，非真实数据。
课程内容使用公开的高等数学定义，不涉及任何真实课件或学生信息。
