# 接口设计验证记录

任务#80，基线main 7c174a4。所有v2为候选，尚未接入真实业务路由。

## 实际运行

- 使用仓库锁定Python3.12.14环境；新增开发依赖openapi-spec-validator==0.7.2，传递依赖进入uv.lock。
- OpenAPI3.1.1完整规范校验已实际通过；JSON Schema逐模型、逐请求/响应实例验证，静态鉴权声明、命名、分页、204、敏感字段和SSE反例由tests/contracts执行。
- 最终全量实际528 passed，覆盖率99.53%；其中370项为本批契约验证、158项为已有应用测试。包含114个HTTP操作、233个结构、逐操作请求/响应、Postman保存样例及考试公开/私有答案隔离反例。覆盖率只统计现有app，不表示新v2服务已实现。
- ruff格式/lint（含scripts/api-design）、mypy实际通过；生成一致性--check实际通过。契约工具通过本目录.ruff.toml继承API的同一套配置，避免从不同工作目录运行时出现88/100列标准差异。
- Web的pnpm format:check、typecheck、lint、test（5个文件31项）及build实际通过。生成的v2类型独立且未导入旧客户端。
- 现有依赖发出Starlette/httpx和AnyIO兼容别名两项弃用警告，无失败；本任务未为消除警告改动已锁定运行依赖。

## 复跑

```powershell
cd apps/api
uv sync --locked
uv run --locked ruff format --check . ../../scripts/api-design
uv run --locked ruff check . ../../scripts/api-design
uv run --locked mypy
uv run --locked pytest
uv run --locked python ../../scripts/api-design/build_contracts.py --check
```

仓库根目录另跑scripts/api-design的ruff和Web门禁。生成文件不是手改格式；api-v2.ts由生成器维护，API CI核对源漂移，Web仍做类型检查和lint。

## 明确未验证

- 新v2路由部署、真实角色/owner权限、限流/TLS/CORS/网关，以及后台worker并发。
- 新增持久化实体和事件2.0迁移、PG事务/回滚/重启、任务重放与对象存储清理。
- 真实模型、ASR/TTS/OCR、真实课件、真实学生资料和浏览器完整学习链。
- Apifox/Postman真实运行、候选P99压测和生产备份恢复。

本批仅通过schema/样例并不证明这些真实能力。保留Mock标识，不降低原80%应用覆盖门槛，不修改原测试求绿。AI辅助补设计、生成和静态测试；作者负责自审，不能替代非作者Review。
