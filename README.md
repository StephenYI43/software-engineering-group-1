# 大学生辅助学习 AI 数字人系统

软件工程第一组：陪伴式、学科化、全流程的 AI 学习助教，覆盖预习、答疑、复习、作业与备考。

当前已建立 API 开发骨架（健康检查、请求 ID、测试与 CI 配置）与 Web 前端工程壳（学生端路由骨架、共享组件、契约 Mock），业务功能尚未实现。第一阶段以一门高数示范课程打通完整学习链路。API 启动方式见 [开发指南](docs/development.md)。

## 本地启动

### 前端（`apps/web`）

环境：Node 24.21.0、pnpm 11.27.0。版本由 [`.node-version`](.node-version) 与根 `package.json` 的 `packageManager` 字段固定，依据 [ADR-0003](docs/adr/0003-web-toolchain.md)。

```bash
# 安装 pnpm（经 Corepack，无需 sudo）
corepack enable pnpm

# 在仓库根目录装依赖（pnpm workspace，前端与 packages/* 共用一份锁文件）
pnpm install --frozen-lockfile

# 启动开发服务器
pnpm dev          # 默认 http://localhost:5173

# 提交前检查
pnpm typecheck    # tsc --noEmit
pnpm lint         # eslint .
pnpm format:check # prettier --check .
pnpm test         # vitest run
pnpm build        # vite build
```

学生端路由：`/courses`、`/courses/:courseId`、`/tutoring/:sessionId`。

开发服务器支持用查询参数切换演示场景（数据全部为契约样例，非真实服务）：

- `?turn=thought|summary|noEvidence` —— 切换演示哪一轮答疑回答
- `?mock=normal|empty|error|error-raw|slow` —— 切换正常 / 空 / 契约内错误 / 非契约错误 / 慢响应

### 后端（`apps/api`）

见 [开发指南](docs/development.md)。

## 开工入口

- [六人分工与迭代计划](docs/team-plan.md)
- [需求范围与验收](docs/requirements.md)
- [代码、命名与 API 规范](docs/code-standards.md)
- [Git、PR、评审与反馈工作流](CONTRIBUTING.md)
- [给 AI 开发工具的统一指令](AGENTS.md)
- [成员任务卡](docs/tasks/index.md)
- [项目看板](https://github.com/users/StephenYI43/projects/5)

成员分工已确认并指派到 Issue：M1 @StephenYI43、M2 @Saber-www、M3 @ljt2293977194-dotcom、M4 @haoxuanluo351-lgtm、M5 @Jiege123-CMYK、M6 @xk1024。详见六人分工表。

## 协作原则

每人一个主模块，一个任务分支；接口先约定，再各自实现。AI 生成代码由提交者核验，通过非作者评审与验证后合并。进度、阻塞和验收结果记录到 Issue/PR。

本仓库公开，请只使用合成或获许可的测试资料，不提交学生隐私、模型密钥或私有课件。
