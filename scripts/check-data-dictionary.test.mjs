/**
 * 数据字典检查器的反例测试（#70 A 批）。
 *
 * 全部用临时目录里的合成文档，不读仓库真实字典：真实字典会随各 owner 提交而变，
 * 测试跟着变就失去意义。每条失败断言都要求「错误原因 + 位置」，只断言退出码非 0
 * 会让任何无关错误都能把测试变绿。
 *
 * 三组已知缺陷（本文件先复现再修）：
 * 1. 带引号的默认值（'archived'）绕过枚举校验；
 * 2. JSONB 内部属性的类型列为空仍通过；
 * 3. 合法的「设计保留」状态被误判失败。
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

/** platform.md 那种表级信息（用途/主键+索引/来源+读写/保留/状态）。 */
const META_BULLETS = [
  '- 用途：测试表；平台业务。',
  '- 主键：`id`；索引：status 普通索引。',
  '- 来源：合成seed；读写：服务端读写，学生只读。',
  '- 保留/删除：停用不物理删除。',
  '- 状态：设计草案；数据库实现与验证均未完成。',
].join('\n')

/** 拼一份字典文档。meta 为 true 时带完整表级信息。 */
function buildDoc({
  owner = 'M2',
  title = 'items',
  meta = META_BULLETS,
  rows = [ID_ROW, STATUS_ROW],
}) {
  const head = owner === null ? '# 测试文档' : `# 测试文档\n\nowner：${owner}`
  const bullets = meta === null ? '' : `${meta}\n`
  return `${head}\n\n## ${title}\n\n${bullets}\n${HEADER}\n${SEPARATOR}\n${rows.join('\n')}\n`
}

/** 带 JSONB 小节与内部属性表的文档。 */
function buildJsonbDoc({
  attrRows,
  jsonbRow = '| payload | 载荷 | jsonb | 否 | {} | 无 | 无（非键） |',
}) {
  const section = ['', '## JSONB内部字典', '', HEADER, SEPARATOR, ...attrRows, ''].join('\n')
  return `${buildDoc({ rows: [ID_ROW, jsonbRow] })}${section}`
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
  const output = `${result.stdout}${result.stderr}`
  assert.doesNotMatch(output, /(?:^|\n)(?:ReferenceError|TypeError|SyntaxError):/)
  return { status: result.status, output }
}

function withRepo(files, callback) {
  const root = makeRepo(files)
  try {
    return callback(root)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

/* ------------------------------------------------------------ 基线：能通过 */

test('完整字典通过', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /结论：通过/)
  })
})

test('表级信息齐全（用途/索引/读写/保留/状态）不误报', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { output } = run(root, ['--files', 'student.md'])
    assert.doesNotMatch(output, /表缺少/)
  })
})

/* ----------------------------------------------------- 七列：缺列、空格、重名 */

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
    assert.match(output, /字段 status 重复（首次出现在第 \d+ 行）/)
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

test('主键允许为空，被拦下', () => {
  const broken = '| id | 记录标识 | varchar(64) | 是 | 无 | item_+32hex | PK |'
  withRepo({ 'student.md': buildDoc({ rows: [broken] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /声明为主键却允许为空/)
  })
})

test('可空列写成非 是/否，被拦下', () => {
  const broken = '| note | 备注 | text | 可 | 无 | 无 | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, broken] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /可空列「可」只能是 是\/否/)
  })
})

/* ------------------------------------------------------------- FK 引用登记 */

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

test('FK 列没给出目标表字段，被拦下', () => {
  const vague = '| course_id | 所属课程 | varchar(64) | 否 | 无 | 无 | FK |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, vague] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /FK 列没有给出 表\.字段/)
  })
})

test('「无物理FK」是合法写法，不误报', () => {
  const noFk = '| target_id | 目标快照 | varchar(64) | 是 | NULL | 无 | 无物理FK；保留已删除目标 |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, noFk] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

/* --------------------------------------------------- 默认值与枚举/CHECK 对账 */

test('默认值与枚举取值矛盾（不带引号），被拦下', () => {
  const row =
    '| status | 状态 | varchar(16) | 否 | archived | CHECK IN(active,disabled) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /默认值「archived」不在取值范围/)
  })
})

