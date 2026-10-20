#!/usr/bin/env node
/**
 * 数据字典检查器（#70 A 批）。
 *
 * 只做静态检查，不连数据库、不生成任何内容：把 `docs/data-model/*.md` 当数据源，
 * 校验七列是否真的填满、字段是否重名、FK 是否指向已登记的表与列、默认值能否与
 * 枚举/CHECK 对账、JSONB 内部结构是否完整、表级信息是否写全、模块清单是否缺文件。
 *
 * 两条硬规则：
 * 1. **发现缺项就报错，不自动补空列**——自动补全会让「七列没填完」看起来像「已经填完」。
 * 2. **无法自动核验的内容单列「未验证」**，不混进「通过」，也不假装查过
 *    （例如本工具解析不了的 `CHECK char_length(x) > 0`）。
 *
 * 用法：
 *   node scripts/check-data-dictionary.mjs                      # 全量：模块清单 + 所有字典
 *   node scripts/check-data-dictionary.mjs --files student.md   # 只查指定文件（owner 自检）
 *   node scripts/check-data-dictionary.mjs --root <dir>         # 指定仓库根（测试用）
 *
 * 全量与局部是有意区分的：
 * - 局部（`--files`）只对本文件判错；引用到尚未提交的表只提醒，因为 M2 修不了别人的字典。
 *   结论会写明「仅局部检查，未做全量验收」。
 * - 全量（默认）把未登记引用、缺模块、空文件都当错误；缺项时结论不会出现「通过」。
 *
 * 表级 owner 允许写在文档头（一个模块一份字典、单一 owner），不要求每张表重复同一行；
 * 其余表级信息（用途、业务/管理归类、索引、读写权限、保留策略、实现状态）逐表检查，
 * 但只判断「有没有写」，不判断内容语义是否成立——语义仍需人工评审。
 *
 * 退出码：0 = 无阻断错误；1 = 有错误；2 = 用法错误。「未验证」与「提醒」不改变退出码，
 * 但会在结论里点名数量，避免被读成「全部核验通过」。
 */

import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

/** 模块清单与 owner。缺任何一个都算「模块清单缺项」。 */
const MODULES = [
  { file: 'platform.md', owner: 'M1' },
  { file: 'student.md', owner: 'M2' },
  { file: 'tutoring-knowledge.md', owner: 'M3' },
  { file: 'avatar-media.md', owner: 'M4' },
  { file: 'learning.md', owner: 'M5' },
  { file: 'analytics-admin.md', owner: 'M6' },
]

/** 公共文件：不按模块字典校验，但必须存在（#69「目录固定为 docs/data-model/」）。 */
const SHARED_FILES = ['README.md', 'erd.md', 'acceptance.md']

/** 七列表头的前缀。容忍列名后缀（如「取值范围/枚举/唯一/CHECK」）。 */
const SEVEN_HEADERS = [
  '物理字段名',
  '中文名称',
  'PostgreSQL',
  '可空',
  '默认值',
  '取值范围',
  'PK/FK',
]

/** 实现状态四级（README 与 #69 共同口径）。「设计保留」是并列标记，不是第五级。 */
const LIFECYCLE_PATTERN = /设计草案|评审确认|迁移已实现|真实\s*PostgreSQL/
const DESIGN_RESERVED_PATTERN = /设计保留/
const IMPLEMENTED_PATTERN = /迁移已实现|真实\s*PostgreSQL/

/** 「本文件不登记新表」的显式声明。没有字典表时必须写明，避免空文件静默通过。 */
const NO_TABLE_DECLARATION = /本文件不登记新表/

/** FK 单元格里出现「无物理FK」表示故意不建外键，不当作缺项。 */
const NO_FK_PATTERN = /无物理\s*FK/i

/** 枚举单元格的 IN(...) 写法。 */
const CHECK_IN_PATTERN = /IN\s*\(([^)]*)\)/i

/** 默认值被判为「字面量枚举值」的形态：小写标识符，不含空格与中文。 */
const LITERAL_PATTERN = /^[a-z][a-z0-9_]*$/

/** 不算枚举值的内建默认。 */
const BUILTIN_DEFAULTS = new Set(['null', 'true', 'false', 'current_timestamp', 'now'])

