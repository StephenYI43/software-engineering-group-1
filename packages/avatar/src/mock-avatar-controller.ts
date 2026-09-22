import { defaultPlaybackTiming } from './mock-timing'
import type { PlaybackTiming } from './mock-timing'
import { isAvatarAction, isAvatarEmotion } from './types'
import type {
  AvatarAction,
  AvatarController,
  AvatarEmotion,
  AvatarError,
  AvatarPlaybackEvent,
  AvatarPlaybackStatus,
  SpeakInput,
} from './types'

/**
 * 结构性入参错误（调用方缺陷）：`speak` 同步抛出，不产生任何事件。
 * 区别于非法 emotion/action 取值——后者只降级，不抛错（契约「降级规则」）。
 */
export class AvatarInputError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AvatarInputError'
  }
}

/** 失败注入规格：仅测试/演示使用；未提供的字段由控制器按契约默认补齐。 */
export interface MockFailureSpec {
  code?: string
  message?: string
  details?: Record<string, unknown>
}

export interface MockAvatarOptions {
  /** 播报时长策略，默认按文本长度模拟（见 mock-timing.ts，实现细节非契约承诺）。 */
  timing?: PlaybackTiming
  /** 失败注入：返回非 null 时，本次播报在 started 后以 avatar_playback_error 终止。默认永不失败。 */
  shouldFail?: (input: SpeakInput) => MockFailureSpec | null
  /**
   * error.requestId 的生成器。默认生成 `req_` + 随机 hex 的**本地追踪 ID**：
   * 仅供前端日志关联，不代表服务端请求；ID 形态待 M1 统一约定（契约「utteranceId 与 requestId」）。
   */
  requestIdFactory?: () => string
}

/** 最近一次被接受的播报（含已终止）：供文字区在播报结束后保留展示（文字降级路径）。 */
export interface LastUtterance {
  utteranceId: string
  text: string
  emotion: AvatarEmotion
  action: AvatarAction
}

export interface PlaybackSnapshot {
  status: AvatarPlaybackStatus
  lastUtterance: LastUtterance | null
  /** 最近一次播放错误（历史信息）；组件只在 status === 'error' 时展示。 */
  lastError: AvatarError | null
}

/**
 * Mock 控制器在契约接口之上的附加能力（增量，不改变契约四方法）。
 * 组件经它获取契约事件流之外的展示数据（effective metadata 与保留文本）。
 */
export interface MockAvatarController extends AvatarController {
  getPlaybackSnapshot(): PlaybackSnapshot
}

type PlaybackState =
  | { status: 'idle' }
  | {
      status: 'speaking'
      utteranceId: string
      timer: ReturnType<typeof setTimeout> | null
    }
  | { status: 'error' }

const DEFAULT_FAILURE_CODE = 'AVATAR_PLAYBACK_FAILED'
const DEFAULT_FAILURE_MESSAGE = '播放失败，文字回答已保留'

