# 本批设计验证记录

日期：2026-10-24。数据库PostgreSQL17.11原生临时实例；Python3.12.14，使用apps/api现有锁定依赖，未引入新框架。测试库位于本次私有临时data目录，名称以_test结尾，非保留业务库。

## 实际命令

仓库根目录使用锁定API环境执行：

```powershell
apps/api/.venv/Scripts/python.exe scripts/database-design/build_schema.py
$env:DESIGN_TEST_DATABASE_URL='postgresql+psycopg://<测试用户>@127.0.0.1:<临时端口>/<独立空库>_test'
$env:DESIGN_SNAPSHOT_PATH='<Git外路径>/design-proof.json'
apps/api/.venv/Scripts/python.exe scripts/database-design/verify_design.py
# 关闭连接，pg_ctl仅重启本次私有data目录，保留文件。
apps/api/.venv/Scripts/python.exe scripts/database-design/verify_design.py --read-existing
apps/api/.venv/Scripts/ruff.exe check scripts/database-design
apps/api/.venv/Scripts/ruff.exe format --check scripts/database-design
git diff --check
```

占位URL必须替换为已核实的本机可丢弃空库。验证器会拒绝非本机、非_test库和已有public对象的库；不会清空已有数据。快照只记录逐表行数与全部字段摘要，不写token/密码或学生正文。

## 最终关键输出

```text
DDL: 40 tables / 413 columns; all FK definitions installed
INSERT: synthetic rows accepted across all 40 tables; platform seed retained
REJECT: ASCII username whitelist
REJECT: JSON null schemaVersion
REJECT: unpublished draft retirement
REJECT: missing FK
REJECT: out-of-range preference
REJECT: uncontracted persistent status
REJECT: JSON object version is not null
ROLLBACK: failed transaction left no event
LATE COMMIT: older invisible event became pending after later commit; processed event excluded
PASS: 40 tables/413 columns/390 constraints; 7 negative constraints; rollback and two-connection ledger query
SNAPSHOT: all 40 tables populated; only counts and aggregate digests recorded, no raw token
RESTART PASS: all 40 tables retain identical row counts, primary keys and field digests after PostgreSQL restart
```

平台seed连续执行两次；补充合成凭证的签发/撤销使auth_sessions也有样例，原始token只在进程内存。四十表在关闭连接与真实PG进程重启后比较全行摘要，包含主键。

首次样例构造曾被model_config_versions的Mock一致性CHECK和citation_id长度限制拒绝，已修正合成样例后在新的独立空库完整重跑；未删除约束求绿。最终参考DDL与结构清单一致，生成器assert检查40表/49个平台字段及全部JSONB列属性字典覆盖。

Ruff lint、格式检查和git diff --check实际通过。当前API/Web CI不会执行这套临时数据库设计验证器，不能用线上绿灯代替上面的实际命令。

## 明确未验证

- 各域应用ORM、Alembic revision串联、service/router及真实principal/ACL；
- 完整消费worker的并发、毒事件重放、重算与生产性能；两连接实验只证明本设计的未处理账本查询不会被高水位永久排除；
- 完整JSON嵌套schema与所有跨表业务规则；SQL CHECK仅覆盖可表达子集，属性规则仍待领域service测试；
- 各域API进程重启、真实浏览器流程、真实模型与真实TTS/ASR；
- 本机Docker Compose、生产部署、备份恢复和真实数据生命周期审批。

平台#75此前62项及M2 E1/E2取证是已有平台实现证据，不与本批合并计算成全域应用完成。参考SQL通过后，仍须领域owner按任务交migration/repository/API与分层验收；本批不关闭#69。


## 2026-11-03：M6评审修订复验

同一锁定Python环境和Windows原生PostgreSQL 17.11，另建仅监听本机的空测试库。重新执行build_schema.py、verify_design.py、私有实例pg_ctl restart、verify_design.py --read-existing。初版上方的413列/390约束/7反例记录保留为历史证据。

- 40表、415列、397约束，全表合成数据写入成功；16项数据库约束反例被拒绝。
- 新反例覆盖unknown不能写0、known不能缺数值、改时区不能复制同日键、重放/解决必须有操作者、报告失败必须有安全错误码、执行与结束时间约束。已确认的0可写，合法重放状态与报告失败可写；核对两条查询索引存在。
- 保留原失败事务回滚与双连接迟到提交可见性；实际重启临时PostgreSQL后40表行数、主键及全字段摘要一致。
- 本次验证为参考DDL和受控SQL操作；未运行M6新worker、领域应用迁移、真实ACL或完整用户流程。source_hash协议仍待消费者实现验证；不把本次SQL测试当成M6分支PG测试已通过。
