# 平台 API 启动与验证

在 #11 骨架上已增量实现 #45 登录与 #48 PostgreSQL 平台数据底座。
课程/数字人/真实AI尚未接入主应用。
数据库启动、迁移、seed与重启验证见 [平台数据库指南](data-model/platform-verification.md)。

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

访问 http://127.0.0.1:8000/api/v1/health；开发文档 http://127.0.0.1:8000/docs。退出用 Ctrl+C。
未配置DATABASE_URL时保留无需数据库的离线演示；配置后账号与会话必须使用PostgreSQL，不回退演示账号。

## 登录（Issue #45，无需数据库）

内置三个合成演示账号：

| 账号     | 密码           | 角色 |
| -------- | -------------- | ---- |
| student1 | demo-student-1 | 学生 |
| student2 | demo-student-2 | 学生 |
| teacher1 | demo-teacher-1 | 教师 |

```powershell
$body = @{ username = 'student1'; password = 'demo-student-1' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/login -Method Post -ContentType 'application/json' -Body $body
```

会话 token 为 HS256，默认 24 小时过期（`AUTH_SESSION_TTL_SECONDS`）；`/api/v1/auth/logout` 以进程内吊销列表使其失效，**重启后失效列表清空**，属 S1 已知口径。签名密钥默认值**仅限演示**，任何非演示用途必须通过 `AUTH_SESSION_SECRET` 覆盖；合成账号可用 `AUTH_SYNTHETIC_ACCOUNTS`（JSON 数组）整体替换，参考 `.env.example`。

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

GitHub API CI 在所有 PR、main 推送和手动触发时执行同一组检查，10 分钟超时。`API quality (Python 3.12)` 已配置为 main 的必需检查；main 同时要求非作者评审和讨论解决，细则见 `CONTRIBUTING.md`。线上部署未配置。

## 下一次工作

下一步实施 #16 课程/班级授权与各域数据库接入。模型注册/Base/Session/迁移约定见数据库指南，
不要另建一套连接或用户表。/health只验证进程存活，不代表数据库或真实学生业务就绪。