/** 表名/列名引用：table.column。 */
const REFERENCE_PATTERN = /([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)/g

/** 表级信息。只判断写没写，不判断内容对不对。 */
const TABLE_INFO = [
  { key: '用途', label: '用途', pattern: /用途\s*[：:]/ },
  { key: '状态', label: '实现状态', pattern: /状态\s*[：:]/ },
  { key: '归类', label: '业务/管理归类', pattern: /业务|管理/ },
  { key: '索引', label: '索引', pattern: /索引/ },
  { key: '权限', label: '读写权限', pattern: /读写|权限|授权/ },
  { key: '保留', label: '保留策略', pattern: /保留/ },
]

class Report {
  constructor() {
    this.errors = []
    this.unverified = []
    this.warnings = []
  }

  error(file, line, table, message) {
    this.errors.push({ file, line, table, message })
  }

  todo(file, line, table, message) {
    this.unverified.push({ file, line, table, message })
  }

  warn(file, line, table, message) {
    this.warnings.push({ file, line, table, message })
  }
}

/** 去掉 markdown 装饰，便于比较；不改变字段语义。 */
function clean(cell) {
  return (cell ?? '').replace(/`/g, '').replace(/\*\*/g, '').trim()
}

/** 去掉 SQL 风格引号，让 `'active'` 与 active 被当作同一个枚举值。 */
function unquote(value) {
  return value.replace(/^(['"`])(.*)\1$/, '$2').trim()
}