test("带引号的默认值同样对账（'archived' 不再绕过）", () => {
  const row =
    "| status | 状态 | varchar(16) | 否 | 'archived' | CHECK IN(active,disabled) | 无（非键） |"
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /默认值「archived」不在取值范围/)
  })
})

test("带引号的合法默认值（'active'）通过", () => {
  const row =
    "| status | 状态 | varchar(16) | 否 | 'active' | CHECK IN(active,disabled) | 无（非键） |"
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

test('默认值为「无」时不做枚举对账，不误报', () => {
  const row = '| kind | 类型 | varchar(16) | 否 | 无 | CHECK IN(a,b) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

test('无法解析的 CHECK 表达式标记为未验证，而不是默认通过', () => {
  const row = '| code | 编码 | varchar(32) | 否 | abc | CHECK char_length(code) > 0 | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /无法与取值范围表达式对账/)
  })
})

/* ------------------------------------------------------------ JSONB 内部结构 */

test('JSONB 列没有内部字典小节，被拦下', () => {
  const jsonbRow = '| payload | 载荷 | jsonb | 否 | {} | 无 | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, jsonbRow] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /没有「JSONB内部字典」小节/)
  })
})

test('JSONB 列在内部字典里缺失，被拦下', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| other.schemaVersion | 其他载荷版本 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
    ],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 列 payload 缺少 schemaVersion 属性/)
    assert.match(output, /other\.schemaVersion 挂在未声明的 JSONB 列 other 下/)
  })
})

test('JSONB 内部属性的类型列为空，仍被拦下', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| payload.schemaVersion | 载荷版本 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
      '| payload.chapterId | 章节 |  | 否 | 无 | 必填 | 无（非键） |',
    ],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 属性 payload\.chapterId 的第 3 列（PostgreSQL）为空/)
  })
})

test('JSONB 列缺少 schemaVersion 属性，被拦下', () => {
  const doc = buildJsonbDoc({
    attrRows: ['| payload.chapterId | 章节 | jsonb内string | 否 | 无 | 必填 | 无（非键） |'],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 列 payload 缺少 schemaVersion 属性/)
  })
})

test('JSONB 属性重名被拦下', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| payload.schemaVersion | 载荷版本 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
      '| payload.schemaVersion | 又一个 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
    ],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 属性 payload\.schemaVersion 重复/)
  })
})

test('完整 JSONB 字典通过', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| payload.schemaVersion | 载荷版本 | jsonb内string | 否 | 无 | 1.0 | 无（非键） |',
      '| payload.chapterId | 章节 | jsonb内string | 否 | 无 | 必填 | 无（非键） |',
    ],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

/* ------------------------------------------------------------ 表级信息与状态 */

test('表级「用途」「状态」缺失，被拦下', () => {
  withRepo({ 'student.md': buildDoc({ meta: null }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /表缺少「用途」信息/)
    assert.match(output, /表缺少「实现状态」信息/)
  })
})

test('表级缺索引/读写权限/保留策略，分别被拦下', () => {
  const meta = ['- 用途：测试表；平台业务。', '- 状态：设计草案'].join('\n')
  withRepo({ 'student.md': buildDoc({ meta }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /表缺少「索引」信息/)
    assert.match(output, /表缺少「读写权限」信息/)
    assert.match(output, /表缺少「保留策略」信息/)
  })
})

