# 六人分工与交付计划

项目：大学生辅助学习 AI 数字人系统。以下账号分工由组长于 2026-09-15 确认，六人均已具有仓库写入权限，模块任务已设置对应 Assignee。每人对自己模块的接口、测试与文档负责。

## GitHub 账号映射

| 角色 | GitHub 账号 | 模块任务 | 交叉评审人 |
| --- | --- | --- | --- |
| M1 | @StephenYI43 | [#2](https://github.com/StephenYI43/software-engineering-group-1/issues/2) | @xk1024 |
| M2 | @Saber-www | [#3](https://github.com/StephenYI43/software-engineering-group-1/issues/3) | @haoxuanluo351-lgtm |
| M3 | @ljt2293977194-dotcom | [#4](https://github.com/StephenYI43/software-engineering-group-1/issues/4) | @Jiege123-CMYK |
| M4 | @haoxuanluo351-lgtm | [#5](https://github.com/StephenYI43/software-engineering-group-1/issues/5) | @Saber-www |
| M5 | @Jiege123-CMYK | [#6](https://github.com/StephenYI43/software-engineering-group-1/issues/6) | @ljt2293977194-dotcom |
| M6 | @xk1024 | [#7](https://github.com/StephenYI43/software-engineering-group-1/issues/7) | @StephenYI43 |

## 职责与边界

| 成员 | 主责 | 负责目录（计划） | 主要交付物 | 固定交叉评审 |
| --- | --- | --- | --- | --- |
| M1 | 架构、账号权限、集成与部署 | apps/api/app/core、infra、.github/workflows | 脚手架、角色鉴权、开发环境、CI、集成演示 | M6 |
| M2 | 学生端与通用交互 | apps/web/src/features/student、packages/ui | 课程页、流式聊天、作业/错题/计划页面、学生端测试 | M4 |
| M3 | AI 答疑、RAG、导学 | apps/api/app/domains/tutoring、apps/api/app/domains/knowledge、ai | 文档解析检索、引导式答疑、结构化生成、评测集 | M5 |
| M4 | 数字人、语音与课堂媒体 | packages/avatar、apps/api/app/domains/media | 形象与动作、ASR/TTS、专注计时、录音转写与降级 | M2 |
| M5 | 学习业务后端 | apps/api/app/domains/learning、apps/api/migrations | 课程、作业、错题、计划、提醒、备考业务 API | M3 |
| M6 | 教师端与学习数据 | apps/web/src/features/teacher、apps/api/app/domains/analytics | 知识库管理入口、班级看板、统计/掌握度/周月报 | M1 |

共享路由、锁文件、接口契约由提交者先通知相关负责人。M1 负责协调公共入口，不承担所有人的业务补漏。数据库迁移由各表负责人编写，M5 协调迁移顺序，M1 检查可部署性。

M2 负责页面布局与数据展示，M4 提供独立数字人组件；M6 自行实现教师端，不把所有 UI 工作交给 M2。M3 生成计划建议，M5 校验后保存；M6 从学习事件聚合统计，不改动其他领域数据。首版采用模块化单体，共用数据库但按领域划分表和访问层，不拆六套微服务。

## 十大需求归属

| 需求 | 主责 | 协作 |
| --- | --- | --- |
| 数字人学习陪伴 | M4 | M2、M3 |
| 课程知识智能导学 | M3 | M5、M2 |
| AI 智能答疑 | M3 | M2、M4 |
| 作业与习题辅导 | M5 | M3、M2、M6 |
| 预习与复习规划 | M5 | M3、M2 |
| 课堂辅助 | M4 | M3、M2 |
| 备考冲刺 | M5 | M3、M2 |
| 学习数据与成长报告 | M6 | M5、M2 |
| 多学科适配 | M3 | M5、M6 |
| 教师/管理后台 | M6 | M1、M5 |

## 建议四次迭代

每次建议一周，属于工作拆分假设，不是已承诺日期；第一周结束按实际完成量调整。

| 迭代 | 共同目标 | 各成员可交付结果 |
| --- | --- | --- |
| S0 | 契约与环境 | M1 环境/认证；M2 页面骨架；M3 答疑 schema/样例；M4 数字人组件接口；M5 表模型/API；M6 学习事件/教师原型 |
| S1 | 最小文字学习闭环 | M1 权限联调；M2 文字聊天/课程页；M3 单门课 PDF 检索答疑；M4 2D 形象与播报；M5 作业/错题/计划；M6 课件上传/基础统计 |
| S2 | 多模态和学习增强 | M1 稳定性；M2 图片与计划交互；M3 OCR/同类题/PPTX；M4 ASR/录音转写；M5 提醒/复习规则；M6 雷达图/周报 |
| S3 | 全链路演示与扩展准备 | 全员修复回归；验证权限、失败降级、核心 AI 评测；整理部署和演示材料 |

## 第一阶段共同验收

使用合成学生账号和一门高数示范课程，完成：教师上传 PDF → 查看解析状态 → 学生选章节并提问 → 引导式答疑显示可定位引用 → 数字人播报 → 经学生确认将错题收录 → 生成并保存复习计划 → 教师看到授权班级统计。

只有用户提交错误答案或明确标记错题时才收录；不能把所有问题默认当错题。课堂录音和 PPTX 属于 S2 增量，不阻塞 S1 文字链路。

每人至少交付一个正常场景、一个失败场景、一项权限/边界测试和可复现演示证据。集成演示轮流主持，M1 维护集成环境。某人落后时按可独立验收的子任务转交，更新 Issue 负责人，避免多人同时改同一文件。

## 首日开工

1. 账号和模块任务 Assignee 已配置；每人核对本表后在自己的 Issue 更新首次工作计划。
2. 阅读 CONTRIBUTING、代码规范与 AGENTS；AI 开发工具不自动读取 AGENTS 时手工附上。
3. 各自把模块任务拆成 0.5—2 天的小 Issue，声明受影响目录。
4. M1/M3/M4/M5/M6 共同确认接口样例；M2/M6 可以基于明确标记的 Mock 并行开发。
5. 每人创建自己的分支和 Draft PR；禁止六个人共用一个开发分支。
