# ADR-0003：Web 前端工具链与工程结构基线

状态：提议（M2 已提交实装验证，待非作者评审；不代表全员已批准）
日期：2026-09-15
提出人：M2 / @Saber-www
评审人：M1 / @StephenYI43（Node、pnpm 可复现性、CI、统一开发环境）；M6 / @xk1024（同一 Web 工程的消费者）；涉及根级 workspace 跨模块组织，M4 / @haoxuanluo351-lgtm 评审 `packages/avatar` 相关部分
关联任务：[Issue #22](https://github.com/StephenYI43/software-engineering-group-1/issues/22)（本 ADR）、[Issue #3](https://github.com/StephenYI43/software-engineering-group-1/issues/3)（M2 Epic）、[Issue #11](https://github.com/StephenYI43/software-engineering-group-1/issues/11)（M1 指派）
相关基础：ADR-0001（平台骨架，只落 API）、ADR-0002（模型 adapter）

## 问题与约束

`docs/code-standards.md:3` 要求「具体**前端**/数据库版本、模型供应商和部署平台在**相应任务的 ADR** 中锁定，不使用"latest"作为可复现配置」。ADR-0001 已明确把前端排除在其范围外（「前端和数据库环境的版本在对应任务中明确，尚未安装或启动」），M1 在 #11 中指派本 ADR 由 M2 起草。

约束：

1. **禁止 "latest"**，版本必须具体到可复现（`docs/code-standards.md:3`）。
2. **前端统一 pnpm**（`docs/code-standards.md:5`），与后端 uv 并列。
3. **必须能在 CI 跑通**——ADR-0001 已建立 API CI，前端 CI 由 M1 后续接入。
4. **必须与现有所有权一致**：`.github/CODEOWNERS` 把 `/apps/web/` 整棵树归 M2，M6 在 `apps/web/src/features/teacher/` 内工作。
5. **必须支持多人并行**：M2 与 M6 不能各自初始化一套工程基础。

## 候选方案与选择理由

### 决策一：工程结构采用**根级 pnpm workspace**

| 候选 | 说明 |
| --- | --- |
| **A. 根级 pnpm workspace（选定）** | 根目录 `pnpm-workspace.yaml`，成员含 `apps/web`、`packages/ui`、`packages/avatar` |
| B. `apps/web` 单包 | 锁文件在 `apps/web/` 内，与 `apps/api/uv.lock` 形式对称 |

选 A 的理由：`packages/ui`（M2）与 `packages/avatar`（M4）都是**要被 `apps/web` import 的 TypeScript 包**。方案 B 下这两者只能靠相对路径跨包引源码，或各自构建出 `dist` 再引，前者让 tsconfig / ESLint 的 project service 跨包失效（本 ADR 的验证已实测过这类配置失败，见下），后者凭空多一道构建步骤。

与后端的**不对称是有意的**：`apps/api` 是单个 Python 应用，没有"被其他应用 import 的本地共享包"，所以 `uv.lock` 留在包内是对的；前端有 `packages/*` 这一层，根级 workspace 才是对应结构。

`packages/contracts` **暂不作为 workspace 成员**——它当前是纯 Markdown 与 JSON，没有 `package.json`。若日后需要从契约生成 TS 类型，再单独评审是否纳入。

### 决策二：版本采用**保守可验证组合**，而非各自取 latest

实查发现当前主流多为新大版本，其中一处**存在硬性不兼容**：

```
$ curl -s https://registry.npmjs.org/typescript-eslint \
  | jq -r '.versions[.["dist-tags"].latest].peerDependencies'
{
  "eslint": "^8.57.0 || ^9.0.0 || ^10.0.0",
  "typescript": ">=4.8.4 <6.1.0"
}

dist-tags: {"rc-v8":"8.0.0-alpha.62","latest":"8.70.0","canary":"8.70.1-alpha.14"}
→ latest 与 canary 的 peer 均为 typescript < 6.1.0，TypeScript 7.0.2 不被支持
```

若采用 TypeScript 7.0.2，**类型感知 lint 链路直接断裂**，只能临时关掉 `recommendedTypeChecked` 全部规则。这恰是 `docs/code-standards.md:101`「禁止删除失败测试或降低阈值求通过」要避免的情形。

其余新版本的成熟度：

| 组件 | latest | 该大版本首发 | 判断 |
| --- | --- | --- | --- |
| TypeScript | 7.0.2 | 2026-07-08 | 不被 typescript-eslint 支持 |
| Vitest | 5.0.0 | 2026-09-03 | 发布 12 天 |
| pnpm | 12.4.1 | 12.0.0 → 2026-08-26 | 发布 20 天 |
| Vite | 8.3.0 | 8.0.0 → 2026-03-12 | 已半年，采用 |
| ESLint | 10.10.0 | 10.0.0 → 2026-02-06 | 已 7 个月，采用 |

本 ADR 的目标不是"用上最新"，而是"六个月后仍可复现安装"。低一档的稳定版本没有功能损失。

### 决策三：pnpm 通过 corepack 安装，shim 装到用户目录

实装时发现 `corepack enable pnpm` **因权限失败**：

```
$ corepack enable pnpm
Internal Error: EACCES: permission denied,
  symlink '../lib/node_modules/corepack/dist/pnpm.js' -> '/usr/local/bin/pnpm'
```

corepack 自身装在 `/usr/local/lib`，默认往不可写的 `/usr/local/bin` 建软链。**用 `--install-directory` 指向用户级目录即可，无需 sudo**：

```bash
corepack enable --install-directory ~/.npm-global/bin pnpm
corepack prepare pnpm@11.27.0 --activate
```

选择 corepack 而非 `npm i -g pnpm` 的理由：`package.json` 的 `packageManager` 字段可由 corepack 强制校验版本，团队成员与 CI 拿到的是同一个 pnpm，符合本 ADR 的可复现目标。

## 决策、影响与接口变化

### 锁定版本

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Node | 24.21.0（Krypton LTS） | 见下方「未验证项」 |
| pnpm | 11.27.0 | 写入 `packageManager` |
| TypeScript | 6.0.3 | **不使用 7.0.2**，理由见决策二 |
| react / react-dom | 19.3.0 | |
| @types/react / @types/react-dom | 19.3.0 | |
| vite | 8.3.0 | |
| @vitejs/plugin-react | 6.1.1 | |
| eslint | 10.10.0 | |
| typescript-eslint | 8.70.0 | |
| prettier | 3.9.6 | |
| vitest | 4.1.11 | **不使用 5.0.0** |
| @testing-library/react | 16.3.3 | |
| jsdom | 30.0.1 | |

### 目录与共享文件

```text
pnpm-workspace.yaml       # 新增（根）
package.json              # 新增（根，无业务依赖，放 scripts 与 packageManager）
pnpm-lock.yaml            # 新增（根，共享单点）
apps/web/package.json     # @app/web
packages/ui/package.json  # @pkg/ui      —— M2
packages/avatar/          # @pkg/avatar  —— M4，本 ADR 只声明其为 workspace 成员
```

**共享文件单点维护**（M1 在 #11 裁定，`docs/team-plan.md:27`）：

- 根 `package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml` 由 **M2 单点落地**，M6 不单独初始化
- 他人新增依赖可以发 PR，但共享 manifest / lockfile 变更须通知 M2 与受影响负责人
- **应用级根路由由 M2 维护**；M6 在 `features/teacher/` 内声明自己的路由配置，根 router 只做组合，M6 无需修改根 router 文件

### 命令基线

```bash
pnpm install --frozen-lockfile
pnpm typecheck     # tsc --noEmit
pnpm lint          # eslint .
pnpm format:check  # prettier --check .
pnpm test          # vitest run
pnpm build         # vite build
```

`--frozen-lockfile` 对应 ADR-0001 对 `uv sync --locked` 的同类要求：CI 与本地都必须用锁文件安装，禁止隐式更新依赖。

### 必要的忽略规则（实装踩到，必须写进配置）

两条规则不是风格偏好，**缺失会直接让 CI 失败**：

1. **ESLint 需忽略自身配置文件**。`projectService` 会尝试把 `eslint.config.js` 纳入类型工程，而它不在 `tsconfig.json` 的 `include` 内，报 `Parsing error: ... was not found by the project service`。配置中须有 `{ ignores: ['dist/**', 'eslint.config.js'] }`。
2. **Prettier 需忽略构建产物与锁文件**。否则 `dist/`、`pnpm-lock.yaml` 会被判定格式不合规，`format:check` 必然失败。须有 `.prettierignore` 含 `dist`、`node_modules`、`pnpm-lock.yaml`。

### 对其他成员的影响

- **M1**：前端 CI（lint / 类型 / 测试 / 构建）可按上方命令基线接入；pnpm 版本由 `packageManager` 字段固定。本 ADR 不修改任何 CI 文件。
- **M4**：`packages/avatar` 被声明为 workspace 成员，消费方式与 `packages/ui` 相同（由 `apps/web` 直接 import，无需各自构建）。
- **M6**：不初始化 `package.json` 或 lockfile；在 `features/teacher/` 内声明路由配置由根 router 组合。
- 本 ADR **不改动** `docs/code-standards.md` 与其他任何已有文件。

## 验证、迁移与回滚

### 已实测（不是计划，是实际执行结果）

在隔离目录建最小工程，按上表**精确版本**实装并跑通全链路：

```
$ node -v && pnpm -v
v24.15.0
11.27.0

$ pnpm install
Progress: resolved 219, reused 0, downloaded 195, added 195, done
+ react 19.3.0 / react-dom 19.3.0 / vite 8.3.0 / typescript 6.0.3 / vitest 4.1.11
  eslint 10.10.0 / typescript-eslint 8.70.0 / prettier 3.9.6 ...
Done in 1m 25.3s using pnpm v11.27.0

$ pnpm typecheck     → exit 0
$ pnpm lint          → exit 0
$ pnpm build         → exit 0  (✓ 15 modules transformed, ✓ built in 70ms)
$ pnpm test          → exit 0  (Test Files 1 passed, Tests 1 passed)
$ pnpm format:check  → exit 0
```

**类型感知 lint 确实生效**（这是排除 TS 7 后最需要证明的一点）。用两个探针实测确认类型信息流入了 ESLint：

```
src/Leak.tsx   2:3  error  Promises must be awaited ...  @typescript-eslint/no-floating-promises
src/Unsafe.tsx 2:9  error  Unsafe assignment of an `any` value  @typescript-eslint/no-unsafe-assignment
               2:14 error  Unexpected any. Specify a different type @typescript-eslint/no-explicit-any
```

同时 `tsc --noEmit` 抓到 `error TS2322: Type 'string' is not assignable to type 'number'`。

**lockfile 解析结果与上表逐项一致**：`react 19.3.0`、`vite 8.3.0`、`typescript 6.0.3`、`eslint 10.10.0`、`typescript-eslint 8.70.0`、`vitest 4.1.11`、`prettier 3.9.6`、`jsdom 30.0.1`、`@vitejs/plugin-react 6.1.1`、`@testing-library/react 16.3.3`、`@types/react 19.3.0`、`@types/react-dom 19.3.0`。`lockfileVersion: '9.0'`。

### 未验证项（不得当作已验证）

1. **Node 版本**：验证在 **v24.15.0**（本机现状）完成，而本 ADR 推荐 **24.21.0**。两者同属 Node 24 LTS，但 **24.21.0 未实际安装验证**。落地时须在 24.21.0 上重跑一次链路，或改推荐为 24.15.0。
2. **根级 workspace**：验证工程为单包，**workspace 结构本身未实装验证**。跨包 import 的 tsconfig / ESLint project service 配置须在 #23 中实测。
3. **CI**：前端 CI 尚未存在，本 ADR 只给命令基线，不声称已接入。
4. **`packages/avatar`**：仅声明为 workspace 成员，未验证 M4 的包在 workspace 下可正常构建。

### 迁移

无既有前端代码需要迁移，本 ADR 为首次建立。已合并的 `main` 不受影响。

### 回滚

本 ADR 为文档，回滚即恢复本文档。若 #23 实施中发现某版本不可用，**变更方式是提新 ADR 或修订本 ADR**，而不是直接改 `package.json`——版本一旦锁定，改动须可追溯（`docs/code-standards.md:3`）。

## 后续工作

1. **#23**：按本 ADR 建立 `apps/web` 工程壳与 `packages/ui` 骨架，并在其中实测 workspace 跨包消费（本 ADR 的未验证项 2）。
2. **M1**：接入前端 CI（命令基线见上）；确认 Node 版本口径（未验证项 1）。
3. **M6**：基于同一工程壳挂载教师端路由；不初始化第二套 `package.json` / lockfile。
4. **M4**：确认 `packages/avatar` 作为 workspace 成员的组织方式。
5. 若 typescript-eslint 后续支持 TypeScript 7，另提 ADR 评估升级。

## 与 ADR-0001 的关系

本 ADR 补齐 ADR-0001 明确留出的前端部分（其「后续任务」第 3 条「M1/M2/M6 确认 Web 工具链」）。两者不冲突：ADR-0001 锁定 Python 侧运行时与依赖，本 ADR 锁定 Node 侧。后端的 `apps/api/uv.lock` 与前端根 `pnpm-lock.yaml` 各自独立，互不影响。
