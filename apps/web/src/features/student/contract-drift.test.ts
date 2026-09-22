import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { TutoringAction, TutoringEmotion } from './types'

/**
 * 契约漂移守卫：数字人枚举。
 *
 * `TutoringResponse.emotion/action` 的取值集合**不是**本模块定的，而是 M4 在
 * `packages/contracts/avatar/avatar-controller.md` 冻结的 `AvatarEmotion` / `AvatarAction`
 * 全集（`docs/code-standards.md:69`：契约是唯一来源）。本测试直接从契约文件抽取值集合，
 * 与 `./types.ts` 中的联合类型逐项比对：契约改了集值而前端没跟，这里变红。
 *
 * 与 M4 的 `packages/avatar/src/contract-samples.test.ts` 同思路（那边守事件语义，
 * 这边守枚举集值），区别是本包不依赖 `@pkg/avatar`——`packages/avatar` 尚未进入
 * `apps/web` 依赖，宿主接入随 tutoring 页面工作一起做。
 *
 * 读取路径基于 `process.cwd()`：vitest 无论经 `pnpm -r`、`pnpm --filter @app/web` 还是 CI 调用，
 * 工作目录都是 `apps/web`（本包的 package.json 所在目录）。**不要**改用 `import.meta.url`——
 * vitest 转换后它不保证是 `file:` URL（实测 `fileURLToPath` 会抛 `The URL must be of scheme file`）。
 * 移动契约文件时需要同步更新此处与 `apps/web/package.json` 的相对层级。
 */

const CONTRACT_PATH = resolve(process.cwd(), '../../packages/contracts/avatar/avatar-controller.md')

/** 契约文件里形如：取值：`a` | `b` | `c` */
function parseValuesAfterHeading(markdown: string, heading: string): string[] {
  const headingIndex = markdown.indexOf(heading)
  if (headingIndex < 0) {
    throw new Error(`契约中找不到小节：${heading}`)
  }
  const section = markdown.slice(headingIndex)
  const match = /取值：(.+)/.exec(section)
  const values = match?.[1]
  if (values === undefined) {
    throw new Error(`契约小节「${heading}」下找不到「取值：」行`)
  }
  // 逐个解构捕获组并显式判 undefined：`noUncheckedIndexedAccess` 下 `m?.[1]` 仍是 `string | undefined`。
  return Array.from(values.matchAll(/`([^`]+)`/g), ([, value]) => {
    if (value === undefined) {
      throw new Error(`契约小节「${heading}」的「取值：」行里有空的反引号片段`)
    }
    return value
  })
}

/** 源码里定义的联合类型，作为「前端实际接受的取值集合」。 */
const EMOTIONS_IN_CODE: readonly TutoringEmotion[] = [
  'neutral',
  'encouraging',
  'thinking',
  'celebrating',
]

const ACTIONS_IN_CODE: readonly TutoringAction[] = ['idle', 'nod', 'point', 'write']

/** 编译期守卫：上面的清单必须与 `./types.ts` 的联合类型完全一致。 */
const EMOTIONS_IN_CODE_SATISFIES: readonly TutoringEmotion[] = EMOTIONS_IN_CODE
const ACTIONS_IN_CODE_SATISFIES: readonly TutoringAction[] = ACTIONS_IN_CODE

describe('数字人枚举契约漂移守卫', () => {
  const contract = readFileSync(CONTRACT_PATH, 'utf8')

  it('AvatarEmotion 集值与前端 TutoringEmotion 一致', () => {
    expect(parseValuesAfterHeading(contract, '### AvatarEmotion')).toEqual([
      ...EMOTIONS_IN_CODE_SATISFIES,
    ])
  })

  it('AvatarAction 集值与前端 TutoringAction 一致', () => {
    expect(parseValuesAfterHeading(contract, '### AvatarAction')).toEqual([
      ...ACTIONS_IN_CODE_SATISFIES,
    ])
  })

  it('两组集值都是非空且互不重复（解析失败会立刻暴露）', () => {
    const emotions = parseValuesAfterHeading(contract, '### AvatarEmotion')
    const actions = parseValuesAfterHeading(contract, '### AvatarAction')
    expect(emotions.length).toBeGreaterThan(0)
    expect(new Set(emotions).size).toBe(emotions.length)
    expect(new Set(actions).size).toBe(actions.length)
  })
})
