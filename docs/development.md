# M1 首次开发：API 启动与验证

对应 [Issue #11](https://github.com/StephenYI43/software-engineering-group-1/issues/11)。此阶段只有 API 骨架，未实现登录、课程、数据库连接、数字人或 AI 服务。

## 环境

安装 Python 3.12.14 和 uv 0.12.13。若使用 Python 安装 uv：

```bash
python -m pip install uv==0.12.13
```

以下命令都在仓库 apps/api 目录运行。uv 未进入 PATH 时，可使用同一环境内的 python -m uv 替代 uv。仓库 .local 为本机忽略的工具目录，不是团队依赖。

```bash
cd apps/api
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问 http://127.0.0.1:8000/api/v1/health；开发文档 http://127.0.0.1:8000/docs。退出用 Ctrl+C。无需 .env、模型密钥或数据库。

Windows PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

期望 status=ok，service=learning-assistant-api，requestId 与 X-Request-ID 响应头相同。此端点只检测进程存活，不做外部依赖就绪检查。

## 提交前验证

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

覆盖率阈值为 80%。新接口必须增加正常/失败/资源权限用例；当前 3 项仅验证健康检查、请求 ID 独立且不可由客户端覆盖、未知路由返回 404。

GitHub API CI 在 PR、main 推送和初始骨架分支推送时执行同一组检查，10 分钟超时。远程运行成功与分支保护是否开启是两件事。线上部署未配置。

## 下一次工作

先评审 [平台契约](../packages/contracts/platform/README.md)，再实施身份认证与资源权限的小任务。M2/M6 可使用已批准的骨架，M3/M4/M5 继续各自契约和模块开发。不要把 /health 成功视为能安全处理真实学生数据。
