import type { TutoringResponse } from '../types'

/**
 * 示意数据标记。
 *
 * 契约要求 fixture 层**显式声明来源**，而不是复用响应里的 `isMock` 字段：
 *
 * > `isMock` 表达的是「这一轮回答是否由 `MockModelClient` 生成」，是**运行时来源**，
 * > 不是「这个文件是不是假数据」。若 M2 把本目录样例用作前端 fixture，**不要用
 * > `isMock` 兼职表达「这是示意数据」**——请在 fixture 层显式声明来源。
 * > 　—— `packages/contracts/tutoring/samples/README.md`
 *
 * 违反这条的后果很具体：`05-sse-stream.txt` 变体三的 `isMock=false` 是为了演示
 * 「不显示 Mock 标识」那条渲染路径；若把它当「非假数据」的标记，示意数据就会被
 * 渲染成真实模型输出，违反 `AGENTS.md:8`。
 */
export type Fixture<T> = T & {
  /** 恒为 true：这份数据是手工构造的示意数据，不是真实运行结果。 */
  _fixture: true
}

/**
 * 以下三条逐字取自 `packages/contracts/tutoring/samples/`，
 * 仅追加 `_fixture: true`，未改动任何契约字段。
 *
 * | fixture | 来源文件 |
 * | --- | --- |
 * | `thoughtWithCitation` | `01-thought-with-citation.json` |
 * | `summaryAfterAttempt` | `02-summary-after-attempt.json` |
 * | `noEvidence` | `03-no-evidence.json` |
 */

/** 首轮回答，`thought` 阶段，带页码引用。 */
export const thoughtWithCitation: Fixture<TutoringResponse> = {
  _fixture: true,
  turnId: 'turn_7f3a9c21',
  sessionId: 'sess_4b8d1e02',
  stage: 'thought',
  content:
    '我们先不急着写出定义。你想一想，说「当 x 靠近 a 时 f(x) 趋近 L」，这里的「靠近」是一种动态描述——那我怎么用一个确定的、可以检验的说法，来代替这个「靠近」呢？\n\n提示你一个方向：既然要「可以检验」，就得分清楚谁先给定、谁随之确定。你先说说看，在这个定义里，应该先给定哪一个量？',
  citations: [
    {
      citationId: 'c1',
      documentId: 'doc_9a2f4c',
      documentTitle: '高等数学-上册-第1章.pdf',
      pageNumber: 12,
      snippet:
        '设函数 f(x) 在点 a 的某个去心邻域内有定义。如果存在常数 L，使得对于任意给定的正数 ε，总存在正数 δ，当 0 < |x - a| < δ 时，有 |f(x) - L| < ε，则称 L 为函数 f(x) 当 x→a 时的极限。',
    },
  ],
  hasEvidence: true,
  followUps: ['那 ε 和 δ 哪个是先给定的？', '如果只从右侧趋近，结论还成立吗？'],
  emotion: 'encouraging',
  action: 'nod',
  isMock: true,
  promptVersion: 'guided-tutoring.v1',
  createdAt: '2026-09-14T08:00:00Z',
}

/** 学生尝试后，`summary` 阶段给出教学解释，两条引用。 */
export const summaryAfterAttempt: Fixture<TutoringResponse> = {
  _fixture: true,
  turnId: 'turn_2c81b5d4',
  sessionId: 'sess_4b8d1e02',
  stage: 'summary',
  content:
    '你答对了关键的一点：ε 是先给定的，δ 是随之确定的。这正是这个定义的核心。\n\n把完整逻辑串起来：\n\n1. 任意给定一个正数 ε，它就划定了「离 L 多近」的标准。\n2. 我们要找到正数 δ，使得 x 落在 a 的去心 δ 邻域内时，f(x) 一定落在 L 的 ε 邻域内。\n3. δ 的取法可以依赖 ε，但一旦 ε 给定，δ 就随之确定。\n\n所以要检验极限，就是回答这个问题：「给定这个 ε，我能找到对应的 δ 吗？」\n\n需要注意的边界：条件是 0 < |x - a| < δ，那个「0 <」意味着 x = a 这一点本身不参与讨论——函数在 a 点有没有定义、取值多少，都不影响极限。这一点初学时最容易忽略。',
  citations: [
    {
      citationId: 'c1',
      documentId: 'doc_9a2f4c',
      documentTitle: '高等数学-上册-第1章.pdf',
      pageNumber: 12,
      snippet:
        '设函数 f(x) 在点 a 的某个去心邻域内有定义。如果存在常数 L，使得对于任意给定的正数 ε，总存在正数 δ，当 0 < |x - a| < δ 时，有 |f(x) - L| < ε，则称 L 为函数 f(x) 当 x→a 时的极限。',
    },
    {
      citationId: 'c2',
      documentId: 'doc_9a2f4c',
      documentTitle: '高等数学-上册-第1章.pdf',
      pageNumber: 14,
      snippet:
        '注意定义中的条件 0 < |x - a| < δ 表示 x ≠ a，即函数在点 a 处是否有定义与极限是否存在无关。',
    },
  ],
  hasEvidence: true,
  followUps: [
    '用这个定义证明 lim(x→2)(2x+1)=5',
    '如果改成 0 < |x - a| < δ 去掉那个「0 <」，会有什么问题？',
  ],
  emotion: 'celebrating',
  action: 'point',
  isMock: true,
  promptVersion: 'guided-tutoring.v1',
  createdAt: '2026-09-14T08:05:30Z',
}

/**
 * 检索不到依据：`citations` 为空数组、`hasEvidence` 为 false。
 *
 * 这是**正常业务结果**，HTTP 仍是 200（契约称 `TUTORING_NO_EVIDENCE` 不是错误）。
 * 界面上必须明确说明找不到依据，且**不得**渲染任何占位引用或编造引用。
 */
export const noEvidence: Fixture<TutoringResponse> = {
  _fixture: true,
  turnId: 'turn_53ea77b1',
  sessionId: 'sess_4b8d1e02',
  stage: 'thought',
  content:
    '这个问题我在当前课程的课件里没有找到相关依据，所以我不给你一个可能不准确的结论。\n\n我检索的范围是这门高等数学课程的已授权课件，其中没有覆盖到这个主题。你可以：\n\n1. 换一种问法，或者确认一下这个知识点是否属于本课程范围；\n2. 如果你是想要延伸学习，我可以基于课程内已讲过的相关概念（比如导数的定义）帮你梳理思路，但那属于课程外的延伸，我会明确标注。\n\n你希望我怎么做？',
  citations: [],
  hasEvidence: false,
  followUps: ['那这门课里和它最接近的知识点是什么？', '帮我看看本课程大纲里有哪些相关章节'],
  emotion: 'neutral',
  action: 'idle',
  isMock: true,
  promptVersion: 'guided-tutoring.v1',
  createdAt: '2026-09-14T08:12:00Z',
}
