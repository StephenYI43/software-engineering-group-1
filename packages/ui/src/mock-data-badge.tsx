export type MockDataBadgeProps = {
  /** 补充说明数据来源，例如「契约样例」或「本地 Mock」。不替代「示意数据」这个判断。 */
  source?: string
}

/**
 * 示意数据标识。
 *
 * 这个组件存在的理由是一条硬约束：`AGENTS.md:8`「Mock 必须明确标记，不能当
 * 生产完成证据」。它表达的是**「这份数据不是真实运行结果」**。
 *
 * 不要用契约里的 `isMock` 字段兼职表达这件事——`isMock` 的语义是
 * **运行时来源**（这一轮回答是否由 `MockModelClient` 生成），两者含义不同。
 * 见 `packages/contracts/tutoring/samples/README.md` 的「消费方注意」一节。
 *
 * `source` 是**补充**而非替换：无论调用方传什么，「示意数据」这个判断都必须出现，
 * 否则一个写了来源说明的调用方会无意中把标识本身挤掉。
 */
export function MockDataBadge({ source }: MockDataBadgeProps) {
  return (
    <p className="ui-mock-badge" role="note">
      ⚠ 示意数据
      {source !== undefined && source !== '' && `（${source}）`}
      ，不是真实模型输出，也不是已实现功能的证据
    </p>
  )
}
