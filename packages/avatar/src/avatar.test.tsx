import { act, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Avatar } from './avatar'
import { createMockAvatarController } from './mock-avatar-controller'
import type { SpeakInput } from './types'

const input: SpeakInput = {
  utteranceId: 'utt_view_0001',
  text: '这是一段要在组件中展示的回答。',
  emotion: 'encouraging',
  action: 'nod',
}

describe('<Avatar />（2D Mock 组件）', () => {
  it('常驻 Mock 标识，初始状态为空闲', () => {
    const controller = createMockAvatarController()
    render(<Avatar controller={controller} />)

    expect(screen.getByRole('note').textContent).toContain('Mock')
    expect(screen.getByText('状态：空闲')).toBeTruthy()
  })

  it('speak 后展示播报中状态、降级后 metadata 与播报文本', () => {
    const controller = createMockAvatarController({ timing: () => 100_000 })
    render(<Avatar controller={controller} />)

    act(() => {
      controller.speak(input)
    })

    expect(screen.getByText('状态：播报中')).toBeTruthy()
    expect(screen.getByText(/情绪：鼓励/)).toBeTruthy()
    expect(screen.getByText(/动作：点头/)).toBeTruthy()
    expect(screen.getByTestId('avatar-text').textContent).toBe(input.text)
  })

  it('播放失败时展示错误提示且文字回答继续保留', () => {
    const controller = createMockAvatarController({ shouldFail: () => ({}) })
    render(<Avatar controller={controller} />)

    act(() => {
      controller.speak(input)
    })

    expect(screen.getByRole('alert').textContent).toContain('播放失败')
    expect(screen.getByRole('alert').textContent).toContain('AVATAR_PLAYBACK_FAILED')
    // 文字降级路径：error 状态下文本区保留
    expect(screen.getByTestId('avatar-text').textContent).toBe(input.text)
  })

  it('主动停止后回到空闲，文字回答继续保留', () => {
    const controller = createMockAvatarController({ timing: () => 100_000 })
    render(<Avatar controller={controller} />)

    act(() => {
      controller.speak(input)
    })
    act(() => {
      controller.stop()
    })

    expect(screen.getByText('状态：空闲')).toBeTruthy()
    expect(screen.getByTestId('avatar-text').textContent).toBe(input.text)
  })
})
