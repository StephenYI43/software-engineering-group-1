#!/usr/bin/env node
/**
 * 数据字典检查器（#70 A 批）。
 *
 * 只做静态检查，不连数据库、不生成任何内容：把 `docs/data-model/*.md` 当数据源，
 * 校验七列是否真的填满、字段是否重名、FK 是否指向已登记的表与列、默认值是否与枚举矛盾、
 * 模块清单是否缺文件。**发现缺项就报错，不自动补空列**——自动补全会让「七列没填完」
 * 看起来像「已经填完」，这正是本轮课堂交付要避免的假证据。
 *
 * 用法：
 *   node scripts/check-data-dictionary.mjs                      # 全量：模块清单 + 所有字典
 *   node scripts/check-data-dictionary.mjs --files student.md   # 只查指定文件（owner 自检用）
 *   node scripts/check-data-dictionary.mjs --root <dir>         # 指定仓库根（测试用）
 *
 * 退出码：0 = 无错误；1 = 有错误；2 = 用法错误。
 * 「提醒」不影响退出码：未登记表引用在对应 owner 的字典合并前必然存在，
 * 把它当错误会让所有人一直红着，反而促使有人去删检查。
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

/** 实现状态四级（README 与 #69 共同口径）。 */
const STATUS_PATTERN = /设计草案|评审确认|迁移已实现|真实\s*PostgreSQL/

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

class Report {
  constructor() {
    this.errors = []
    this.warnings = []
  }

  error(file, line, table, message) {
    this.errors.push({ file, line, table, message })
  }

  warn(file, line, table, message) {
    this.warnings.push({ file, line, table, message })
  }
}

