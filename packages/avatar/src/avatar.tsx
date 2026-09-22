import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { MockAvatarController } from './mock-avatar-controller'
import type { AvatarAction, AvatarEmotion, AvatarPlaybackStatus } from './types'

const STATUS_LABEL: Record<AvatarPlaybackStatus, string> = {
  idle: '空闲',
  speaking: '播报中',
  error: '错误',
}

const EMOTION_LABEL: Record<AvatarEmotion, string> = {
  neutral: '中性',
  encouraging: '鼓励',
  thinking: '思考',
  celebrating: '庆祝',
}

const ACTION_LABEL: Record<AvatarAction, string> = {
  idle: '无动作',
  nod: '点头',
  point: '指向内容区',
  write: '书写板书',
}

// 关键视觉结构用内联样式：Mock 组件可能先在无宿主全局 CSS 的环境（如独立演示页）渲染，
// 不能依赖 apps/web 的 global.css；className 留给宿主做覆盖定制。
const containerStyle: CSSProperties = {
  display: 'inline-block',
  maxWidth: 360,
  padding: 12,
  border: '1px solid #cbd5e1',
  borderRadius: 8,
  fontFamily: 'system-ui, sans-serif',
}

const badgeStyle: CSSProperties = {
  display: 'inline-block',
  marginBottom: 8,
  padding: '2px 8px',
  borderRadius: 4,
  background: '#fef3c7',
  color: '#92400e',
  fontSize: 12,
}

const figureStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 96,
  height: 96,
  marginBottom: 8,
  border: '2px dashed #94a3b8',
  borderRadius: '50%',
  color: '#64748b',
  fontSize: 12,
  textAlign: 'center',
}

const errorStyle: CSSProperties = {
  color: '#b91c1c',
}

export interface AvatarProps {
  controller: MockAvatarController
}

/**
 * 2D 占位数字人（Mock）。
 *
 * 当前阶段不接入真实 TTS/ASR，形象为占位渲染：展示播放状态、降级后的
 * 情绪/动作，以及**与播放状态解耦的文本区**——播报失败或被停止后文字回答
 * 继续保留（契约「语音/文字降级」）。
 * 「Mock 播报」标识常驻（AGENTS.md:8：Mock 必须明确标记）。
 */
export function Avatar({ controller }: AvatarProps) {
  const [, setVersion] = useState(0)

  useEffect(() => {
    // 事件同步分发，收到任何事件都可能改变 snapshot，触发重渲染。
    return controller.subscribe(() => {
      setVersion((v) => v + 1)
    })
  }, [controller])

  const snapshot = controller.getPlaybackSnapshot()

  return (
    <div className="avatar-mock" style={containerStyle} data-testid="avatar-mock">
      <span className="avatar-mock-badge" style={badgeStyle} role="note">
        Mock 播报 · 无真实语音
      </span>
      <div className="avatar-figure" style={figureStyle} aria-label="2D 数字人占位形象">
        2D 形象
        <br />
        占位
      </div>
      <p className="avatar-status">状态：{STATUS_LABEL[snapshot.status]}</p>
      {snapshot.lastUtterance !== null && (
        <div className="avatar-utterance">
          <p className="avatar-metadata">
            情绪：{EMOTION_LABEL[snapshot.lastUtterance.emotion]} · 动作：
            {ACTION_LABEL[snapshot.lastUtterance.action]}
          </p>
          <p className="avatar-text" data-testid="avatar-text">
            {snapshot.lastUtterance.text}
          </p>
        </div>
      )}
      {snapshot.status === 'error' && snapshot.lastError !== null && (
        <p className="avatar-error" style={errorStyle} role="alert">
          播放失败，文字回答已保留（{snapshot.lastError.code}）
        </p>
      )}
    </div>
  )
}