test('设计保留是合法状态，不误判失败', () => {
  const meta = META_BULLETS.replace(
    '- 状态：设计草案；数据库实现与验证均未完成。',
    '- 状态：设计保留（S2 实体，本轮不建表）。',
  )
  withRepo({ 'student.md': buildDoc({ meta }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
  })
})

test('设计保留与已实现同时标注，视为矛盾', () => {
  const meta = META_BULLETS.replace(
    '- 状态：设计草案；数据库实现与验证均未完成。',
    '- 状态：设计保留；迁移已实现。',
  )
  withRepo({ 'student.md': buildDoc({ meta }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /设计保留.*已实现/)
  })
})

test('状态不在四级口径内，被拦下', () => {
  const meta = META_BULLETS.replace(
    '- 状态：设计草案；数据库实现与验证均未完成。',
    '- 状态：差不多好了。',
  )
  withRepo({ 'student.md': buildDoc({ meta }) }, (root) => {
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

/* --------------------------------------------------------- 文件、模块与重复 */

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

test('空文件被拦下（不是静默通过）', () => {
  withRepo({ 'student.md': '' }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /文件为空/)
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
  const files = { 'README.md': '# 总览\n', 'erd.md': '# ER\n', 'acceptance.md': '# 验收\n' }
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
      // 报在后登记的那份文件上，并指出与谁冲突；两份文件名都要出现。
      assert.match(output, /docs\/data-model\/learning\.md\n/)
      assert.match(output, /表名与 docs\/data-model\/student\.md 重复登记/)
    },
  )
})

/* ------------------------------------------------------------- 跨文件引用 */

test('目标表所在文件未选中但已存在时，不误报未登记', () => {
  const student = [
    buildDoc({ owner: 'M2', title: 'student_maps' }),
    '## 映射',
    '',
    '| 前端字段 | 领域表.列 | 来源 |',
    '| --- | --- | --- |',
    '| id | users.id | 未实现 |',
    '',
  ].join('\n')
  withRepo(
    { 'platform.md': buildDoc({ owner: 'M1', title: 'users' }), 'student.md': student },
    (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 0, output)
      assert.doesNotMatch(output, /未登记的表 users/)
    },
  )
})

test('局部模式：未登记的引用只提醒，不阻塞', () => {
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
    assert.match(output, /局部/)
  })
})

test('全量模式：未登记的引用不得只提醒后仍宣称通过', () => {
  const modules = [
    ['platform.md', 'users'],
    ['tutoring-knowledge.md', 'tutoring_sessions'],
    ['avatar-media.md', 'avatar_profiles'],
    ['learning.md', 'courses'],
    ['analytics-admin.md', 'analytics_daily_metrics'],
  ]
  const files = { 'README.md': '# 总览\n', 'erd.md': '# ER\n', 'acceptance.md': '# 验收\n' }
  modules.forEach(([file, table], index) => {
    files[file] = buildDoc({ owner: `M${index + 1}`, title: table })
  })
  files['student.md'] = [
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
  withRepo(files, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 1, output)
    assert.match(output, /未登记的表 future_courses/)
    assert.match(output, /未完成/)
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
    assert.match(output, /映射引用了 items\.ghost_column/)
  })
})

/* ------------------------------------------------------------------- 用法 */

test('缺少 --files 的值时按用法错误处理', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root, ['--files'])
    assert.equal(status, 2, output)
    assert.match(output, /--files 需要一个逗号分隔的路径列表/)
  })
})

test('未知参数按用法错误处理', () => {
  withRepo({ 'student.md': buildDoc({}) }, (root) => {
    const { status, output } = run(root, ['--verbose'])
    assert.equal(status, 2, output)
    assert.match(output, /未知参数/)
  })
})

/* ------------------------------------------------------- 本轮审计漏检回归 */

for (const [label, value] of [
  ['大小写不同的字符串', "'ACTIVE'"],
  ['带 PostgreSQL 类型转换的字符串', "'archived'::text"],
]) {
  test(`${label}默认值不能绕过枚举检查`, () => {
    const row = `| status | 状态 | varchar(16) | 否 | ${value} | CHECK IN('active','disabled') | 无（非键） |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 1, output)
      assert.match(output, /字段 status 的默认值.*不在取值范围/)
    })
  })
}

test('数字默认值必须属于数字枚举', () => {
  const row = '| mode | 模式 | integer | 否 | 2 | CHECK IN(0,1) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /字段 mode 的默认值.*不在取值范围/)
  })
})

test('不能解析的默认值表达式明确标记未验证', () => {
  const row =
    '| status | 状态 | varchar(16) | 否 | make_status() | CHECK IN(active,disabled) | 无（非键） |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /字段 status.*未验证/)
    assert.match(output, /1 项未验证/)
  })
})

for (const [value, allowed] of [
  ["'Active'::text", "'Active','Disabled'"],
  ['1', '0,1'],
  ['1.00', '0,1.0'],
  ['true', 'true,false'],
]) {
  test(`合法默认值 ${value} 与枚举正确对账`, () => {
    const row = `| mode | 模式 | varchar(16) | 否 | ${value} | CHECK IN(${allowed}) | 无（非键） |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 0, output)
      assert.match(output, /0 项未验证/)
    })
  })
}

