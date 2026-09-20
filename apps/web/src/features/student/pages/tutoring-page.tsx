import { Link, useLocation, useParams } from 'react-router'
import { Card, MockDataBadge } from '@pkg/ui'
import { AsyncContent, useAsyncData } from '../../../app/async-content'
import { getTutoringTurn } from '../api/tutoring-client'
import { parseScenario, parseTutoringTurnKind, type MockScenario } from '../mocks'
import type { Citation, TutoringResponse, TutoringStage } from '../types'

/**
 * 教学阶段展示名。
 *
 * `thought` 刻意译作「思路」而非「思考过程」——契约写明它是**面向学生的解题思路**，
 * 不是模型的内部推理（`tutoring-response.md`：「若后续有人想在界面上展示思考过程，
 * 那是新需求，需重新评审本契约」）。
 */
const STAGE_LABEL: Record<TutoringStage, string> = {
  thought: '思路',
  hint: '提示',
  step: '分步',
  summary: '总结',
}

const TURN_KINDS = [
  ['thought', '首轮思路'],
  ['summary', '总结'],
  ['noEvidence', '无依据'],
] as const

const SCENARIOS = [
  ['normal', '正常'],
  ['empty', '空'],
  ['error', '契约内错误'],
  ['error-raw', '非契约错误'],
  ['slow', '慢响应'],
] as const

function StageIndicator({ stage }: { stage: TutoringStage }) {
  return (
    <p className="stage-indicator" data-testid="stage">
      当前阶段：{STAGE_LABEL[stage]}
    </p>
  )
}

function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <Card title="依据">
      <ul className="citation-list" data-testid="citations">
        {citations.map((citation) => (
          <li key={citation.citationId} className="citation-list__item">
            {/* documentTitle 来自上传者，属于不可信输入；以文本节点渲染由 React 转义 */}
            <p className="citation-list__source">
              {citation.documentTitle} · 第 {citation.pageNumber} 页
            </p>
            <blockquote className="citation-list__snippet">{citation.snippet}</blockquote>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/**
 * 无依据时的说明。
 *
 * 契约不变量：`hasEvidence === false` 与 `citations` 为空数组互为充要条件。
 * 此时**不渲染引用区**，也不显示任何占位引用——「找不到依据」是正常业务结果，
 * HTTP 仍是 200（`TUTORING_NO_EVIDENCE` 不是错误），界面照常展示回答正文。
 */
function NoEvidenceNotice() {
  return (
    <Card title="依据">
      <p data-testid="no-evidence">本轮未检索到课程依据，回答中不包含引用。</p>
    </Card>
  )
}

function Answer({ response }: { response: TutoringResponse }) {
  return (
    <div>
      <StageIndicator stage={response.stage} />

      {/*
        `isMock` 是**运行时来源**标记（这一轮是否由 MockModelClient 生成），
        与「这份数据是示意数据」是两件事。前者由服务端字段驱动，后者由 _fixture 驱动。
      */}
      {response.isMock && (
        <p className="runtime-source" data-testid="runtime-source">
          本轮回答由离线假模型生成（isMock = true）
        </p>
      )}

      <Card title="回答">
        <div className="answer-content" data-testid="answer-content">
          {response.content
            .split('\n')
            .filter((line) => line !== '')
            .map((line, index) => (
              <p key={index}>{line}</p>
            ))}
        </div>
      </Card>

      {response.hasEvidence ? (
        <CitationList citations={response.citations} />
      ) : (
        <NoEvidenceNotice />
      )}

      {response.followUps.length > 0 && (
        <Card title="可以继续问">
          <ul className="follow-up-list">
            {response.followUps.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

/** 演示用的场景切换链接。保留另一半参数，只改一个。 */
function DemoSwitches({ kind, scenario }: { kind: string; scenario: MockScenario }) {
  return (
    <p className="demo-switch">
      {TURN_KINDS.map(([value, label], index) => (
        <span key={value}>
          {index > 0 && ' · '}
          <Link to={`?turn=${value}&mock=${scenario}`}>{label}</Link>
        </span>
      ))}
      {' ｜ '}
      {SCENARIOS.map(([value, label], index) => (
        <span key={value}>
          {index > 0 && ' · '}
          <Link to={`?turn=${kind}&mock=${value}`}>{label}</Link>
        </span>
      ))}
    </p>
  )
}

export function TutoringPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const scenario = parseScenario(location.search)
  const kind = parseTutoringTurnKind(location.search)

  const state = useAsyncData(`tutoring:${sessionId ?? ''}:${kind}:${scenario}`, () =>
    getTutoringTurn(kind, scenario),
  )

  return (
    <div>
      <p>
        <Link to="/courses">← 返回课程列表</Link>
      </p>
      <h1>答疑</h1>
      <MockDataBadge source="取自 tutoring 契约样例" />
      <DemoSwitches kind={kind} scenario={scenario} />
      <AsyncContent state={state}>{(response) => <Answer response={response} />}</AsyncContent>
    </div>
  )
}
