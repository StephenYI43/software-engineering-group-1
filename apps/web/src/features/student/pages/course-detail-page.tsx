import { Link, useLocation, useParams } from 'react-router'
import { Card, EmptyState, MockDataBadge } from '@pkg/ui'
import { AsyncContent, useAsyncData } from '../../../app/async-content'
import { getChapters, getCourse } from '../api/courses-client'
import { parseScenario } from '../mocks'
import { subjectLabel } from '../subject-label'
import type { Chapter } from '../types'

function ChapterList({ chapters }: { chapters: Chapter[] }) {
  if (chapters.length === 0) {
    return <EmptyState title="本课程还没有章节" />
  }
  return (
    <ol className="chapter-list">
      {chapters.map((chapter) => (
        <li key={chapter.id} className="chapter-list__item">
          <span className="chapter-list__order">{chapter.order}</span>
          <div>
            <p className="chapter-list__title">{chapter.title}</p>
            {chapter.description !== null && (
              <p className="chapter-list__meta">{chapter.description}</p>
            )}
            {/* documentId 只是引用，课件内容由 M3 知识库托管，前端不展示其内容 */}
            {chapter.documentId !== null && <p className="chapter-list__meta">已关联课件</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>()
  const location = useLocation()
  const scenario = parseScenario(location.search)
  const id = courseId ?? ''

  // 两个请求各自独立处理加载与错误——章节失败不应把课程信息一起挡掉。
  const courseState = useAsyncData(`course:${id}:${scenario}`, () => getCourse(id, scenario))
  const chaptersState = useAsyncData(`chapters:${id}:${scenario}`, () => getChapters(id, scenario))

  return (
    <div>
      <p>
        <Link to="/courses">← 返回课程列表</Link>
      </p>
      <MockDataBadge source="取自课程契约样例" />

      <AsyncContent state={courseState}>
        {(course) => (
          <div>
            <h1>{course.title}</h1>
            <p className="course-card__meta">
              学科：{subjectLabel(course.subject)}
              {course.teacherName !== null && ` · 主讲：${course.teacherName}`}
            </p>
            {course.description !== null && <p>{course.description}</p>}
          </div>
        )}
      </AsyncContent>

      <Card title="章节">
        <AsyncContent state={chaptersState}>
          {(page) => <ChapterList chapters={page.items} />}
        </AsyncContent>
      </Card>
    </div>
  )
}
