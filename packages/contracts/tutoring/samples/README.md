# 样例说明

手写样例，供 M2 / M4 / M5 对照实现、编写前端 Mock 与测试。
**均为人工构造的示意数据，不是真实模型输出，也不是已实现功能的证据。**

样例中的 `isMock` **演示的是该分支的取值，不代表样例自身的来源**。
样例全部是人工构造，没有运行时来源，因此谈不上「如实标注」

**消费方注意**：`isMock` 表达的是「这一轮回答是否由 `MockModelClient` 生成」
（`tutoring-response.md:77`），是**运行时来源**，不是「这个文件是不是假数据」。
若 M2 把本目录样例用作前端 fixture，**不要用 `isMock` 兼职表达「这是示意数据」**——
请在 fixture 层显式声明来源（例如加 `"_fixture": true`），由 Mock 层统一覆盖渲染。

否则会出这样的错：`05-sse-stream.txt` 变体三的 `isMock=false` 是为了演示
「不显示 Mock 标识」那条渲染路径，若把它当「非假数据」的标记，
示意数据就会被渲染成真实模型输出，违反 `AGENTS.md:8`。

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
M4 冻结正式枚举后，本目录所有样例需同步替换，**由 M3 负责**
（本目录由 M3 提供，见 [../README.md](../README.md) 开头），M2 / M4 不需要提 PR。
但改动仍按 `CONTRIBUTING.md:37` 走至少 2 名评审人的流程，并请 M4 评审。

样例中的 UUID 与会话标识均为示例，非真实数据。
课程内容使用公开的高等数学定义，不涉及任何真实课件或学生信息。
