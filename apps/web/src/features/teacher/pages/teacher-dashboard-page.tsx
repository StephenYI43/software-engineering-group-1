import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'
import { Card, ErrorState, LoadingState, MockDataBadge } from '@pkg/ui'
import { TeacherRequestError, getClassOverview } from '../api/class-overview-client'
import type {
  ChapterWeakPoint,
  ClassOverview,
  MetricNumber,
  QuestionTypeWeakPoint,
  StudentOverview,
} from '../types'
import '../teacher-dashboard.css'

/**
 * 教师端「班级概览」页（M6 / S1）。
 *
 * 数据来自 M6 自己的统计契约
 * （`packages/contracts/analytics/statistics-api.md`，PR #37）；后端实现在 PR #38。
 *
 * 页面遵循契约的三条展示约束：
 * 1. **未知不显示 0**：周期内无事件的学生显示「暂无数据」，而不是「0 分钟」；
 * 2. **三态必须区分**：「暂无数据」（无事件）/「本周期无错题」（有数据但没错题）/
 *    正常值——把它们混为一谈会给出错误结论；
 * 3. **样本量与口径必须可见**：薄弱点标注样本量，样本不足的条目显式提示；
 *    时长标注算法口径，避免把过渡口径当成测量值。
 *
 * 权限不在本页：教师仅见授权班级由 M1 的鉴权层与 API 层保证，
 * 页面不自行过滤权限、也不靠隐藏菜单表达权限（`docs/code-standards.md:104`）。
 */

/** 班级选择器待 M1 的身份/权限接口接入，先固定示意班级。 */
const PLACEHOLDER_CLASS_ID = 'class_mock_c01'

const UNKNOWN_LABEL = '暂无数据'
const NO_MISTAKE_LABEL = '本周期无错题'

type OverviewState =
  | { status: 'loading' }
  | { status: 'error'; error: TeacherRequestError }
  | { status: 'ready'; overview: ClassOverview; isFixture: boolean }

function toRequestError(thrown: unknown): TeacherRequestError {
  if (thrown instanceof TeacherRequestError) return thrown
  return new TeacherRequestError('请求失败，请稍后重试')
}

/**
 * 加载班级概览。
 *
 * 刻意不复用 `app/async-content` 的 `useAsyncData`：它内部依赖
 * `features/student/api/http-client`，教师端复用即等于依赖学生端实现
 * （该耦合已在 PR #36 评审中提出；M2 若把它提到共享层，本 hook 可改为复用）。
 */
