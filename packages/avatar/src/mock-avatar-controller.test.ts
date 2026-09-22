import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AvatarInputError, createMockAvatarController } from './mock-avatar-controller'
import type { MockAvatarController } from './mock-avatar-controller'
import { defaultPlaybackTiming } from './mock-timing'
import type { AvatarAction, AvatarEmotion, AvatarPlaybackEvent, SpeakInput } from './types'

function makeInput(overrides: Partial<SpeakInput> = {}): SpeakInput {
  return {
    utteranceId: 'utt_test_0001',
    text: '这是一段测试播报文本。',
    emotion: 'neutral',
    action: 'idle',
    ...overrides,
  }
}

function createEventLog(controller: MockAvatarController): AvatarPlaybackEvent[] {
  const events: AvatarPlaybackEvent[] = []
  controller.subscribe((event) => {
    events.push(event)
  })
  return events
}

/** 运行时校验用例需要绕过编译期类型，统一在这里断言一次。 */
function speakRaw(controller: MockAvatarController, value: unknown): void {
  controller.speak(value as SpeakInput)
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('正常播报', () => {
  it('started 同步即发，计时到期后恰一次 completed，状态回到 idle', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    expect(controller.getStatus()).toBe('speaking')
    expect(events).toEqual([{ type: 'avatar_playback_started', utteranceId: 'utt_test_0001' }])

    vi.advanceTimersByTime(1000)
    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_test_0001' },
      { type: 'avatar_playback_completed', utteranceId: 'utt_test_0001' },
    ])
    expect(controller.getStatus()).toBe('idle')
  })

  it('默认时长策略：300ms 基础 + 每字 70ms，夹在 [600, 8000]', () => {
    expect(defaultPlaybackTiming('')).toBe(600)
    expect(defaultPlaybackTiming('短')).toBe(600)
    expect(defaultPlaybackTiming('一二三四五六七八九十')).toBe(1000)
    expect(defaultPlaybackTiming('长'.repeat(1000))).toBe(8000)
  })

  it('控制器按默认时长策略到期后发出 completed', () => {
    const controller = createMockAvatarController()
    const events = createEventLog(controller)
    const text = '这是一段测试播报文本。'

    controller.speak(makeInput({ text }))
    const duration = defaultPlaybackTiming(text)
    vi.advanceTimersByTime(duration - 1)
    expect(events).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(events).toHaveLength(2)
    expect(events[1]).toEqual({ type: 'avatar_playback_completed', utteranceId: 'utt_test_0001' })
  })
})

describe('主动停止与 stop 幂等', () => {
  it('播报中 stop 产生恰一次 stopped(client_stop)，此后不再有任何事件', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    controller.stop()
    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_test_0001' },
      { type: 'avatar_playback_stopped', utteranceId: 'utt_test_0001', reason: 'client_stop' },
    ])
    expect(controller.getStatus()).toBe('idle')

    vi.advanceTimersByTime(10000)
    expect(events).toHaveLength(2)
  })

  it('重复 stop、无播报时 stop、completed 后 stop 都是 no-op', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.stop()
    expect(events).toHaveLength(0)

    controller.speak(makeInput())
    controller.stop()
    controller.stop()
    expect(events).toHaveLength(2)

    controller.speak(makeInput({ utteranceId: 'utt_test_0002' }))
    vi.advanceTimersByTime(1000)
    const countAfterCompleted = events.length
    controller.stop()
    expect(events).toHaveLength(countAfterCompleted)
  })

  it('stop(utteranceId) 只停止匹配的播报，不匹配时不误停', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    controller.stop('utt_other')
    expect(events).toHaveLength(1)
    expect(controller.getStatus()).toBe('speaking')

    controller.stop('utt_test_0001')
    expect(events).toHaveLength(2)
    expect(events[1]).toEqual({
      type: 'avatar_playback_stopped',
      utteranceId: 'utt_test_0001',
      reason: 'client_stop',
    })
  })
})

describe('新播报替换旧播报', () => {
  it('旧播报恰一次 stopped(replaced) 且先于新 started，旧 ID 此后零事件', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput({ utteranceId: 'utt_a' }))
    controller.speak(makeInput({ utteranceId: 'utt_b' }))
    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_a' },
      { type: 'avatar_playback_stopped', utteranceId: 'utt_a', reason: 'replaced' },
      { type: 'avatar_playback_started', utteranceId: 'utt_b' },
    ])

    vi.advanceTimersByTime(1000)
    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_a' },
      { type: 'avatar_playback_stopped', utteranceId: 'utt_a', reason: 'replaced' },
      { type: 'avatar_playback_started', utteranceId: 'utt_b' },
      { type: 'avatar_playback_completed', utteranceId: 'utt_b' },
    ])
  })
})