/** 去掉 markdown 装饰，便于比较；不改变字段语义。 */
function clean(cell) {
  return (cell ?? '').replace(/`/g, '').replace(/\*\*/g, '').trim()
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

function parseArgs(argv) {
  const options = { root: process.cwd(), files: null, full: true }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--help' || arg === '-h') {
      options.help = true
    } else if (arg === '--root') {
      options.root = resolve(argv[(i += 1)])
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
    '退出码：0 无错误；1 有错误；2 用法错误。',
  ].join('\n')
}

/** 第一遍：读取并登记所有表，供 FK / 映射引用做跨文件校验。 */
function collectDocs(docDir, report, options) {
  const docs = []
  const registry = new Map()

  const missing = new Set()
  if (options.full) {
    for (const entry of [...SHARED_FILES.map((file) => ({ file, owner: '公共' })), ...MODULES]) {
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

  const names = options.files ?? MODULES.map((entry) => entry.file)
  for (const name of names) {
    // 全量模式下缺失已在清单里报过一次，这里不再重复报同一个文件。
    if (missing.has(name)) continue
    const path = join(docDir, name)
    if (!existsSync(path)) {
      report.error(`docs/data-model/${name}`, 1, null, '文件不存在')
      continue
    }
    const text = readFileSync(path, 'utf8')
    const doc = { name, file: `docs/data-model/${name}`, text, tables: [], mappings: [] }
    if (!/owner\s*[：:]/.test(text)) {
      report.error(doc.file, 1, null, '文档未标注 owner（需要 `owner：Mx`）')
    }
    for (const section of splitSections(text)) {
      if (section.title === null) continue
      for (const table of findTables(section)) {
        if (isDictionaryHeader(table.header)) {
          doc.tables.push({ section, table, name: section.title })
          continue
        }
        const column = mappingColumnIndex(table.header)
        if (column >= 0) doc.mappings.push({ section, table, column })
      }
    }
    for (const { section, table, name: tableName } of doc.tables) {
      if (/JSONB/i.test(section.title)) continue
      if (registry.has(tableName)) {
        const previous = registry.get(tableName)
        report.error(
          doc.file,
          table.line,
          tableName,
          `表名与 ${previous.file} 重复登记——一张表只能有一个 owner`,
        )
        continue
      }
      const fields = new Map()
      for (const row of table.rows) {
        const field = clean(row.cells[0])
        if (field) fields.set(field.toLowerCase(), { line: row.line, field })
      }
      registry.set(tableName, { file: doc.file, fields })
    }
    docs.push(doc)
  }
  return { docs, registry }
}

/** 第二遍：逐表逐列校验。 */
function checkDictionaryTable(doc, section, table, registry, report) {
  const tableName = section.title
  const meta = sectionMeta(section, table.line)
  const context = tableName

  for (const key of ['用途', '状态']) {
    if (!meta.get(key)) {
      report.error(doc.file, table.line, context, `表缺少「${key}」说明（七列之外的表级信息）`)
    }
  }
  const status = meta.get('状态') ?? ''
  if (status && !STATUS_PATTERN.test(status)) {
    report.error(
      doc.file,
      table.line,
      context,
      `状态「${status}」不在四级口径内（设计草案/评审确认/迁移已实现/真实 PostgreSQL 测试通过）`,
    )
  }

  const seen = new Map()
  const jsonbColumns = new Set()

  for (const row of table.rows) {
    const field = clean(row.cells[0])
    if (!field) {
      report.error(doc.file, row.line, context, '存在空字段名行')
      continue
    }
    if (row.cells.length !== SEVEN_HEADERS.length) {
      report.error(
        doc.file,
        row.line,
        context,
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
        context,
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
          context,
          `字段 ${field} 的第 ${index + 1} 列（${SEVEN_HEADERS[index]}）为空——没有就写「无」`,
        )
      }
    })

    const nullable = nullableCell.trim()
    if (nullable !== '是' && nullable !== '否') {
      report.error(doc.file, row.line, context, `字段 ${field} 的可空列「${nullable}」只能是 是/否`)
    }
    if (/\bPK\b/.test(keyCell) && nullable === '是') {
      report.error(doc.file, row.line, context, `字段 ${field} 声明为主键却允许为空`)
    }

    // 默认值与枚举矛盾：默认值是裸标识符，却不在 IN(...) 的取值范围内。
    const inMatch = CHECK_IN_PATTERN.exec(valuesCell)
    if (inMatch && LITERAL_PATTERN.test(defaultCell)) {
      const allowed = inMatch[1]
        .split(',')
        .map((item) => clean(item).toLowerCase())
        .filter(Boolean)
      const value = defaultCell.toLowerCase()
      if (!allowed.includes(value) && !BUILTIN_DEFAULTS.has(value)) {
        report.error(
          doc.file,
          row.line,
          context,
          `字段 ${field} 的默认值「${defaultCell}」不在取值范围 ${allowed.join('/')} 内`,
        )
      }
    }

    // FK：给了就必须指向已登记的表与列。
    if (/FK/i.test(keyCell) && !NO_FK_PATTERN.test(keyCell)) {
      const refs = [...keyCell.matchAll(REFERENCE_PATTERN)]
      if (refs.length === 0) {
        report.error(doc.file, row.line, context, `字段 ${field} 的 FK 列没有给出 表.字段`)
      }
      for (const [, refTable, refColumn] of refs) {
        const target = registry.get(refTable)
        if (!target) {
          report.error(
            doc.file,
            row.line,
            context,
            `字段 ${field} 的外键指向未登记的表 ${refTable}（悬空 FK）`,
          )
        } else if (!target.fields.has(refColumn.toLowerCase())) {
          report.error(
            doc.file,
            row.line,
            context,
            `字段 ${field} 的外键指向 ${refTable} 不存在的列 ${refColumn}`,
          )
        }
      }
    }

    if (typeCell.toLowerCase().includes('jsonb')) jsonbColumns.add(field)
  }

  // JSONB 必须给内部结构，不允许用一个 payload 字段掩盖未建模数据（#69）。
  if (jsonbColumns.size > 0) {
    const jsonbSection = splitSections(doc.text).find((item) => /JSONB/i.test(item.title ?? ''))
    if (!jsonbSection) {
      report.error(
        doc.file,
        table.line,
        context,
        `存在 JSONB 列（${[...jsonbColumns].join('、')}）但没有「JSONB内部字典」小节`,
      )
    } else {
      const declared = new Set()
      for (const jsonbTable of findTables(jsonbSection)) {
        for (const row of jsonbTable.rows) {
          const path = clean(row.cells[0])
          if (path.includes('.')) declared.add(path.split('.')[0].toLowerCase())
        }
      }
      for (const column of jsonbColumns) {
        if (!declared.has(column.toLowerCase())) {
          report.error(
            doc.file,
            table.line,
            context,
            `JSONB 列 ${column} 没有在「JSONB内部字典」里给出内部属性`,
          )
        }
      }
    }
  }
}

/**
 * 映射表：领域表.列 必须落在已登记表上。
 *
 * 未登记的表只提醒、不阻塞——那是「owner 的字典还没提交」，不是 M2 能修的缺项；
 * 但同一张表在同一文档里只提醒一次，避免几十行同义提醒把真错误挤出屏幕。
 * 错误（已登记表中的列名写错）仍然逐行报，因为它确实能定位到具体位置。
 */
function checkMappingTable(doc, table, column, registry, report, unresolved) {
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
  const { docs, registry } = collectDocs(docDir, report, options)

  for (const doc of docs) {
    for (const { section, table } of doc.tables) {
      if (/JSONB/i.test(section.title)) continue
      checkDictionaryTable(doc, section, table, registry, report)
    }
    const unresolved = new Map()
    for (const mapping of doc.mappings) {
      checkMappingTable(doc, mapping.table, mapping.column, registry, report, unresolved)
    }
    for (const [tableName, { count, line }] of unresolved) {
      report.warn(
        doc.file,
        line,
        tableName,
        `映射引用了未登记的表 ${tableName}（${count} 处）——待对应 owner 的字典合并后自动校验`,
      )
    }
    const dictionaryTables = doc.tables.filter((item) => !/JSONB/i.test(item.section.title))
    if (dictionaryTables.length === 0 && !NO_TABLE_DECLARATION.test(doc.text)) {
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
    if (!byFile.has(item.file)) byFile.set(item.file, { errors: [], warnings: [] })
    byFile.get(item.file)[bucket].push(item)
  }
  report.errors.forEach((item) => push('errors', item))
  report.warnings.forEach((item) => push('warnings', item))

  for (const [file, group] of [...byFile].sort(([a], [b]) => a.localeCompare(b))) {
    process.stdout.write(`${file}\n`)
    for (const item of group.errors) {
      const table = item.table ? `[${item.table}] ` : ''
      process.stdout.write(`  ✗ 第 ${item.line} 行  ${table}${item.message}\n`)
    }
    for (const item of group.warnings) {
      const table = item.table ? `[${item.table}] ` : ''
      process.stdout.write(`  ! 第 ${item.line} 行  ${table}${item.message}\n`)
    }
  }

  process.stdout.write(
    `\n汇总：${report.errors.length} 个错误，${report.warnings.length} 条提醒，已登记 ${registry.size} 张表\n`,
  )
  if (report.errors.length > 0) {
    process.stdout.write('结论：字典不通过（缺项须补齐，不得靠删检查或填空列通过）\n')
    return 1
  }
  process.stdout.write('结论：通过\n')
  return 0
}

process.exitCode = main()
