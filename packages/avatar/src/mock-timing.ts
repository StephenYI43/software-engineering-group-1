/**
 * Mock 播报时长策略。
 *
 * 这是**实现细节，不是契约承诺**：契约只保证事件语义，不约束时长。
 * 默认按文本长度模拟：300ms 基础 + 每字 70ms，夹在 [600, 8000]ms。
 * 演示与评测记录须说明这是 Mock 计时，不代表真实 TTS 速率。
 */
export const DEFAULT_MOCK_TIMING = {
  baseMs: 300,
  perCharMs: 70,
  minMs: 600,
  maxMs: 8000,
} as const

export type PlaybackTiming = (text: string) => number

export const defaultPlaybackTiming: PlaybackTiming = (text) => {
  const { baseMs, perCharMs, minMs, maxMs } = DEFAULT_MOCK_TIMING
  return Math.min(maxMs, Math.max(minMs, baseMs + perCharMs * text.length))
}
