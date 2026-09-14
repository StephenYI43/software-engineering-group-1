# 代码、命名与接口规范

本文是开工基线，尚未安装框架或实现业务。首版建议 React + TypeScript + Vite 学生/教师 Web、FastAPI 模块化后端、PostgreSQL（需要时启用 pgvector），避免多人各自搭建不同架构。具体版本、模型供应商和部署平台由 M1 在脚手架任务的 ADR 中锁定，不使用“latest”作为可复现配置。

前端统一 pnpm，后端统一 uv；提交各自锁文件。新增框架、模型服务或数据库需要说明理由并由受影响负责人评审。

## 目录契约

```text
apps/web/src/
  features/student/          # M2
  features/teacher/          # M6
  generated/                 # 自动生成 API 类型，禁止手改
apps/api/
  app/core/                  # M1：配置、鉴权、日志
  app/domains/
    tutoring/                # M3
    knowledge/               # M3
    media/                   # M4
    learning/                # M5
    analytics/               # M6
  migrations/                # 各领域编写，M5 协调
  tests/
packages/ui/                 # M2：共享组件
packages/avatar/             # M4：数字人组件
packages/contracts/          # OpenAPI 快照、事件 schema、示例
ai/prompts/                  # M3：版本化提示词
ai/evaluations/              # M3：评测样例和结果
infra/                       # M1
docs/adr/                    # 架构决策
```

以上为计划目录，不表示当前已有应用。各后端领域内部按 router、schemas、service、repository 分层。路由只处理协议，业务规则放 service，数据访问放 repository；跨领域走公开服务函数或事件，不直接写其他模块的表。前端不得直连数据库或持有模型密钥。

## 命名统一表

| 对象 | 规则 | 示例 |
| --- | --- | --- |
| TS 变量/函数 | camelCase | createStudyPlan、durationSeconds |
| React 组件/类型 | PascalCase | StudyPlanCard、CourseResponse |
| TS 文件/目录 | kebab-case | study-plan-card.tsx |
| Hook/事件 | use、on、handle 前缀 | useStudyTimer、onSubmit、handleSubmit |
| 布尔值 | is/has/can/should | isLoading、canEdit |
| Python 文件/函数/变量 | snake_case | study_plan.py、create_study_plan |
| Python 类/异常 | PascalCase，异常以 Error 结尾 | StudyPlan、CourseNotFoundError |
| 常量/环境变量 | UPPER_SNAKE_CASE | MAX_UPLOAD_BYTES |
| API 路径 | 小写复数名词、kebab-case | /api/v1/study-plans |
| JSON、查询与路径参数 | camelCase | courseId、pageSize |
| 表名/数据库列 | 复数表名、snake_case 列 | study_plans、course_id |
| 主键/外键 | id、实体_id | id、user_id |
| 时间字段 | created_at/updated_at 等 | started_at |
| 枚举值 | 小写 snake_case | in_progress |
| 提示词文件 | 场景和版本 | guided-tutoring.v1.md |

不用拼音变量、无意义缩写、test2/final/new 等名称。React 导出名 PascalCase，与 kebab-case 文件名对应。Python 内部 snake_case 通过 schema alias 转成 JSON camelCase。时间变量标明单位；API 时间使用 UTC ISO 8601，UI 按用户时区显示。

## 编码

- UTF-8、LF；TS/JSON/YAML 两空格，Python 四空格。前端 Prettier/ESLint/TypeScript strict，后端 Ruff/类型检查/Pytest，由 M1 脚手架任务落实配置。
- TypeScript 不随意使用 any、非空断言和 ts-ignore；外部数据用 unknown 并验证。Python 公共函数标注类型，不用可变默认参数。
- 函数专注一件事，复杂业务分解为可测试单元，禁止大量复制粘贴。复用前先检索仓库已有实现。
- 注释解释原因、边界和业务规则；公开函数写必要文档。TODO 必须关联 Issue。
- 不吞异常，不以 200 + 空字符串表示失败；用户提示不暴露堆栈。外部请求设置超时，重试有上限且考虑幂等。
- 数据写入使用事务；迁移需从主分支现有 schema 升级验证，已合并迁移不回改。
- 模型供应商经统一 adapter 调用，支持 Mock；禁止页面中硬编码供应商 SDK 调用。

## API 契约优先

实现前提交请求/响应/错误样例，由提供方和调用方共同评审。API schema 作为唯一契约，自动生成前端类型；变更同时更新契约和测试。

常规列表用 page/pageSize，返回 items/total/page/pageSize。错误结构：

```json
{
  "code": "COURSE_NOT_FOUND",
  "message": "未找到课程",
  "requestId": "example-request-id",
  "details": {}
}
```

异步解析/转写返回 202 与 jobId，通过任务状态接口查询 queued/running/succeeded/failed；重复提交需幂等。认证错误 401、禁止访问 403、缺失 404、冲突 409、验证失败 422、限流 429。私有资源可以按统一策略返回 404 防枚举。

首批需明确的边界：

| 提供方 → 调用方 | 契约 |
| --- | --- |
| M1 → 全员 | 用户身份、角色、课程/班级访问规则、requestId |
| M5 → M2/M6 | 课程章节、作业提交、错题、计划、提醒 |
| M3 → M2/M4/M5 | tutoring response：stage/content/citations/followUps/emotion/action |
| M4 → M2 | speak(text)、stop()、状态与错误回调；语音/文字降级 |
| M2/M4/M5 → M6 | 学习事件 eventId/eventType/userId/occurredAt/traceId/schemaVersion |
| M6 → M2 | 时长、掌握度和统计周期、样本数、未知状态 |

stage 采用 thought/hint/step/summary（thought 表示面向学生的解题思路）。流式答疑使用 SSE，定义 started/delta/completed/error、序号和停止行为；未经服务端确认完成的半截回答不当作完成记录。M3 负责校验模型 schema 与引用，客户端不能自行推进教学状态绕过后端校验。

## 测试、日志与安全

每个 PR 执行受影响模块格式、lint、类型、单测、构建；涉及契约、数据库时补集成和迁移检查。纯文档修改只需链接、内容和差异检查，不伪装成已跑业务测试。

应用 CI 建成后的目标：新增/修改业务代码行覆盖率 ≥80%，权限和资源隔离场景必须全覆盖；高风险改动增加端到端测试。禁止删除失败测试或降低阈值求通过，确需临时跳过时注明 Issue 和恢复日期。

必需 CI 使用固定 Mock 与合成数据，不依赖付费在线模型；真实模型评测在受控环境执行，记录模型、提示词版本、样本与结果。

结构化日志记录 requestId/事件/耗时/错误码，AI 额外记录模型、提示词版本、token 用量；不打印密钥、完整对话、录音或真实学生资料。认证、资源归属与课程检索权限均在服务端检查；上传校验大小、类型与内容，模型输出展示前净化。RAG 文档不能授予模型执行命令的权限。

数据采集/录音须有知情同意和删除途径；统计优先使用必要的汇总数据。测试资料使用合成或已获许可材料；公开仓库禁止真实学生信息和课件原文。密钥放本地环境或部署 Secrets，泄漏先吊销轮换再处理 Git 历史。