describe('播放失败与文字降级', () => {
  it('失败注入：started 后发出 avatar_playback_error，error 四字段齐全', () => {
    const controller = createMockAvatarController({ shouldFail: () => ({}) })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: 'avatar_playback_started', utteranceId: 'utt_test_0001' })

    const errorEvent = events[1]
    if (errorEvent?.type !== 'avatar_playback_error') {
      throw new Error('期望第二个事件是 avatar_playback_error')
    }
    expect(errorEvent.utteranceId).toBe('utt_test_0001')
    expect(errorEvent.error.code).toBe('AVATAR_PLAYBACK_FAILED')
    expect(errorEvent.error.message).toBe('播放失败，文字回答已保留')
    expect(errorEvent.error.requestId).toMatch(/^req_[0-9a-f]{12}$/)
    expect(errorEvent.error.details).toEqual({})
    expect(controller.getStatus()).toBe('error')
  })

  it('失败注入支持自定义 code/message/details 与 requestIdFactory', () => {
    const controller = createMockAvatarController({
      shouldFail: () => ({ code: 'X_CUSTOM', message: '自定义失败', details: { at: 't0' } }),
      requestIdFactory: () => 'req_fixed00001',
      timing: () => 1000,
    })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    const errorEvent = events[1]
    if (errorEvent?.type !== 'avatar_playback_error') {
      throw new Error('期望第二个事件是 avatar_playback_error')
    }
    expect(errorEvent.error).toEqual({
      code: 'X_CUSTOM',
      message: '自定义失败',
      requestId: 'req_fixed00001',
      details: { at: 't0' },
    })
  })

  it('error 状态下 stop 是 no-op，新 speak 正常开始播报', () => {
    const controller = createMockAvatarController({
      shouldFail: (input) => (input.utteranceId === 'utt_fail' ? {} : null),
      timing: () => 1000,
    })
    const events = createEventLog(controller)

    controller.speak(makeInput({ utteranceId: 'utt_fail' }))
    const countAfterError = events.length
    controller.stop()
    expect(events).toHaveLength(countAfterError)

    controller.speak(makeInput({ utteranceId: 'utt_ok' }))
    vi.advanceTimersByTime(1000)
    expect(events[countAfterError]).toEqual({
      type: 'avatar_playback_started',
      utteranceId: 'utt_ok',
    })
    expect(events[events.length - 1]).toEqual({
      type: 'avatar_playback_completed',
      utteranceId: 'utt_ok',
    })
    expect(controller.getStatus()).toBe('idle')
  })

  it('播报失败后文字保留在快照中（文字降级路径）', () => {
    const controller = createMockAvatarController({ shouldFail: () => ({}) })
    controller.speak(makeInput({ text: '这段文字必须在失败后保留。' }))
    expect(controller.getPlaybackSnapshot().lastUtterance?.text).toBe('这段文字必须在失败后保留。')
  })
})

describe('非法 metadata 降级', () => {
  it('不在枚举内的 emotion/action 降级为 neutral/idle，播报照常完成', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    speakRaw(
      controller,
      makeInput({ emotion: 'excited' as AvatarEmotion, action: 'dance' as AvatarAction }),
    )
    vi.advanceTimersByTime(1000)

    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_test_0001' },
      { type: 'avatar_playback_completed', utteranceId: 'utt_test_0001' },
    ])
    const snapshot = controller.getPlaybackSnapshot()
    expect(snapshot.lastUtterance?.emotion).toBe('neutral')
    expect(snapshot.lastUtterance?.action).toBe('idle')
    expect(snapshot.lastUtterance?.text).toBe('这是一段测试播报文本。')
  })
})

describe('结构性入参校验', () => {
  it.each([
    ['text 为空', makeInput({ text: '' })],
    ['text 非字符串', { ...makeInput(), text: 123 }],
    ['utteranceId 为空', makeInput({ utteranceId: '' })],
    ['缺 utteranceId', { text: 'x', emotion: 'neutral', action: 'idle' }],
    ['emotion 非字符串', { ...makeInput(), emotion: 123 }],
    ['缺 action', { utteranceId: 'utt_x', text: 'x', emotion: 'neutral' }],
    ['入参不是对象', null],
  ])('%s：同步抛 AvatarInputError，零事件、状态不变', (_label, badInput) => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    expect(() => {
      speakRaw(controller, badInput)
    }).toThrow(AvatarInputError)
    expect(events).toHaveLength(0)
    expect(controller.getStatus()).toBe('idle')
  })

  it('utteranceId 与已终止播报重复时抛错', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    controller.speak(makeInput())
    vi.advanceTimersByTime(1000)

    expect(() => {
      controller.speak(makeInput())
    }).toThrow(AvatarInputError)
    expect(controller.getStatus()).toBe('idle')
  })

  it('utteranceId 与进行中播报重复时抛错，原播报不受影响', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput())
    expect(() => {
      controller.speak(makeInput())
    }).toThrow(AvatarInputError)

    vi.advanceTimersByTime(1000)
    expect(events).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_test_0001' },
      { type: 'avatar_playback_completed', utteranceId: 'utt_test_0001' },
    ])
  })
})

describe('终止事件互斥', () => {
  it('终止之后旧 utteranceId 不再产生任何事件', () => {
    const controller = createMockAvatarController({ timing: () => 1000 })
    const events = createEventLog(controller)

    controller.speak(makeInput({ utteranceId: 'utt_old' }))
    controller.stop()

    controller.speak(makeInput({ utteranceId: 'utt_new' }))
    vi.advanceTimersByTime(100000)
    controller.stop()
    controller.stop('utt_old')

    const oldEvents = events.filter((e) => e.utteranceId === 'utt_old')
    expect(oldEvents).toEqual([
      { type: 'avatar_playback_started', utteranceId: 'utt_old' },
      { type: 'avatar_playback_stopped', utteranceId: 'utt_old', reason: 'client_stop' },
    ])
  })
})