/** 拆一行表格为单元格。行首行尾的管道不算单元格。 */
function splitRow(line) {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

/** 分隔行：| --- | :---: | 之类。 */
function isSeparator(line) {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('-')
}

/** 把文档拆成「## 标题 + 行」的小节，保留行号用于定位。 */
function splitSections(text) {
  const lines = text.split(/\r?\n/)
  const sections = [{ title: null, line: 1, entries: [] }]
  let current = sections[0]
  lines.forEach((raw, index) => {
    const line = index + 1
    if (/^##\s+/.test(raw)) {
      current = { title: raw.replace(/^##\s+/, '').trim(), line, entries: [] }
      sections.push(current)
      return
    }
    current.entries.push({ text: raw, line })
  })
  return sections
}

/** 在一节里找出所有表格块。 */
function findTables(section) {
  const tables = []
  const { entries } = section
  for (let i = 0; i < entries.length; i += 1) {
    const line = entries[i].text
    const next = entries[i + 1]
    if (!line.trim().startsWith('|') || !next || !isSeparator(next.text)) continue
    const header = splitRow(line).map(clean)
    const rows = []
    let j = i + 2
    while (j < entries.length && entries[j].text.trim().startsWith('|')) {
      rows.push({ cells: splitRow(entries[j].text).map(clean), line: entries[j].line })
      j += 1
    }
    tables.push({ header, rows, line: entries[i].line })
    i = j - 1
  }
  return tables
}

/** 七列表头判定：列数与顺序都要对，避免把映射表当成字典表。 */
function isDictionaryHeader(header) {
  if (header.length !== SEVEN_HEADERS.length) return false
  return SEVEN_HEADERS.every((prefix, index) => header[index].startsWith(prefix))
}

/** 映射表判定：表头出现「领域表」列（#70 要求「JSON 字段 → 领域表.列」）。 */
function mappingColumnIndex(header) {
  return header.findIndex((cell) => cell.includes('领域表'))
}

/** 一节的元信息：`- 用途：xxx` 这类项目符号。 */
function sectionMeta(section, stopLine) {
  const meta = new Map()
  for (const entry of section.entries) {
    if (entry.line >= stopLine) break
    const match = /^\s*-\s*([^：:]+)[：:]\s*(.*)$/.exec(entry.text)
    if (match) meta.set(clean(match[1]).toLowerCase(), clean(match[2]))
  }
  return meta
}

/** 表格之前的整段文字：部分信息写在「主键：…；索引：…」里。 */
function sectionPreamble(section, stopLine) {
  return section.entries
    .filter((entry) => entry.line < stopLine)
    .map((entry) => entry.text)
    .join('\n')
}

function parseArgs(argv) {
  const options = { root: process.cwd(), files: null, full: true }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--help' || arg === '-h') {
      options.help = true
    } else if (arg === '--root') {
      const value = argv[(i += 1)]
      if (!value) return { ...options, invalid: '--root 需要一个目录' }
      options.root = resolve(value)
    } else if (arg === '--files') {
      const value = argv[(i += 1)]
      if (!value) return { ...options, invalid: '--files 需要一个逗号分隔的路径列表' }
      options.files = value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      options.full = false
    } else {
      return { ...options, invalid: `未知参数：${arg}` }
    }
  }
  return options
}

function usage() {
  return [
    '数据字典检查器',
    '',
    '  node scripts/check-data-dictionary.mjs                      全量检查（模块清单 + 字典）',
    '  node scripts/check-data-dictionary.mjs --files student.md   只查指定文件（相对 docs/data-model/）',
    '  node scripts/check-data-dictionary.mjs --root <dir>         指定仓库根目录',
    '',
    '退出码：0 无阻断错误；1 有错误；2 用法错误。',
  ].join('\n')
}

/** 解析一份文档：字典表、映射表、JSONB 小节。 */
function parseDoc(name, text) {
  const doc = {
    name,
    file: `docs/data-model/${name}`,
    text,
    tables: [],
    mappings: [],
    jsonbSection: null,
  }
  for (const section of splitSections(text)) {
    if (section.title === null) continue
    if (/JSONB/i.test(section.title)) {
      doc.jsonbSection = { section, tables: findTables(section) }
      continue
    }
    for (const table of findTables(section)) {
      if (isDictionaryHeader(table.header)) {
        doc.tables.push({ section, table, name: section.title })
        continue
      }
      const column = mappingColumnIndex(table.header)
      if (column >= 0) doc.mappings.push({ section, table, column })
    }
  }
  return doc
}

/** 登记表名与字段；重复表名直接判错（一张表只能有一个 owner）。 */
function buildRegistry(docs, report) {
  const registry = new Map()
  for (const doc of docs) {
    for (const { table, name: tableName } of doc.tables) {
      if (registry.has(tableName)) {
        report.error(
          doc.file,
          table.line,
          tableName,
          `表名与 ${registry.get(tableName).file} 重复登记——一张表只能有一个 owner`,
        )
        continue
      }
      const fields = new Map()
      for (const row of table.rows) {
        const field = clean(row.cells[0])
        if (field) fields.set(field.toLowerCase(), row.line)
      }
      registry.set(tableName, { file: doc.file, fields })
    }
  }
  return registry
}

/** 表级信息：用途/状态/归类/索引/权限/保留。只查存在性。 */
function checkTableInfo(doc, section, table, report) {
  const meta = sectionMeta(section, table.line)
  const preamble = sectionPreamble(section, table.line)

  for (const item of TABLE_INFO) {
    const present =
      item.key === '用途' || item.key === '状态' ? meta.has(item.key) : item.pattern.test(preamble)
    if (!present) {
      report.error(doc.file, table.line, section.title, `表缺少「${item.label}」信息`)
    }
  }

  const status = meta.get('状态') ?? ''
  if (status === '') return
  if (!LIFECYCLE_PATTERN.test(status) && !DESIGN_RESERVED_PATTERN.test(status)) {
    report.error(
      doc.file,
      table.line,
      section.title,
      `状态「${status}」不在四级口径内（设计草案/评审确认/迁移已实现/真实 PostgreSQL 测试通过）`,
    )
  }
  if (DESIGN_RESERVED_PATTERN.test(status) && IMPLEMENTED_PATTERN.test(status)) {
    report.error(
      doc.file,
      table.line,
      section.title,
      `状态同时标注设计保留与已实现（「${status}」）——设计保留的实体本轮不得声称已建表`,
    )
  }
}

function checkNullable(doc, tableName, field, line, nullableCell, keyCell, report) {
  const nullable = nullableCell.trim()
  if (nullable !== '是' && nullable !== '否') {
    report.error(doc.file, line, tableName, `字段 ${field} 的可空列「${nullable}」只能是 是/否`)
  }
  if (/\bPK\b/.test(keyCell) && nullable === '是') {
    report.error(doc.file, line, tableName, `字段 ${field} 声明为主键却允许为空`)
  }
}

/** 默认值 vs 枚举/CHECK：能对账就对账，对不了账标「未验证」，不默认为通过。 */
function checkDefaultAgainstEnum(doc, tableName, field, line, defaultCell, valuesCell, report) {
  const literal = unquote(defaultCell)
  if (!LITERAL_PATTERN.test(literal)) return

  const inMatch = CHECK_IN_PATTERN.exec(valuesCell)
  if (inMatch) {
    const allowed = inMatch[1]
      .split(',')
      .map((item) => unquote(clean(item)).toLowerCase())
      .filter(Boolean)
    const value = literal.toLowerCase()
    if (!allowed.includes(value) && !BUILTIN_DEFAULTS.has(value)) {
      report.error(
        doc.file,
        line,
        tableName,
        `字段 ${field} 的默认值「${literal}」不在取值范围 ${allowed.join('/')} 内`,
      )
    }
    return
  }
  if (/CHECK/i.test(valuesCell)) {
    report.todo(
      doc.file,
      line,
      tableName,
      `字段 ${field} 的默认值「${literal}」无法与取值范围表达式对账（未验证）`,
    )
  }
}

/** FK：给了就必须指向已登记的表与列。 */
function checkForeignKey(doc, tableName, field, line, keyCell, registry, report) {
  if (!/FK/i.test(keyCell) || NO_FK_PATTERN.test(keyCell)) return
  const refs = [...keyCell.matchAll(REFERENCE_PATTERN)]
  if (refs.length === 0) {
    report.error(doc.file, line, tableName, `字段 ${field} 的 FK 列没有给出 表.字段`)
    return
  }
  for (const [, refTable, refColumn] of refs) {
    const target = registry.get(refTable)
    if (!target) {
      report.error(
        doc.file,
        line,
        tableName,
        `字段 ${field} 的外键指向未登记的表 ${refTable}（悬空 FK）`,
      )
    } else if (!target.fields.has(refColumn.toLowerCase())) {
      report.error(
        doc.file,
        line,
        tableName,
        `字段 ${field} 的外键指向 ${refTable} 不存在的列 ${refColumn}`,
      )
    }
  }
}

/** 七列逐行校验，返回本表的 JSONB 列名。 */
function checkRows(doc, section, table, registry, report) {
  const tableName = section.title
  const seen = new Map()
  const jsonbColumns = new Set()

  for (const row of table.rows) {
    const field = clean(row.cells[0])
    if (!field) {
      report.error(doc.file, row.line, tableName, '存在空字段名行')
      continue
    }
    if (row.cells.length !== SEVEN_HEADERS.length) {
      report.error(
        doc.file,
        row.line,
        tableName,
        `字段 ${field} 的列数为 ${row.cells.length}，应为 7（缺列或多列都不接受）`,
      )
      continue
    }

    const [, , typeCell, nullableCell, defaultCell, valuesCell, keyCell] = row.cells

    const lower = field.toLowerCase()
    if (seen.has(lower)) {
      report.error(
        doc.file,
        row.line,
        tableName,
        `字段 ${field} 重复（首次出现在第 ${seen.get(lower)} 行）`,
      )
    } else {
      seen.set(lower, row.line)
    }

    row.cells.forEach((cell, index) => {
      if (cell.trim() === '') {
        report.error(
          doc.file,
          row.line,
          tableName,
          `字段 ${field} 的第 ${index + 1} 列（${SEVEN_HEADERS[index]}）为空——没有就写「无」`,
        )
      }
    })

    checkNullable(doc, tableName, field, row.line, nullableCell, keyCell, report)
    checkDefaultAgainstEnum(doc, tableName, field, row.line, defaultCell, valuesCell, report)
    checkForeignKey(doc, tableName, field, row.line, keyCell, registry, report)

    if (typeCell.toLowerCase().includes('jsonb')) jsonbColumns.add(field)
  }

  return jsonbColumns
}

/**
 * JSONB 内部字典：不仅要「有这一节」，还要每个属性行七列齐全、
 * 每个 JSONB 列都有 schemaVersion、属性必须挂在已声明的列下。
 */
function checkJsonb(doc, jsonbColumns, report) {
  if (jsonbColumns.size === 0) return

  if (!doc.jsonbSection) {
    report.error(
      doc.file,
      1,
      null,
      `存在 JSONB 列（${[...jsonbColumns].join('、')}）但没有「JSONB内部字典」小节`,
    )
    return
  }

  const declared = new Set()
  const seen = new Map()

  for (const table of doc.jsonbSection.tables) {
    for (const row of table.rows) {
      const path = clean(row.cells[0])
      if (!path) {
        report.error(doc.file, row.line, 'JSONB内部字典', '存在空属性名行')
        continue
      }
      if (row.cells.length !== SEVEN_HEADERS.length) {
        report.error(
          doc.file,
          row.line,
          'JSONB内部字典',
          `属性 ${path} 的列数为 ${row.cells.length}，应为 7`,
        )
        continue
      }
      row.cells.forEach((cell, index) => {
        if (cell.trim() === '') {
          report.error(
            doc.file,
            row.line,
            'JSONB内部字典',
            `JSONB 属性 ${path} 的第 ${index + 1} 列（${SEVEN_HEADERS[index]}）为空`,
          )
        }
      })

      const lower = path.toLowerCase()
      if (seen.has(lower)) {
        report.error(
          doc.file,
          row.line,
          'JSONB内部字典',
          `JSONB 属性 ${path} 重复（首次出现在第 ${seen.get(lower)} 行）`,
        )
      } else {
        seen.set(lower, row.line)
      }

      const [column] = path.split('.')
      if (!jsonbColumns.has(column)) {
        report.error(
          doc.file,
          row.line,
          'JSONB内部字典',
          `JSONB 属性 ${path} 挂在未声明的 JSONB 列 ${column} 下`,
        )
        continue
      }
      declared.add(lower)
    }
  }

  for (const column of jsonbColumns) {
    if (!declared.has(`${column.toLowerCase()}.schemaversion`)) {
      report.error(
        doc.file,
        1,
        null,
        `JSONB 列 ${column} 缺少 schemaVersion 属性（内部结构必须带版本）`,
      )
    }
  }
}

/**
 * 映射表：领域表.列 必须落在已登记表上。
 *
 * 未登记的表在局部模式只提醒（owner 的字典还没提交，M2 修不了）；
 * 全量模式视为错误，否则「缺五份字典」也能输出「通过」。
 */
function checkMappings(doc, registry, report, unresolved) {
  for (const { table, column } of doc.mappings) {
    for (const row of table.rows) {
      const cell = clean(row.cells[column])
      for (const [, tableName, columnName] of cell.matchAll(REFERENCE_PATTERN)) {
        const target = registry.get(tableName)
        if (!target) {
          const hit = unresolved.get(tableName)
          if (hit) hit.count += 1
          else unresolved.set(tableName, { count: 1, line: row.line })
          continue
        }
        if (!target.fields.has(columnName.toLowerCase())) {
          report.error(
            doc.file,
            row.line,
            tableName,
            `映射引用了 ${tableName}.${columnName}，但该表没有登记这一列`,
          )
        }
      }
    }
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    process.stdout.write(`${usage()}\n`)
    return 0
  }
  if (options.invalid) {
    process.stderr.write(`${options.invalid}\n\n${usage()}\n`)
    return 2
  }

  const docDir = join(options.root, 'docs', 'data-model')
  if (!existsSync(docDir)) {
    process.stderr.write(`找不到 docs/data-model/（root=${options.root}）\n`)
    return 2
  }

  const report = new Report()
  const missing = new Set()

  if (options.full) {
    const required = [...SHARED_FILES.map((file) => ({ file, owner: '公共' })), ...MODULES]
    for (const entry of required) {
      if (!existsSync(join(docDir, entry.file))) {
        missing.add(entry.file)
        report.error(
          `docs/data-model/${entry.file}`,
          1,
          null,
          `缺少模块文件（owner ${entry.owner}）——不得为通过检查而新建空文件`,
        )
      }
    }
  }

  // 登记阶段读所有已存在的模块文件：局部检查时也要能解析引用到别人的表，
  // 否则「目标存在但未选中」会被误报成未登记。
  const loaded = new Map()
  for (const entry of MODULES) {
    if (missing.has(entry.file)) continue
    const path = join(docDir, entry.file)
    if (!existsSync(path)) continue
    const text = readFileSync(path, 'utf8')
    loaded.set(entry.file, { text, doc: text.trim() === '' ? null : parseDoc(entry.file, text) })
  }

  const registry = buildRegistry(
    [...loaded.values()].filter((item) => item.doc !== null).map((item) => item.doc),
    report,
  )

  const selected = options.full ? MODULES.map((entry) => entry.file) : options.files
  for (const name of selected) {
    if (missing.has(name)) continue
    const entry = loaded.get(name)
    if (!entry) {
      report.error(`docs/data-model/${name}`, 1, null, '文件不存在')
      continue
    }
    if (entry.doc === null) {
      report.error(`docs/data-model/${name}`, 1, null, '文件为空')
      continue
    }

    const doc = entry.doc
    if (!/owner\s*[：:]/.test(doc.text)) {
      report.error(doc.file, 1, null, '文档未标注 owner（需要 `owner：Mx`）')
    }

    const jsonbColumns = new Set()
    for (const { section, table } of doc.tables) {
      checkTableInfo(doc, section, table, report)
      for (const column of checkRows(doc, section, table, registry, report)) {
        jsonbColumns.add(column)
      }
    }
    checkJsonb(doc, jsonbColumns, report)

    const unresolved = new Map()
    checkMappings(doc, registry, report, unresolved)
    for (const [tableName, { count, line }] of unresolved) {
      const message = `映射引用了未登记的表 ${tableName}（${count} 处）`
      if (options.full) {
        report.error(doc.file, line, tableName, `${message}——全量检查不接受未登记引用`)
      } else {
        report.warn(doc.file, line, tableName, `${message}——待对应 owner 的字典合并后自动校验`)
      }
    }

    if (doc.tables.length === 0 && !NO_TABLE_DECLARATION.test(doc.text)) {
      report.error(
        doc.file,
        1,
        null,
        '没有登记任何字典表，也没有写「本文件不登记新表」——空文件不得静默通过',
      )
    }
  }

  const byFile = new Map()
  const push = (bucket, item) => {
    if (!byFile.has(item.file)) byFile.set(item.file, { errors: [], todo: [], warnings: [] })
    byFile.get(item.file)[bucket].push(item)
  }
  report.errors.forEach((item) => push('errors', item))
  report.unverified.forEach((item) => push('todo', item))
  report.warnings.forEach((item) => push('warnings', item))

  for (const [file, group] of [...byFile].sort(([a], [b]) => a.localeCompare(b))) {
    process.stdout.write(`${file}\n`)
    const print = (mark, items) => {
      for (const item of items) {
        const table = item.table ? `[${item.table}] ` : ''
        const where = item.line ? `第 ${item.line} 行  ` : ''
        process.stdout.write(`  ${mark} ${where}${table}${item.message}\n`)
      }
    }
    print('✗', group.errors)
    print('?', group.todo)
    print('!', group.warnings)
  }

  process.stdout.write(
    `\n汇总：${report.errors.length} 个错误，${report.unverified.length} 项未验证，` +
      `${report.warnings.length} 条提醒，已登记 ${registry.size} 张表\n`,
  )

  if (report.errors.length > 0) {
    const scope = options.full ? '未完成全量验收' : '未通过（局部检查）'
    process.stdout.write(
      `结论：${scope}，${report.errors.length} 个错误。缺项须补齐，不得靠删检查、填空列或新建空文件通过\n`,
    )
    return 1
  }
  if (options.full) {
    const suffix =
      report.unverified.length > 0
        ? `，其中 ${report.unverified.length} 项无法自动核验，需人工复核`
        : ''
    process.stdout.write(`结论：通过（全量）${suffix}\n`)
    return 0
  }
  process.stdout.write(
    `结论：通过（局部检查：${(options.files ?? []).join(', ')}；未做全量验收）\n`,
  )
  return 0
}

process.exitCode = main()