const defaultRequestIdFactory = (): string => {
  const bytes = new Uint8Array(6)
  crypto.getRandomValues(bytes)
  return 'req_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * 创建数字人 Mock 控制器。
 *
 * **Mock 实现（AGENTS.md:8 要求明确标记）**：不接入真实 TTS/ASR 或任何外部语音服务，
 * 用 setTimeout 按文本长度模拟播报时长，只保证契约的事件语义
 * （packages/contracts/avatar/avatar-controller.md）。
 */
export function createMockAvatarController(options: MockAvatarOptions = {}): MockAvatarController {
  const timing = options.timing ?? defaultPlaybackTiming
  const shouldFail = options.shouldFail ?? (() => null)
  const requestIdFactory = options.requestIdFactory ?? defaultRequestIdFactory

  let state: PlaybackState = { status: 'idle' }
  /** 已终止的 utteranceId：重复使用该 ID 属于调用方缺陷，speak 同步抛错。 */
  const terminatedIds = new Set<string>()
  const listeners = new Set<(event: AvatarPlaybackEvent) => void>()
  let lastUtterance: LastUtterance | null = null
  let lastError: AvatarError | null = null

  const emit = (event: AvatarPlaybackEvent): void => {
    for (const listener of listeners) {
      listener(event)
    }
  }

  const assertSpeakInput = (input: SpeakInput): void => {
    if (input === null || typeof input !== 'object') {
      throw new AvatarInputError('speak 入参必须是对象')
    }
    const { utteranceId, text, emotion, action } = input
    if (typeof utteranceId !== 'string' || utteranceId.length === 0) {
      throw new AvatarInputError('utteranceId 缺失或为空')
    }
    if (
      (state.status === 'speaking' && state.utteranceId === utteranceId) ||
      terminatedIds.has(utteranceId)
    ) {
      throw new AvatarInputError(`utteranceId 重复使用：${utteranceId}`)
    }
    if (typeof text !== 'string' || text.length === 0) {
      throw new AvatarInputError('text 缺失或为空')
    }
    // 类型错误（含缺失）是缺陷，抛错；字符串但不在枚举内不是缺陷，走降级。
    if (typeof emotion !== 'string' || typeof action !== 'string') {
      throw new AvatarInputError('emotion/action 类型错误')
    }
  }

  const buildAvatarError = (spec: MockFailureSpec): AvatarError => ({
    code: spec.code ?? DEFAULT_FAILURE_CODE,
    message: spec.message ?? DEFAULT_FAILURE_MESSAGE,
    requestId: requestIdFactory(),
    details: spec.details ?? {},
  })

  const speak = (input: SpeakInput): void => {
    assertSpeakInput(input)

    // 替换规则：旧播报恰好一次 stopped(replaced)，且先于新 started 分发。
    if (state.status === 'speaking') {
      const replacedId = state.utteranceId
      if (state.timer !== null) {
        clearTimeout(state.timer)
      }
      terminatedIds.add(replacedId)
      state = { status: 'idle' }
      emit({ type: 'avatar_playback_stopped', utteranceId: replacedId, reason: 'replaced' })
    }

    // 降级只影响展示元数据：不改写调用方入参，text 原样保留。
    const effective: LastUtterance = {
      utteranceId: input.utteranceId,
      text: input.text,
      emotion: isAvatarEmotion(input.emotion) ? input.emotion : 'neutral',
      action: isAvatarAction(input.action) ? input.action : 'idle',
    }
    lastUtterance = effective

    state = { status: 'speaking', utteranceId: input.utteranceId, timer: null }
    emit({ type: 'avatar_playback_started', utteranceId: input.utteranceId })

    const failure = shouldFail(input)
    if (failure !== null) {
      const error = buildAvatarError(failure)
      terminatedIds.add(input.utteranceId)
      state = { status: 'error' }
      lastError = error
      emit({ type: 'avatar_playback_error', utteranceId: input.utteranceId, error })
      return
    }

    const utteranceId = input.utteranceId
    state = {
      status: 'speaking',
      utteranceId,
      timer: setTimeout(() => {
        // 防御：stop/替换已 clearTimeout，这里再确认身份，保证终止事件互斥。
        if (state.status !== 'speaking' || state.utteranceId !== utteranceId) {
          return
        }
        terminatedIds.add(utteranceId)
        state = { status: 'idle' }
        emit({ type: 'avatar_playback_completed', utteranceId })
      }, timing(input.text)),
    }
  }

  const stop = (utteranceId?: string): void => {
    // 幂等：已终止（completed/stopped/error）或本无播报时是 no-op，不产生新事件。
    if (state.status !== 'speaking') {
      return
    }
    // stop(utteranceId) 仅当该 ID 仍在播报时才停止，避免替换竞态误停新播报。
    if (utteranceId !== undefined && utteranceId !== state.utteranceId) {
      return
    }
    const stoppedId = state.utteranceId
    if (state.timer !== null) {
      clearTimeout(state.timer)
    }
    terminatedIds.add(stoppedId)
    state = { status: 'idle' }
    emit({ type: 'avatar_playback_stopped', utteranceId: stoppedId, reason: 'client_stop' })
  }

  const getStatus = (): AvatarPlaybackStatus => state.status

  const getPlaybackSnapshot = (): PlaybackSnapshot => ({
    status: state.status,
    lastUtterance,
    lastError,
  })

  const subscribe = (listener: (event: AvatarPlaybackEvent) => void): (() => void) => {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }

  return { speak, stop, getStatus, getPlaybackSnapshot, subscribe }
}
