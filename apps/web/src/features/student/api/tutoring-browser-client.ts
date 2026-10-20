import { createTutoringClient } from './tutoring-client'

/** 开发演示显式标记；?live=1 或生产构建使用真实 HTTP，不降级伪造回答。 */
export function createBrowserTutoringClient(search: string) {
  const isDemo = import.meta.env.DEV && new URLSearchParams(search).get('live') !== '1'
  let demoFetch: Promise<typeof globalThis.fetch> | undefined
  const client = createTutoringClient({
    fetch: async (input, init) => {
      if (import.meta.env.DEV && isDemo) {
        demoFetch ??= import('../mocks/tutoring-stream').then((module) =>
          module.createMockTutoringFetch(search),
        )
        return (await demoFetch)(input, init)
      }
      return globalThis.fetch(input, init)
    },
  })
  return { client, isDemo }
}