test('一张有效表不能掩盖另一张表的缺列表头', () => {
  const bad = buildDoc({ title: 'other_items' }).replace(' | PK/FK/关联与删除/更新规则 |', ' |')
  withRepo({ 'student.md': `${buildDoc({})}\n${bad}` }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /\[other_items\].*表头.*7/)
  })
})

test('只有表头没有字段行的字典表不通过', () => {
  withRepo({ 'student.md': buildDoc({ rows: [] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /\[items\].*没有字段行/)
  })
})

for (const label of ['用途', '状态']) {
  test(`表级${label}只有标签、内容为空时不通过`, () => {
    const meta = META_BULLETS.replace(new RegExp(`- ${label}：[^\\n]+`), `- ${label}：`)
    withRepo({ 'student.md': buildDoc({ meta }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 1, output)
      assert.match(output, new RegExp(`表缺少「${label === '状态' ? '实现状态' : label}」信息`))
    })
  })
}

test('owner 标签为空不算标注负责人', () => {
  withRepo({ 'student.md': buildDoc({ owner: '' }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /owner/)
  })
})

function completeFiles() {
  const modules = [
    ['platform.md', 'users'],
    ['student.md', 'student_maps'],
    ['tutoring-knowledge.md', 'tutoring_sessions'],
    ['avatar-media.md', 'avatar_profiles'],
    ['learning.md', 'courses'],
    ['analytics-admin.md', 'analytics_daily_metrics'],
  ]
  return Object.fromEntries([
    ['README.md', '# 总览\n'],
    ['erd.md', '# ER\n'],
    ['acceptance.md', '# 验收\n'],
    ...modules.map(([file, title]) => [file, buildDoc({ title })]),
  ])
}

for (const name of ['README.md', 'erd.md', 'acceptance.md']) {
  test(`全量模式拒绝空的公共文件 ${name}`, () => {
    withRepo({ ...completeFiles(), [name]: ' \n' }, (root) => {
      const { status, output } = run(root)
      assert.equal(status, 1, output)
      assert.match(output, /文件为空/)
      assert.ok(output.includes(`docs/data-model/${name}`), output)
    })
  })
}

for (const reference of [
  'reminders.*',
  'courses.id / ghost_column',
  'ghost_column / courses.id',
  'courses.(id,ghost_column)',
]) {
  test(`映射引用 ${reference} 不能在全量检查中静默跳过`, () => {
    const mapping = `# 映射\nowner：M2\n本文件不登记新表。\n\n## 映射\n| JSON字段 | 领域表.列 | 来源 |\n| --- | --- | --- |\n| x | ${reference} | 未实现 |\n`
    withRepo({ ...completeFiles(), 'student.md': mapping }, (root) => {
      const { status, output } = run(root)
      assert.equal(status, 1, output)
      assert.match(output, /映射.*(?:通配符|完整的 表\.字段)/)
    })
  })
}

for (const [value, allowed] of [
  ["'1'::integer", '0,1'],
  ['1.1::numeric(2,0)', '1.1,2'],
]) {
  test(`无法证明保值的类型转换 ${value} 留待核验`, () => {
    const row = `| mode | 模式 | numeric | 否 | ${value} | CHECK IN(${allowed}) | 无（非键） |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 0, output)
      assert.match(output, /字段 mode.*未验证/)
      assert.match(output, /1 项未验证/)
    })
  })
}
for (const constraint of [
  "CHECK (status NOT IN('active','disabled'))",
  "CHECK (status IN('active','disabled') AND status <> 'active')",
  "CHECK (status IN('active','disabled') OR status = 'other')",
]) {
  test(`不能把局部 IN 当作完整约束：${constraint}`, () => {
    const row = `| status | 状态 | varchar(16) | 否 | active | ${constraint} | 无（非键） |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 0, output)
      assert.match(output, /字段 status.*未验证/)
    })
  })
}
test('简单带字段名的 SQL CHECK 可以核验', () => {
  const row =
    "| status | 状态 | varchar(16) | 否 | archived | CHECK (status IN('active','disabled')) | 无（非键） |"
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /字段 status.*不在取值范围/)
  })
})
test('只有 Markdown 装饰的元数据仍视为空', () => {
  const meta = META_BULLETS.replace('索引：status 普通索引。', '索引：** **')
  withRepo({ 'student.md': buildDoc({ owner: '** **', meta }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /未标注 owner/)
    assert.match(output, /表缺少「索引」/)
  })
})

