# 手动 tutoring HTTP 联调

此脚本直接运行学生端客户端，通过真实 TCP HTTP 验证五组行为：完整回答及 delta/尾换行一致、
204 停止与 `stopped/client_stop`、停止后新轮且阶段不推进、未知 turn 404、完成轮重复停止后只推进一次。

它不由 Vitest 自动收集，应用没有 import 它，不进入生产 bundle。无需新依赖或修改运行时代码。
**只对本地合成数据运行**；不是生产鉴权、真实模型/RAG 或 PostgreSQL 持久化验收。

## 已验证版本

- M2 PR #68 原客户端：`6faf7a7009f0eca996353fb5c3fbf6a7d4eb9433`。
- M3 PR #62 后端：`ee378919bbaf860898176ae14dab2a1d9cd23baf`。
- Node `24.21.0`，Python `3.12.14`；复用已有 venv，FastAPI `0.141.1`、Uvicorn `0.53.0`、Pydantic `2.13.5`。

## 启动临时 Mock HTTP 服务

以下命令不会修改后端 tracked 文件。`gh` 只读下载指定 commit，`M2_PYTHON` 指向已有安装依赖的
Python 3.12 venv；或者在快照内按后端 `uv.lock` 安装。需要有仓库读取权限。

```bash
M2_HTTP_TMP=$(mktemp -d /tmp/m2-tutoring-http.XXXXXX)
mkdir "$M2_HTTP_TMP/backend"
gh api repos/StephenYI43/software-engineering-group-1/tarball/ee378919bbaf860898176ae14dab2a1d9cd23baf > "$M2_HTTP_TMP/backend.tar.gz"
tar -xzf "$M2_HTTP_TMP/backend.tar.gz" -C "$M2_HTTP_TMP/backend" --strip-components=1
M2_PYTHON=/absolute/path/to/apps/api/.venv/bin/python
cat > "$M2_HTTP_TMP/m2_http_dev.py" <<'PY'
from app.main import create_dev_app
from app.domains.tutoring.adapters import MockModelClient
from app.domains.tutoring.prompt_renderer import load_prompt_template
from app.domains.tutoring.repository import InMemoryTutoringRepository
from app.domains.tutoring.retrieval import StaticRetriever
from app.domains.tutoring.service import TutoringService

app = create_dev_app()
app.state.tutoring_service = TutoringService(
    client=MockModelClient(envelope=True, latency_seconds=0.15),
    retriever=StaticRetriever(),
    repository=InMemoryTutoringRepository(),
    template=load_prompt_template(),
    is_mock=True,
)
PY
PYTHONPATH="$M2_HTTP_TMP/backend/apps/api:$M2_HTTP_TMP" PYTHONDONTWRITEBYTECODE=1 \
  "$M2_PYTHON" -m uvicorn m2_http_dev:app --host 127.0.0.1 --port 18762 \
  > "$M2_HTTP_TMP/server.log" 2>&1 &
M2_SERVER_PID=$!
```

此处显式使用 `create_dev_app()`、合成 principal、慢 Mock 模型、静态检索和内存仓库。
慢模型为客户端在收到真实 delta 后发起停止留出时间。不要把该开发 factory 暴露到公网。
端口占用时改用空闲本地端口，并同步下方 origin。先确认服务启动成功：

```bash
curl --fail http://127.0.0.1:18762/api/v1/health
```

## 运行客户端探针

在包含本脚本的前端仓库根目录运行；Node 原生去除 TypeScript 类型，无需构建或 tsx。
脚本先注册 `.ts` 模块解析 hook，再动态载入未修改的客户端和解析器。

```bash
M2_HTTP_BASE=http://127.0.0.1:18762 \
M2_HTTP_WIRE_PATH="$M2_HTTP_TMP/wire-records.json" \
  node apps/web/src/features/student/api/test-utils/verify-tutoring-http.ts
```

`M2_HTTP_BASE` 必须显式设置为 localhost HTTP origin，不接受凭据、非本地 host、路径或查询。
每轮运行生成随机 session 前缀，服务不重启也能重跑。每个 HTTP 请求（含流读取）最多 10 秒，
整个检查最多 60 秒；断言失败退出非零。成功输出 `PASS 1/5` 至 `PASS 5/5`。

`M2_HTTP_WIRE_PATH` 可省略；设置时写出 HTTP 路径、状态和 SSE 事件，包含合成回答正文。
不写请求头、凭据或问题请求体。文件放 `/tmp`，不要提交为业务数据或真实模型证据。

结束后停止**本次启动**的服务并保留需要的日志：

```bash
kill "$M2_SERVER_PID"
wait "$M2_SERVER_PID" || true
```

验收记录应附双方完整 commit、Node/Python 版本、命令与输出，并明确上述 Mock 边界。
