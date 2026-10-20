/**
 * 字典检查器的反例测试（#70 A 批）。
 *
 * 全部用临时目录里的合成文档，不读仓库真实字典：
 * 真实字典会随各 owner 提交而变，测试跟着变就失去意义。
 * 每个用例断言「检查器会因为具体缺项而失败」，而不只是「退出码非 0」——
 * 只断言非 0 的话，任何一条无关错误都能让测试变绿。
 */

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const SCRIPT = fileURLToPath(new URL('./check-data-dictionary.mjs', import.meta.url))

const HEADER =
  '| 物理字段名 | 中文名称/业务含义 | PostgreSQL 类型与长度/精度 | 可空 | 默认值 | 取值范围/枚举/唯一/CHECK | PK/FK/关联与删除/更新规则 |'
const SEPARATOR = '| --- | --- | --- | --- | --- | --- | --- |'

const ID_ROW = '| id | 记录标识 | varchar(64) | 否 | 无；服务端生成 | item_+32小写hex | PK |'
const STATUS_ROW =
  '| status | 状态 | varchar(16) | 否 | active | CHECK IN(active,disabled) | 无（非键） |'

/** 拼一份字典文档。rows 为表格数据行（不含表头与分隔行）。 */
function buildDoc({ owner = 'M2', title = 'items', meta = true, rows = [ID_ROW, STATUS_ROW] }) {
  const head = owner === null ? '# 测试文档' : `# 测试文档\n\nowner：${owner}`
  const bullets = meta ? '- 用途：测试表\n- 状态：设计草案\n' : ''
  return `${head}\n\n## ${title}\n\n${bullets}\n${HEADER}\n${SEPARATOR}\n${rows.join('\n')}\n`
}

function makeRepo(files) {
  const root = mkdtempSync(join(tmpdir(), 'dict-check-'))
  mkdirSync(join(root, 'docs', 'data-model'), { recursive: true })
  for (const [name, content] of Object.entries(files)) {
    writeFileSync(join(root, 'docs', 'data-model', name), content)
  }
  return root
}

function run(root, args = []) {
  const result = spawnSync(process.execPath, [SCRIPT, '--root', root, ...args], {
    encoding: 'utf8',
  })
  return { status: result.status, output: `${result.stdout}${result.stderr}` }
}

function withRepo(files, callback) {
  const root = makeRepo(files)
  try {
    return callback(root)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

test('完整字典通过', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /结论：通过/)
  })
})

test('空单元格被拦下，并指出具体列', () => {
  const broken = '| status | 状态 | varchar(16) | 否 |  | CHECK IN(active) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, broken] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /字段 status 的第 5 列（默认值）为空/)
  })
})

test('同表字段重名被拦下', () => {
  const duplicate =
    '| status | 又一行状态 | varchar(16) | 否 | active | CHECK IN(active) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, STATUS_ROW, duplicate] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /字段 status 重复/)
  })
})

test('悬空外键被拦下', () => {
  const dangling = '| course_id | 所属课程 | varchar(64) | 否 | 无 | 无 | FK→ghost_courses.id |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, dangling] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /未登记的表 ghost_courses/)
  })
})

test('外键指向已登记表但不存在的列，被拦下', () => {
  const wrongColumn =
    '| course_id | 所属课程 | varchar(64) | 否 | 无 | 无 | FK→items.ghost_column |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, wrongColumn] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /items 不存在的列 ghost_column/)
  })
})

test('默认值与枚举取值矛盾，被拦下', () => {
  const contradiction =
    '| status | 状态 | varchar(16) | 否 | archived | CHECK IN(active,disabled) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, contradiction] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /默认值「archived」不在取值范围/)
  })
})

test('主键允许为空，被拦下', () => {
  const broken = '| id | 记录标识 | varchar(64) | 是 | 无 | item_+32hex | PK |'
  withRepo({ 'student.md': buildDoc({ rows: [broken] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /声明为主键却允许为空/)
  })
})

test('列数不足七列，被拦下', () => {
  const short = '| status | 状态 | varchar(16) | 否 | active | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, short] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /列数为 6，应为 7/)
  })
})