test('业务/管理分组下三级实体标题按真实表名登记并解析内部 FK', () => {
  const first = buildDoc({ title: 'items' }).replace('## items', '## 业务表\n\n### items')
  const second = buildDoc({
    title: 'item_links',
    rows: [ID_ROW, '| item_id | 关联 | varchar(64) | 否 | 无 | 无 | FK→items.id |'],
  }).replace('## item_links', '## 管理表\n\n### item_links')
  withRepo({ 'student.md': first + second }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.match(output, /已登记 2 张表/)
    assert.doesNotMatch(output, /悬空 FK|重复登记/)
  })
})
test('JSONB 三级标题仍是内部属性，不能登记成实体表或跳过属性校验', () => {
  const doc = buildJsonbDoc({
    attrRows: ['| payload.schemaVersion | 版本 | | 否 | 1.0 | 固定 | 无 |'],
  }).replace('## JSONB内部字典', '## JSONB内部字典\n\n### items.payload')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 属性 payload.schemaVersion 的第 3 列/)
    assert.match(output, /已登记 1 张表/)
  })
})

/* -------------------------------------------------- JSONB 归属与原始字面值 */

function sharedJsonbDoc(attributes) {
  const rows = [ID_ROW, '| details | 详情 | jsonb | 否 | {} | 无 | 无（非键） |']
  return [
    buildDoc({ title: 'alpha', rows }),
    buildDoc({ title: 'beta', rows }),
    '## JSONB内部字典',
    attributes,
  ].join('\n')
}

function versionTable(path) {
  return [
    HEADER,
    SEPARATOR,
    `| ${path} | 结构版本 | string | 否 | 无 | 1.0 | 无（非键） |`,
    '',
  ].join('\n')
}

test('全量：同名 JSONB 列不能共用另一张表的版本属性', () => {
  const doc = sharedJsonbDoc(`### alpha.details\n${versionTable('details.schemaVersion')}`)
  withRepo({ ...completeFiles(), 'student.md': doc }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 列 details 缺少 schemaVersion.*beta\.details/)
  })
})

test('不同表同名 JSONB 列按三级归属标题分别登记，不误报重复', () => {
  const attributes = [
    '### alpha.details',
    versionTable('details.schemaVersion'),
    '### beta.details',
    versionTable('details.schemaVersion'),
  ].join('\n')
  withRepo({ ...completeFiles(), 'student.md': sharedJsonbDoc(attributes) }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 0, output)
    assert.match(output, /0 项未验证/)
    assert.doesNotMatch(output, /重复/)
  })
})

test('JSONB 属性接受完整的表名、列名和属性路径', () => {
  const attributes = [
    versionTable('alpha.details.schemaVersion'),
    versionTable('beta.details.schemaVersion'),
  ].join('\n')
  withRepo({ ...completeFiles(), 'student.md': sharedJsonbDoc(attributes) }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 0, output)
    assert.match(output, /0 项未验证/)
  })
})

test('同名 JSONB 列的无归属简写报告歧义，不能任意关联到一张表', () => {
  const doc = sharedJsonbDoc(versionTable('details.schemaVersion'))
  withRepo({ ...completeFiles(), 'student.md': doc }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 1, output)
    assert.match(output, /details\.schemaVersion.*歧义/)
    assert.match(output, /alpha\.details/)
    assert.match(output, /beta\.details/)
  })
})

test('schemaVersion 必须大小写精确，不能用 schemaversion 冒充', () => {
  const doc = buildJsonbDoc({
    attrRows: ['| payload.schemaversion | 版本 | string | 否 | 无 | 1.0 | 无 |'],
  })
  withRepo({ ...completeFiles(), 'student.md': doc }, (root) => {
    const { status, output } = run(root)
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 列 payload 缺少 schemaVersion/)
  })
})

