# 全域数据库实施决定

## 基线和与既有实现的差异

现有main d01f32e没有应用数据库；#75 e1fb5ff提供平台七表和持久会话候选，真实PG62项与进程重启已验证，M2另在#74 423d0d6独立取证。两者仍待评审合入。本批其余表属于补全设计，只有参考SQL验证，不代表应用实现或已合入。

用户名按#75实际ASCII白名单登记，显示名另放profile；配置draft不可不经发布直接retired。参考DDL补充schemaVersion不接受JSON null的CHECK，后续需单独迁移，不能把补强列为旧#75已完成。

## 单一事务与跨域关系

统一PostgreSQL17.11、SQLAlchemy2同步Session、psycopg3、Alembic；一套Base和Session工厂，repository不得commit。成功业务+learning_events+必要管理审计同事务。拒绝/失败审计用受控独立事务，不和回滚一起消失，也不伪装成功。

用户ID都引用users；course与class分离；同人同课可以多班。M5拥有enrollments/teaching_assignments及公共service，M1控制选课HTTP入口、身份/角色和统一ACL语义，绝不建第二套关系表。classes主讲与有效teaching_assignment同事务维护。

物理FK只证明行存在，不证明角色、owner或课程访问权。关联资源的同课程、同学生、一致班级等不能完整用行内CHECK表达的条件，在service中锁定父对象后校验并测试。本人私有资源越权404，角色不符403，未认证401；admin不等于无限读取学生对话全文。前端只提交允许字段，不直写PG或自报userId/role。

## 班级历史和事件归属

enrollments保留joined_at/left_at区间，转班关闭旧区间、新开关系，不改历史事件。作业/提交事件取不可变的作业/提交class快照；章节浏览如在班级上下文中发生，服务端校验并保存class。无法唯一归属的course级行为class_id=NULL，仅入个人/课程汇总，不复制到同课程所有班。

历史统计按事件发生时class_id聚合，查询时按教师当前授权花名册和范围做数据裁剪；转班后不得把旧班事件重新贴到新班。无class数据、已退班学生在教师报告中的展示口径须最小化，仅显示该教师当前仍有授权的班级历史，不向新教师泄露旧班全文。

class_id是本批新增持久元数据，当前wire1.0未包含它，不能静默扩公共JSON。M5/M6需提交公开feed和样例增量共同评审；原occurredAt游标仍仅是内存演示实现，不当作生产摄取保证。

## 不漏迟到提交的账本协议

1. 每轮使用READ COMMITTED新事务，锁定analytics_consumers本行，防同一consumer并发应用相同事件。
2. 经M5公开事件feed查询所有未进入本consumer的processed账本、且未处于open隔离的已提交事件。可按(occurred_at,event_id)稳定排序LIMIT一批，但**不以任何上次最大时间/序号做永久排除条件**。
3. 对每个事件执行schema/归属校验，更新聚合和插入processed账本在同一事务；事件失败可用savepoint回滚该事件变更并登记隔离，最终原子提交本轮可证明的结果。
4. 下一轮新事务重新查未处理集合。T1先取小号/旧occurredAt未提交，T2先提交并处理；T1随后提交后仍不在账本，下轮一定成为候选。无需假设bigserial分配顺序等于提交顺序，也不靠有限回看窗口假装最终可见。
5. open毒事件明确告警、报告partial；授权重放置retry_ready；成功时ledger/聚合/resolved同事务。不得静默标processed跳过。
6. 长期依赖源事件保留；未处理或open隔离事件不得先被清理。算法变化新consumer版本，独立ledger/聚合后再切换，旧版本保留可追溯性。

查询例（:consumerId为绑定参数，不是字符串拼接）：