function useClassOverview(classId: string, demoSearch: string): OverviewState {
  const [state, setState] = useState<OverviewState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    getClassOverview(classId, demoSearch)
      .then((overview) => {
        if (cancelled) return
        setState({ status: 'ready', overview, isFixture: '_fixture' in overview })
      })
      .catch((thrown: unknown) => {
        if (cancelled) return
        setState({ status: 'error', error: toRequestError(thrown) })
      })
    return () => {
      cancelled = true
    }
  }, [classId, demoSearch])

  return state
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.round(seconds / 60)} 分钟`
}

function formatInstant(instant: string, timeZone: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(instant))
}

function MetricText({
  metric,
  format,
  algorithm,
}: {
  metric: MetricNumber
  format: (value: number) => string
  algorithm?: (name: string) => string
}) {
  if (metric.state === 'unknown') {
    return <span className="teacher-metric teacher-metric--unknown">{UNKNOWN_LABEL}</span>
  }
  const suffix =
    algorithm !== undefined && 'algorithm' in metric ? `（${algorithm(metric.algorithm)}）` : ''
  return (
    <span className="teacher-metric">
      {format(metric.value)}
      {suffix}
    </span>
  )
}

function WeakPointRows({ items }: { items: Array<QuestionTypeWeakPoint | ChapterWeakPoint> }) {
  if (items.length === 0) {
    return <p className="teacher-section__empty">{NO_MISTAKE_LABEL}</p>
  }
  return (
    <ul className="teacher-weak-points">
      {items.map((item) => (
        <li key={item.key}>
          <span className="teacher-weak-points__name">{item.label ?? item.key}</span>{' '}
          {'errorRate' in item ? (
            <span>错误率 {Math.round(item.errorRate * 100)}%</span>
          ) : (
            <span>
              错题 {item.mistakeCount} · 已解决 {item.resolvedCount}
            </span>
          )}{' '}
          <span className="teacher-weak-points__sample">样本 {item.sampleSize}</span>
          {item.insufficientSample && (
            <span className="teacher-weak-points__flag">样本不足，不足以据此下结论</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function WeakestChapter({ student }: { student: StudentOverview }) {
  if (student.dataState === 'unknown') return <span>{UNKNOWN_LABEL}</span>
  if (student.weakestChapter === null) return <span>{NO_MISTAKE_LABEL}</span>
  const chapter = student.weakestChapter
  return (
    <span>
      {chapter.label ?? chapter.key}（错题 {chapter.mistakeCount}，样本 {chapter.sampleSize}）
    </span>
  )
}

function DashboardBody({ overview, isFixture }: { overview: ClassOverview; isFixture: boolean }) {
  const { period, summary, weakPoints, students } = overview
  const { coverage } = summary

  return (
    <>
      {isFixture && <MockDataBadge source="取自 M6 统计契约样例（合成数据）" />}

      <p className="teacher-dashboard__meta">
        统计周期 {formatInstant(period.from, period.timezone)} ~{' '}
        {formatInstant(period.to, period.timezone)}（{period.timezone}，共 {period.days} 天）
      </p>
      <p className="teacher-dashboard__meta">
        {overview.dataThrough === null
          ? '尚未消费任何学习事件，全班数据均不可用'
          : `数据截止 ${formatInstant(overview.dataThrough, period.timezone)}`}
      </p>
      <p className="teacher-dashboard__meta">
        覆盖情况：{coverage.studentCount} 名学生中 {coverage.studentsWithData} 名有数据、
        {coverage.studentsWithoutData} 名无数据。总时长为<strong>有数据学生</strong>之和，
        不代表全班总量。
      </p>

      <div className="teacher-dashboard__cards">
        <Card title="班级学习时长">
          <MetricText
            metric={summary.totalDurationSeconds}
            format={formatDuration}
            algorithm={(name) => (name === 'session_inference_v1' ? '会话推断口径' : name)}
          />
        </Card>
        <Card title="活跃人数">
          <MetricText metric={summary.activeStudentCount} format={(value) => `${value} 人`} />
        </Card>
        <Card title="提交数">
          <MetricText metric={summary.submissionCount} format={(value) => `${value} 次`} />
        </Card>
      </div>

      <Card title="答题薄弱点">
        <h3>按题型</h3>
        <WeakPointRows items={weakPoints.byQuestionType} />
        <h3>按章节</h3>
        <WeakPointRows items={weakPoints.byChapter} />
        <p className="teacher-section__note">
          条目按样本量优先排序，样本不足的条目不会因为错误率高而排在前面。
        </p>
      </Card>

      <Card title="学生明细">
        <table className="teacher-students">
          <thead>
            <tr>
              <th>学生</th>
              <th>学习时长</th>
              <th>提交数</th>
              <th>最弱章节</th>
            </tr>
          </thead>
          <tbody>
            {students.map((student) => (
              <tr key={student.userId}>
                <td>{student.displayName ?? student.userId}</td>
                <td>
                  <MetricText metric={student.durationSeconds} format={formatDuration} />
                </td>
                <td>
                  <MetricText metric={student.submissionCount} format={(value) => `${value} 次`} />
                </td>
                <td>
                  <WeakestChapter student={student} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}

export function TeacherDashboardPage() {
  const location = useLocation()
  const state = useClassOverview(PLACEHOLDER_CLASS_ID, location.search)

  return (
    <div className="teacher-dashboard">
      <h1>班级概览</h1>
      <p className="teacher-dashboard__hint">
        班级选择器待 M1 的身份/权限接口接入，当前固定为示意班级 {PLACEHOLDER_CLASS_ID}。
      </p>
      {state.status === 'loading' && <LoadingState />}
      {state.status === 'error' && (
        <ErrorState message={state.error.message} requestId={state.error.requestId} />
      )}
      {state.status === 'ready' && (
        <DashboardBody overview={state.overview} isFixture={state.isFixture} />
      )}
    </div>
  )
}