test('JSONB 大小写不同的属性是独立键，不误报重复', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| payload.schemaVersion | 版本 | string | 否 | 无 | 1.0 | 无 |',
      '| payload.Status | 大写状态 | string | 是 | 无 | 无 | 无 |',
      '| payload.status | 小写状态 | string | 是 | 无 | 无 | 无 |',
    ],
  })
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.doesNotMatch(output, /重复/)
  })
})

test('同一 JSONB 属性的简写和全限定路径仍会识别为重复', () => {
  const doc = buildJsonbDoc({
    attrRows: [
      '| payload.schemaVersion | 版本 | string | 否 | 无 | 1.0 | 无 |',
      '| items.payload.schemaVersion | 重复版本 | string | 否 | 无 | 1.0 | 无 |',
    ],
  }).replace('## JSONB内部字典', '## JSONB内部字典\n\n### items.payload')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /JSONB 属性 items\.payload\.schemaVersion 重复/)
  })
})

test('JSONB 全限定属性与三级归属标题冲突时报告错误', () => {
  const doc = sharedJsonbDoc(
    [
      '### alpha.details',
      versionTable('beta.details.schemaVersion'),
      '### beta.details',
      versionTable('beta.details.schemaVersion'),
    ].join('\n'),
  )
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /beta\.details\.schemaVersion.*归属标题 alpha\.details.*不一致/)
  })
})

test('显式 JSONB 归属标题优先于其他表列的前缀碰撞', () => {
  const doc = [
    buildDoc({
      title: 'containers',
      rows: [ID_ROW, '| settings | 设置 | jsonb | 否 | {} | 无 | 无 |'],
    }),
    buildDoc({
      title: 'settings',
      rows: [ID_ROW, '| options | 选项 | jsonb | 否 | {} | 无 | 无 |'],
    }),
    '## JSONB内部字典',
    '### containers.settings',
    HEADER,
    SEPARATOR,
    '| settings.schemaVersion | 版本 | string | 否 | 无 | 1.0 | 无 |',
    '| settings.options | 选项对象 | object | 是 | 无 | 无 | 无 |',
    '| settings.options.label | 选项名 | string | 是 | 无 | 无 | 无 |',
    '',
    '### settings.options',
    versionTable('settings.options.schemaVersion'),
  ].join('\n')
  withRepo({ 'student.md': doc }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 0, output)
    assert.doesNotMatch(output, /不一致|重复/)
    assert.match(output, /已登记 2 张表/)
  })
})

for (const [label, value, allowed] of [
  ['单引号内的双引号', `'a""b'`, `'a"b'`],
  ['双引号内的单引号', `"a''b"`, `"a'b"`],
  ['字符串内的星号', "'a**b'", "'ab'"],
  ['字符串内的反引号', "'a`b'", "'ab'"],
]) {
  test(`${label}不因清理而改变，矛盾默认值会失败`, () => {
    const row = `| status | 状态 | text | 否 | ${value} | CHECK IN(${allowed}) | 无 |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 1, output)
      assert.match(output, /字段 status 的默认值.*不在取值范围/)
      assert.match(output, /0 项未验证/)
    })
  })
}

test('默认值只有 Markdown 装饰时仍按空单元格失败', () => {
  const row = '| status | 状态 | text | 否 | ** ** | CHECK IN(active) | 无 |'
  withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
    const { status, output } = run(root, ['--files', 'student.md'])
    assert.equal(status, 1, output)
    assert.match(output, /字段 status 的第 5 列（默认值）为空/)
  })
})

for (const [label, value, allowed] of [
  ['单引号转义', "'a''b'", "'a''b'"],
  ['双引号转义', '"a""b"', '"a""b"'],
  ['外层代码装饰与内部字面值', "`'a**`b'`", "'a**`b'"],
  ['外层粗体装饰', "**'a**b'**", "'a**b'"],
]) {
  test(`${label}保持合法值精确一致`, () => {
    const row = `| status | 状态 | text | 否 | ${value} | CHECK IN(${allowed}) | 无 |`
    withRepo({ 'student.md': buildDoc({ rows: [ID_ROW, row] }) }, (root) => {
      const { status, output } = run(root, ['--files', 'student.md'])
      assert.equal(status, 0, output)
      assert.match(output, /0 项未验证/)
    })
  })
}
