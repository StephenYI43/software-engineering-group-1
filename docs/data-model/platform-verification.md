# 平台数据库启动与验证

关联 #48、#69。范围仅M1七张平台表；各业务域数据字典与迁移仍由各owner交付。

## 容器启动与迁移

仓库根目录运行，先复制infra/.env.example到infra/.env并填自己的开发密码。
该.env被Git忽略；Compose不会自动为API进程导入环境变量。

```powershell
Copy-Item infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/compose.yaml up -d --wait
docker compose --env-file infra/.env -f infra/compose.yaml ps
cd apps/api
$env:DATABASE_URL='postgresql+psycopg://learning_app:<URL编码后的开发密码>@127.0.0.1:5432/learning_assistant'
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked alembic current
uv run --locked alembic heads
uv run --locked python -m app.core.db.seed --confirm-development
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

占位密码须替换，不能原样执行后声称连接成功。
公开合成账号：student1/demo-student-1、student2/demo-student-2、teacher1/demo-teacher-1、admin1/demo-admin-1，只用于开发。
初次seed将密码哈希落库；重复seed不会重置密码或授权。默认会话密钥只供演示，非演示环境必须另行配置。

## 各领域接入

继承app.core.db.Base，在本域定义模型；M1在app/core/db/metadata.py登记import。
app.core.db.Database.sessions是唯一Session工厂，app.core.db.get_session是同步依赖。
get_session只关闭/回滚，不自动commit；service用with database.sessions.begin()或注入Session.begin()明确事务。
业务与learning_events必须用同一个Session/事务；repository不得自行commit。

新增Alembic revision先经M5登记down_revision，首版为0001_platform；不得各自新建独立Base或另一个0001。
鉴权仍接#16真实principal；本底座不会授予默认课程权限。
持久凭证复用DatabaseSessionStore(session,request_id)+SessionAuthority，不重写JWT。
读取可使用普通Session，签发/撤销必须在调用方事务内完成。

## 数据库测试

单独创建learning_assistant_test临时库。测试fixture会清空其中平台表，不使用要保留的数据。
本地配置后执行，未配置时集成测试明确skip，不能声称数据库已测。
GitHub Actions未提供该变量时，测试fixture自动创建固定PG17.11镜像的一次性本机Docker容器，动态分配端口并在结束后停止；启动失败使CI失败，不静默跳过。无需修改现有workflow。

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://learning_app:<URL编码后的开发密码>@127.0.0.1:5432/learning_assistant_test'
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

已覆盖：单head/空库升级/降级再升级/模型迁移无漂移；约束与部分唯一索引；seed幂等；审计写失败业务回滚；账号/角色失效；持久会话撤销；数据库故障503不回退。

## API与数据库进程重启验收

DATABASE_URL必须指向临时本机_test库；在另一终端启动相同环境的API端口58048。
状态文件放Git外，它包含负向验证用的合成token，不得上传或打印内容。

```powershell
uv run --locked python -m scripts.verify_platform_persistence --phase write --state <临时路径>/proof.json
# 停止API，重启数据库，保留数据卷，再重新启动API。
docker compose --env-file ../../infra/.env -f ../../infra/compose.yaml restart postgres
uv run --locked python -m scripts.verify_platform_persistence --phase read --state <同一临时路径>/proof.json
```

write执行两次seed、真实HTTP登录/退出、保存用户/配置/会话/审计ID。
read逐项比较相同ID/记录，验证旧token仍拒绝、错误密码HTTP401。仅访问本机API，忽略环境代理。

本次已在Windows/Python3.12.14/PostgreSQL17.11原生进程上实跑：

```text
WRITE: 4 synthetic users, configs, session and audit committed; token not logged.
READ: same IDs/records after restart; revoked token rejected; bad password 401.
PASS: API child and PostgreSQL were both restarted using the same database files.
```

API子进程停止后重新创建；pg_ctl仅对本次临时data目录fast restart，保留数据库文件。
这不是只换Session或在同一连接读回。本机没有Docker，因此Compose本机未运行；CI容器结果另记录。
首轮完整测试62项通过、覆盖率96.01%，有2条既有上游弃用警告；后续最终结果以PR记录为准。
本次平台通过不表示M2/M3/M4/M5/M6各域或完整课堂数据库报告已完成。
