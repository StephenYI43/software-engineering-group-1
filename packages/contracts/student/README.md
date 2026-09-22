# Student 契约（M2 → M6）

本目录定义学生端（M2）产生、由学习数据与分析模块（M6）消费的公共契约。

状态：**草案 v1，待 M1 / M5 / M6 评审确认**。确认前不得据此实现生产写入。

## 文件

| 文件 | 内容 |
| --- | --- |
| [learning-events.md](learning-events.md) | 学生端学习事件的发布边界、schema、幂等与隐私规则 |
| [samples/](samples/) | 客户端意图与服务端规范事件的手写样例 |

## 上下游

| 方向 | 对端 | 内容 |
| --- | --- | --- |
| 输入 | M2 学生页面 | 经过鉴权 API 提交的最小行为意图；不接受客户端构造规范事件 |
| 输出 | M6 analytics | 追加到 `learning_events` 的规范事件 |
| 鉴权与归属 | M1 / M5 | 服务端身份、课程访问权、章节与课程归属 |

公共字段沿用 M5 的
[learning-events.md](../learning/learning-events.md)，消费语义沿用 M6 的
[event-consumption.md](../analytics/event-consumption.md)。本目录只定义 M2 作为生产方独有的事件。

## 变更流程

这是公共接口。变更需至少 2 名非作者评审，并包含相关领域负责人；当前至少需要
M1（平台/鉴权）、M5（学习域）与 M6（消费方）确认。
