# PostgreSQL 平台数据底座与迁移

状态：实现候选，待 M5/M6 评审。日期：2026-10-20；关联 #48、#69；模型基线 PR #73。

## 决定与版本

采用 PostgreSQL 17.11、SQLAlchemy 2.0.55 同步 ORM、psycopg/binary 3.3.6、Alembic 1.20.0。
Python3.12.14/uv0.12.13保持不变，精确版本/哈希见apps/api/uv.lock。
容器固定17.11-bookworm及sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826。
不启用pgvector或MQ，保留领域同步repository边界。

## 单一数据库入口

- Base：app.core.db.Base；各领域模型继承它。
- Database：app.core.db.Database，统一engine和sessions工厂。
- 注册：app/core/db/metadata.py显式import已接受的领域模型。
- FastAPI依赖：app.core.db.get_session，同步handler/dependency承载阻塞I/O。
- 事务：service使用sessions.begin()，repository只flush，不commit。
- Alembic：apps/api/alembic.ini、migrations/versions；首版0001_platform，down_revision=None。

首版只建平台七表，不写其他领域业务。后续迁移由M5协调单链，不回改合并历史。
迁移保存独立DDL，不调用运行时Base.metadata.create_all。当前main没有数据库schema，已验证空库升级、降级再升级、alembic check。

## 模式与权限边界

DATABASE_URL未设置时保留原离线演示，退出仅在内存中失效；设置后只用数据库账号和持久会话，数据库故障返回503，不回退演示账号。
JWT与登录/登出响应不变。DatabaseSessionStore在调用方事务内记录/撤销jti摘要，parse额外检查数据库会话、当前角色与账号状态。
签发和审计同事务；事务成功后才返回token。密码存版本化scrypt哈希，不保存明文；原始token不落库、不打印。
应用关闭dispose连接池；不会在启动时自动迁移、建表或seed。

显式开发seed需--confirm-development且APP_ENV=development；创建学生A/B、教师、管理员四个合成账号与角色/配置。重复执行保留原ID/密码/授权，使用事务锁串行化。
配置版本目前只有表、seed和ORM读写；动态发布/回滚服务、配置完整业务校验仍待后续实现。
数据库底座不代替#16课程/班级ACL，不开放默认角色授予或管理员接口。

## 验证

测试仅接受本机且以_test结尾的临时库；fixture会清空这个测试库的平台表。
本地未提供TEST_DATABASE_URL时明确skip，不用SQLite替代。GitHub Actions中由测试fixture启动固定PG17.11的一次性Docker容器、等待就绪并在结束后停止；容器启动失败则CI失败，不跳过数据库测试。现有workflow不修改。
本机无Docker，使用Zonky Maven发布的PG17.11 Windows原生二进制，在英文临时目录初始化真实数据库，未安装系统服务。
Compose本机未运行，容器服务交由CI验证；原生PG和API进程重启验证已实跑，证据与接入步骤见../data-model/platform-verification.md。

## 参考

- [SQLAlchemy Session与事务](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [Alembic迁移环境](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [psycopg3安装](https://www.psycopg.org/psycopg3/docs/basic/install.html)

本ADR是待评审实现记录，不声称两位非作者已确认；评审通过前不合并。