```sql
SELECT e.* FROM v_learning_event_feed AS e
WHERE NOT EXISTS (
  SELECT 1 FROM analytics_processed_events AS p
  WHERE p.consumer_id = :consumerId AND p.event_id = e.event_id
) AND NOT EXISTS (
  SELECT 1 FROM analytics_quarantined_events AS q
  WHERE q.consumer_id = :consumerId AND q.event_id = e.event_id AND q.status='open'
)
ORDER BY e.occurred_at,e.event_id LIMIT :batchSize;
```

到账顺序可能和发生顺序不同，学习时长等非交换聚合须按受影响学生/班级/日的已处理源事实重算，而非仅对迟到事件追加秒数。无观测unknown+NULL、已确认无活动known+0；dataThrough仅本响应纳入范围的最新发生时间；有open隔离时不能宣称complete。源查询故障503，不返回空成功。

官方依据：[READ COMMITTED](https://www.postgresql.org/docs/17/transaction-iso.html)、[SELECT行锁](https://www.postgresql.org/docs/17/sql-select.html)、[唯一和CHECK约束](https://www.postgresql.org/docs/17/ddl-constraints.html)。本协议是本批待评审的设计决定，不声称#38或#65已经实现。

## 答疑状态和文件安全

持久轮次active/completed/aborted；stop、断连、失败以abort_reason区分，is_complete只在completed为true。成功结算、引用和阶段推进同事务；失败不推进。SSE seq不落库，会话内seq在行锁下分配，同会话至多一个active。

中断正文可保存最多16000字符，必须标未完成，不加入完成历史、不触发数字人播报；成功正文与delta拼接逐字节一致且不静默截断。恢复任务须确认worker租约失效再把遗留active结算aborted/server_restart，避免误结算仍运行进程。

服务端创建会话ID的新接口须先提交schema并由M2/M1确认；旧短ID样例不批量改写或据前缀判权。course_id=NULL仅支持通用答疑，不授权课程文档；请求指定无权course先404，而不是降成hasEvidence=false旁路。

文档版本新行、chunks不跨页，引用存标题/页码/正文快照；检索前只获得已授权文档集，历史引用和原文件下载分别核权。文件和模型输出当数据，不能执行其中命令。教师不默认读完整问答；密钥仅环境/secret服务，库中只存受控provider及非敏感参数。

## 保留清理与数据库运行

本课只使用合成账号与获许可测试文件，演示结束清理；真实部署前学校/项目必须批准每类数据保留期限、同意版本、删除权限与备份到期，未确认不接收真实学生录音/课件。这里不把编造天数写成学校政策。

撤回授权先下架并阻断新检索/下载；确需清除时经授权批次清理对象存储、chunks、引用片段和派生文本/缓存，再处置业务关系/备份，不以RESTRICT为永久拒删理由。日志/审计仅保留无敏感正文的必要动作元数据。不得直接CASCADE删整组数据或清保留卷。

本地容器仅绑定127.0.0.1，密码不入Git；生产连接TLS、网络隔离、迁移与应用账号分离、最小表权限、加密备份和恢复演练由部署任务落实。本批DDL不创建超级用户/密码/全库授权，不代表安全部署已配置。应用健康检查是存活探针，数据库可用性另测。

## 分批落地顺序

- M1：先#73/#75双审及平台补强迁移，再完成#16真实授权、#47/章节intent接口schema，维护metadata。
- M5：课程/班级/关系，接着作业/提交/错题/计划/提醒/事件；协调单链revision。
- M3：文档/配置/会话/回合/引用最小纵切片，补创建会话契约与中断恢复。
- M4：风格/偏好/媒体job/播报元数据，真实TTS/ASR与focus功能另批；不造新框架。
- M6：consumer/ledger/隔离+最小统计，先两连接乱序提交和重启；随后报告任务。
- M2：复用已交检查器和E1/E2证据，逐域恢复真实验收；不将引用M1数字当自己的全域通过。

每批都需要迁移升级、单head、真实PG约束/回滚/幂等/隔离和进程重启证据。未接API只写repository通过；未调用真实模型就保留Mock标识。本批只交设计/参考DDL，不关闭各域实现任务。
