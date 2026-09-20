# Git 与 AI 协作工作流

## 开始一个任务

1. 阅读 README、docs/team-plan.md、docs/code-standards.md 和 AGENTS.md。
2. 认领小 Issue（建议 0.5—2 天），填写验收标准、依赖、影响目录、验证方法。
3. 从最新 main 新建个人任务分支，尽早创建 Draft PR。
4. 先确认接口样例，再实现和测试；准备好后转 Ready for review。
5. 非作者评审通过后 Squash Merge；联调验收通过再关闭 Issue。

大型模块卡是 Epic，不能把整张卡当作一个巨大 PR。每人同时最多一个主要 In Progress 任务，分支尽量 1—3 天合并。

## 分支与提交

人工分支：<type>/<issue>-<english-kebab-description>，例如 feat/12-photo-question。
Codex 创建分支默认加 codex/，例如 codex/feat/12-photo-question。已有 docs/1-project-collaboration-baseline 属于本次建立规范之前创建的文档分支，保留。

```bash
git fetch origin
git switch main
git pull --ff-only
git switch -c feat/12-photo-question
# 编辑后只暂存相关文件
git add path/to/changed-file
git commit -m "feat(tutoring): 支持拍照题干确认"
git push -u origin feat/12-photo-question
```

命令中的编号/文件名是示例，替换为实际任务。先检查 git status，不覆盖未提交工作。

Commit 和 PR 标题：type(scope): 简短中文说明。
type 为 feat/fix/docs/refactor/test/style/perf/build/ci/chore；scope 使用实际领域如 tutoring/media/learning/analytics/platform。
禁止只写 update、final、修一下。PR 中用 Refs #编号；只在合并即可满足全部验收时用 Closes #编号。

## Review 与完成定义

普通 PR 至少 1 名非作者评审。权限、迁移、公共接口、学生隐私和模型工具执行逻辑至少 2 人评审，包含相关领域负责人。AI 自评不能代替成员审核。

每个 PR 一个目标，推荐不超过 400 行有效业务代码；较大改动解释原因或拆分，生成文件和锁文件单独说明。作者必须能解释 AI 生成的关键逻辑，提供实际运行的命令和证据。

验收标准全部通过、相关测试通过、文档与契约同步、PR 已审核合并、集成演示验证后才算完成。“已写代码”“已合并”都不是单独完成条件。

main 保护和 API 必需 CI 已于 2026-09-15 启用。所有 main 改动必须通过 PR，并满足：分支为最新 main、`API quality (Python 3.12)` 成功、至少 1 名非作者批准、最后一次推送不能由该批准者完成、讨论全部解决。过期批准会被撤销；管理员同样受保护规则约束；禁止强推和删除 main。仓库只允许 Squash Merge，合并后自动删除任务分支，并要求线性历史。

自动部署尚未启用。CODEOWNERS 已写入真实账号映射，但 CODEOWNERS 本身不会强制两名评审人；权限、迁移、公共接口、学生隐私和模型工具执行逻辑仍须按上文人工邀请至少 2 名评审人。规范文档同样通过 PR 供团队评审。若 GitHub 远程配置与本文不一致，以先停止合并、由 M1 核验并回写差异为准，不能静默绕过门禁。

## 看板与及时反馈

当前 Project 使用已存在的 Todo → In Progress → Done 三种状态。
Todo 表示待明确/待开工；In Progress 包含开发、评审和联调，在 Issue 更新中注明当前阶段；Done 要求集成验收完成。阻塞使用 blocked 标签，说明原因、已试办法、需要谁协助。不要声称自动同步已启用。

开始任务、接口变化、出现阻塞、提交评审和完成验收时立即更新 Issue/PR；每个工作日结束前补充：

```text
已完成：
验证证据：
剩余工作：
阻塞/依赖：
下一步：
```

每周一次全链路演示。微信群和 AI 会话可以讨论，但结论、接口变更和进度回写 GitHub。本规则是团队工作时反馈约定，不是已部署的持续自动监控。

## 冲突、发布和失败恢复

每日同步 main。个人分支可 rebase；多人共享分支避免改写历史。发生冲突共同核对语义，不盲选 ours/theirs。必要的 force-with-lease 仅限确认无人依赖的自己分支；main 禁止强推。所有冲突解决后重跑受影响测试。

M1 建立开发/测试环境，发布由组长确认。首个演示版本用 v0.1.0，后续增量 v0.2.0、修复 v0.2.1；Release 记录变更、迁移、验证、已知限制与回滚路径。生产发布和数据删除不因 AI 建议而自动执行。

工具卡住时记录命令、等待时间和错误；恢复后先查文件/Git/远程现状，确认是否部分成功再重试，避免重复 Issue 或重复上传。每个小批次立即保存，长命令分段检查并及时反馈。
