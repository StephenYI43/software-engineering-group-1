export { AVATAR_ACTIONS, AVATAR_EMOTIONS, isAvatarAction, isAvatarEmotion } from './types'
export type {
  AvatarAction,
  AvatarController,
  AvatarEmotion,
  AvatarError,
  AvatarPlaybackEvent,
  AvatarPlaybackStatus,
  AvatarPlaybackStoppedReason,
  SpeakInput,
} from './types'

export { DEFAULT_MOCK_TIMING, defaultPlaybackTiming } from './mock-timing'
export type { PlaybackTiming } from './mock-timing'

export { AvatarInputError, createMockAvatarController } from './mock-avatar-controller'
export type {
  LastUtterance,
  MockAvatarController,
  MockAvatarOptions,
  MockFailureSpec,
  PlaybackSnapshot,
} from './mock-avatar-controller'

export { Avatar } from './avatar'
export type { AvatarProps } from './avatar'
