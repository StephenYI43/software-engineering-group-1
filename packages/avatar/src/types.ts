/**
 * 数字人播报契约的类型镜像。
 *
 * 唯一来源是 `packages/contracts/avatar/avatar-controller.md`（PR #51 冻结）。
 * 此处为手写镜像；契约与实现之间的漂移由 `contract-samples.test.ts` 的
 * 样例回放测试拦截。事件 `type` 取值是冻结字符串，不得改动。
 */

export type AvatarEmotion = 'neutral' | 'encouraging' | 'thinking' | 'celebrating'

export type AvatarAction = 'idle' | 'nod' | 'point' | 'write'

export type AvatarPlaybackStatus = 'idle' | 'speaking' | 'error'

export interface SpeakInput {
  /** 本次播报标识：由调用方（M2）为每次播报生成；重新播报必须使用新 ID。 */
  utteranceId: string
  /** 要播报的完整文本，长度 ≥ 1；只应是 tutoring SSE completed 的完整回答。 */
  text: string
  /** 数字人情绪；不在枚举内的取值降级为 neutral（契约「降级规则」）。 */
  emotion: AvatarEmotion
  /** 数字人动作；不在枚举内的取值降级为 idle（契约「降级规则」）。 */
  action: AvatarAction
}

/** 契约错误结构：code / message / requestId / details。 */
export interface AvatarError {
  code: string
  message: string
  requestId: string
  details: Record<string, unknown>
}

export type AvatarPlaybackStoppedReason = 'client_stop' | 'replaced'

export type AvatarPlaybackEvent =
  | { type: 'avatar_playback_started'; utteranceId: string }
  | { type: 'avatar_playback_completed'; utteranceId: string }
  | { type: 'avatar_playback_stopped'; utteranceId: string; reason: AvatarPlaybackStoppedReason }
  | { type: 'avatar_playback_error'; utteranceId: string; error: AvatarError }

export interface AvatarController {
  speak(input: SpeakInput): void
  stop(utteranceId?: string): void
  getStatus(): AvatarPlaybackStatus
  subscribe(listener: (event: AvatarPlaybackEvent) => void): () => void
}

export const AVATAR_EMOTIONS: readonly AvatarEmotion[] = [
  'neutral',
  'encouraging',
  'thinking',
  'celebrating',
]

export const AVATAR_ACTIONS: readonly AvatarAction[] = ['idle', 'nod', 'point', 'write']

/** 运行期守卫：供降级规则判定「字符串但不在枚举内」的脏数据。 */
export function isAvatarEmotion(value: unknown): value is AvatarEmotion {
  return typeof value === 'string' && (AVATAR_EMOTIONS as readonly string[]).includes(value)
}

/** 运行期守卫：供降级规则判定「字符串但不在枚举内」的脏数据。 */
export function isAvatarAction(value: unknown): value is AvatarAction {
  return typeof value === 'string' && (AVATAR_ACTIONS as readonly string[]).includes(value)
}
