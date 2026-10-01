import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockAvatarController } from './mock-avatar-controller'
import type { MockAvatarOptions } from './mock-avatar-controller'
import type { AvatarAction, AvatarEmotion, AvatarPlaybackEvent, SpeakInput } from './types'

/**
 * 契约样例回放测试。
 *
 * 直接读取 `packages/contracts/avatar/samples/*.json`（PR #51 冻结的契约样例），
 * 按 `calls` 顺序同步驱动 Mock 控制器，再推进计时，逐字段比对 `expectedEvents`。
 * 契约与本实现任何一方漂移都会让本测试变红——这是防漂移的硬闸门。
 *
 * 注意：contracts 目录不是 workspace 成员，这里经相对路径读取。路径基于
 * `process.cwd()`（`pnpm -r` / `pnpm --filter` 都会在本包目录下运行 vitest）；
 * 移动样例目录时需要同步更新。
 */

const samplesDir = resolve(process.cwd(), '../contracts/avatar/samples')

interface SampleFile {
  scenario: string
  description: string
  calls: Array<{ method: 'speak' | 'stop'; input?: SpeakInput }>
  expectedEffectiveInput?: { emotion: AvatarEmotion; action: AvatarAction }
  expectedEvents: AvatarPlaybackEvent[]
}

// 样例只描述调用与期望事件，不包含注入指令；播放失败（03）由测试按场景注入。
// 03 的 requestId 是固定示意值，Mock 默认生成随机本地 ID，故注入确定性工厂对齐。
const FAILURE_INJECTION: Record<string, MockAvatarOptions> = {
  '03-error-fallback.json': {
    shouldFail: () => ({}),
    requestIdFactory: () => 'req_6f2a91c4',
  },
}

const sampleFiles = readdirSync(samplesDir)
  .filter((name) => name.endsWith('.json'))
  .sort()

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('契约样例回放（packages/contracts/avatar/samples）', () => {
  it('样例目录非空', () => {
    expect(sampleFiles.length).toBeGreaterThan(0)
  })

  for (const file of sampleFiles) {
    const sample = JSON.parse(readFileSync(resolve(samplesDir, file), 'utf8')) as SampleFile

    it(`${file}：${sample.scenario}`, () => {
      const options: MockAvatarOptions = { timing: () => 1000, ...FAILURE_INJECTION[file] }
      const controller = createMockAvatarController(options)
      const events: AvatarPlaybackEvent[] = []
      controller.subscribe((event) => {
        events.push(event)
      })

      // 样例建模的是同步调用序列：先执行完全部调用，再统一推进计时。
      for (const call of sample.calls) {
        if (call.method === 'speak') {
          if (call.input === undefined) {
            throw new Error(`样例 ${file} 的 speak 调用缺少 input`)
          }
          controller.speak(call.input)
        } else {
          controller.stop()
        }
      }
      vi.advanceTimersByTime(60_000)

      expect(events).toEqual(sample.expectedEvents)

      if (sample.expectedEffectiveInput !== undefined) {
        const snapshot = controller.getPlaybackSnapshot()
        expect(snapshot.lastUtterance?.emotion).toBe(sample.expectedEffectiveInput.emotion)
        expect(snapshot.lastUtterance?.action).toBe(sample.expectedEffectiveInput.action)
      }
    })
  }
})