test('表级「用途」「状态」缺失，被拦下', () => {
  withRepo({ 'student.md': buildDoc({ meta: false }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /表缺少「用途」说明/)
    assert.match(output, /表缺少「状态」说明/)
  })
})

test('状态不在四级口径内，被拦下', () => {
  const doc = buildDoc({}).replace('- 状态：设计草案', '- 状态：差不多好了')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /不在四级口径内/)
  })
})

test('无 owner 标注被拦下', () => {
  withRepo({ 'student.md': buildDoc({ owner: null }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /未标注 owner/)
  })
})

test('JSONB 列没有内部字典，被拦下', () => {
  const jsonbRow = '| payload | 载荷 | jsonb | 否 | {} | 无 | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, jsonbRow] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /没有「JSONB内部字典」小节/)
  })
})

test('JSONB 列在内部字典里缺失，被拦下', () => {
  const jsonbRow = '| payload | 载荷 | jsonb | 否 | {} | 无 | 无（非键） |'
  const jsonbSection = [
    '',
    '## JSONB内部字典',
    '',
    HEADER,
    SEPARATOR,
    '| other.schemaVersion | 其他载荷版本 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
    '',
  ].join('\n')
  const doc = `${buildDoc({ rows: [ID_ROW, jsonbRow] })}${jsonbSection}`
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 列 payload 没有在/)
  })
})

test('不登记表时缺少显式声明，被拦下', () => {
  const doc = '# 测试文档\n\nowner：M2\n\n只有映射，没有表。\n'
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /本文件不登记新表/)
  })
})

test('不登记表但写明声明，通过', () => {
  const doc = '# 测试文档\n\nowner：M2\n\n本文件不登记新表，只做映射。\n'
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

test('映射引用未登记的表只提醒，不阻塞', () => {
  const doc = [
    '# 测试文档',
    '',
    'owner：M2',
    '',
    '本文件不登记新表。',
    '',
    '## 映射',
    '',
    '| 前端字段 | 领域表.列 | 来源 |',
    '| --- | --- | --- |',
    '| title | future_courses.title | 未实现 |',
    '',
  ].join('\n')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /未登记的表 future_courses/)
  })
})

test('映射引用已登记表的不存在列，被拦下', () => {
  const doc = [
    buildDoc({}),
    '## 映射',
    '',
    '| 前端字段 | 领域表.列 | 来源 |',
    '| --- | --- | --- |',
    '| ghost | items.ghost_column | 未实现 |',
    '',
  ].join('\n')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /映射引用了 items.ghost_column/)
  })
})

test('全量模式下模块清单缺项，被拦下', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 1, output)
    assert.match(output, /缺少模块文件（owner M5）/)
    assert.match(output, /缺少模块文件（owner M1）/)
  })
})

test('全量模式下文件齐全且有效，通过', () => {
  const modules = [
    ['platform.md', 'users'],
    ['student.md', 'student_maps'],
    ['tutoring-knowledge.md', 'tutoring_sessions'],
    ['avatar-media.md', 'avatar_profiles'],
    ['learning.md', 'courses'],
    ['analytics-admin.md', 'analytics_daily_metrics'],
  ]
  const files = {
    'README.md': '# 总览\n',
    'erd.md': '# ER\n',
    'acceptance.md': '# 验收\n',
  }
  modules.forEach(([file, table], index) => {
    files[file] = buildDoc({ owner: `M${index + 1}`, title: table })
  })
  withRepo(files, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 0, output)
    assert.match(output, /已登记 6 张表/)
  })
})

test('同一张表被两份文件重复登记，被拦下', () => {
  withRepo(
    {
      'learning.md': buildDoc({ owner: 'M5', title: 'courses' }),
      'student.md': buildDoc({ owner: 'M2', title: 'courses' }),
    },
    (root) => {
      const { status, output } = run(root, ['--files', 'learning.md,student.md'])
      assert.equal(status, 1, output)
      assert.match(output, /表名与 docs\/data-model\/learning.md 重复登记/)
    },
  )
})

test('缺少 --files 的值时按用法错误处理', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root, ['--files'])
    assert.equal(status, 2, output)
    assert.match(output, /--files 需要一个逗号分隔的路径列表/)
  })
})
