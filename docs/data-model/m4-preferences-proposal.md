# M4 用户偏好接口草案（待 M2 确认）

本文件仅供 #72 的提供方与消费方讨论，不是已发布的 API 契约，也不表示
组件或持久化已接线。字段参考 #79 的 `avatar_profiles`，具体路径、错误格式
和更新方法需在实现前与 M2 对齐。继续使用已冻结的 v1 播报契约。

## 拟议读取结果

```json
{
  "autoPlay": false,
  "volume": 1.0,
  "speechRate": 1.0,
  "subtitlesEnabled": true
}
```

| 字段 | 类型 | 约束及建议默认值 |
| --- | --- | --- |
| `autoPlay` | boolean | 默认 `false`，用户明确开启后才自动播报 |
| `volume` | number | 0–1，最多两位小数；默认 1.00 |
| `speechRate` | number | 0.5–2，最多两位小数；默认 1.00 |
| `subtitlesEnabled` | boolean | 默认 `true` |

拟议更新请求使用上述四个字段的完整对象；服务端校验字段和范围后保存，
重复提交相同设置保持同一结果。是否需要部分更新、初次读取时是否持久化
默认值，以及数字人组件如何消费设置，需 M2 确认。字段以外的身份、角色、
所属用户不由请求体提供；服务端从已验证的登录身份获取所有者。

## 实施依赖

- #84 的平台数据库、统一 Base/Session 和迁移当前仍在评审，使用其分支作
  叠加基线，不把它记为已合并。repository 不自行提交事务。
- #79 的设计草案中 `avatar_profiles.config_version_id` 非空并引用
  `avatar_config_versions`；创建偏好记录需要先落实该依赖及默认配置策略。
- `focus_sessions.course_id` 引用 `courses`，#84 基线尚无该表。需要 M5
  确认课程表及迁移先后顺序；不能凭空创建其他领域表或省略外键而声称
  满足字典。
- migration revision 由 M5 协调登记；模型 registry 的接线由 M1 协调。
- 验收需覆盖本人读写、学生 A/B 隔离、数值边界、重复更新、事务回滚及
  真实 PostgreSQL 的重启读回。未确认鉴权和接口前不挂生产路由。

参考：#72、#79、#84。
