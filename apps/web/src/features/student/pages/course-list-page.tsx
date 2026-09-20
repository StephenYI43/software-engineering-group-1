import { Link, useLocation } from 'react-router'
import { Card, EmptyState, MockDataBadge } from '@pkg/ui'
import { AsyncContent, useAsyncData } from '../../../app/async-content'
import { getCourses } from '../api/courses-client'
import { parseScenario } from '../mocks'
import { subjectLabel } from '../subject-label'
import type { Course } from '../types'

function CourseCard({ course }: { course: Course }) {
  return (
    <Card title={<Link to={`/courses/${course.id}`}>{course.title}</Link>}>
      <p className="course-card__meta">
        学科：{subjectLabel(course.subject)}
        {course.teacherName !== null && ` · 主讲：${course.teacherName}`}
      </p>
      {course.description !== null && <p>{course.description}</p>}
      {course.chapterCount !== null && (
        <p className="course-card__meta">共 {course.chapterCount} 章</p>
      )}
    </Card>
  )
}

export function CourseListPage() {
  const location = useLocation()
  const scenario = parseScenario(location.search)
  const state = useAsyncData(`courses:${scenario}`, () => getCourses(scenario))

  return (
    <div>
      <h1>我的课程</h1>
      <MockDataBadge source="取自课程契约样例" />
      <AsyncContent state={state}>
        {(page) =>
          page.items.length === 0 ? (
            <EmptyState title="还没有课程" description="你目前没有已选的课程。" />
          ) : (
            <div className="course-list">
              {page.items.map((course) => (
                <CourseCard key={course.id} course={course} />
              ))}
            </div>
          )
        }
      </AsyncContent>
    </div>
  )
}
