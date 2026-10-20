/** Manual localhost integration check; not imported by the app or collected by Vitest. */
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import type { TutoringRun } from '../tutoring-client'
import type { TutoringEvent } from '../tutoring-sse'

// Node strips TS syntax but does not resolve the app's extensionless imports.
registerHooks({
  resolve(specifier, context, nextResolve) {
    return nextResolve(
      specifier.startsWith('.') && !/\.[a-z]+$/i.test(specifier) ? `${specifier}.ts` : specifier,
      context,
    )
  },
})

const configuredBase = process.env.M2_HTTP_BASE
assert.ok(configuredBase, 'Set M2_HTTP_BASE explicitly to the local Mock HTTP server')
const base = new URL(configuredBase)
assert.ok(
  base.protocol === 'http:' &&
    ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname) &&
    !base.username &&
    !base.password &&
    base.pathname === '/' &&
    !base.search &&
    !base.hash,
  'M2_HTTP_BASE must be a localhost HTTP origin without credentials, path or query',
)

const { createTutoringClient } = await import('../tutoring-client')
const { createSseDecoder } = await import('../tutoring-sse')
type WireRecord = {
  path: string
  status: number
  events: TutoringEvent[]
  body?: string
}
const records: WireRecord[] = []
const overall = new AbortController()
const timer = setTimeout(() => overall.abort(new Error('HTTP integration exceeded 60s')), 60_000)
const runId = randomUUID().replaceAll('-', '')
const completedSession = `sess_m2_http_${runId}_completed`
const stoppedSession = `sess_m2_http_${runId}_stopped`
const input = {
  content: '合成问题：函数极限中 epsilon 和 delta 的关系？',
  courseId: 'course_b3f1c2d4',
}

// Only redirect the network boundary. The real client and decoder remain unchanged.
const fetchHttp: typeof globalThis.fetch = async (input, init) => {
  assert.ok(typeof input === 'string')
  const target = new URL(input, base)
  assert.equal(target.origin, base.origin)
  const signals = [overall.signal, AbortSignal.timeout(10_000)]
  if (init?.signal) signals.push(init.signal)
  const response = await fetch(target, {
    ...init,
    signal: AbortSignal.any(signals),
    redirect: 'error',
  })
  const record: WireRecord = { path: target.pathname, status: response.status, events: [] }
  records.push(record)
  if (response.headers.get('Content-Type')?.includes('text/event-stream')) {
    assert.ok(response.body)
    const decoder = createSseDecoder()
    const stream = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          decoder.push(chunk, (event) => record.events.push(event))
          controller.enqueue(chunk)
        },
        flush() {
          decoder.finish((event) => record.events.push(event))
        },
      }),
    )
    return new Response(stream, { status: response.status, headers: response.headers })
  }
  record.body = await response.clone().text()
  return response
}
const client = createTutoringClient({ fetch: fetchHttp })

function latestStream(session: string) {
  const wire = records.findLast((record) => record.path.endsWith(`/${session}/messages`))
  assert.ok(wire)
  assert.equal(wire.status, 200)
  return wire
}

async function complete(session: string) {
  const result = await client.start(session, input, () => {}).done
  assert.equal(result.status, 'completed', result.error?.message)
  assert.equal(result.isComplete, true)
  assert.ok(result.response)
  assert.equal(result.response.isMock, true)
  const wire = latestStream(session)
  const deltas = wire.events.filter((event) => event.type === 'delta')
  assert.equal(deltas.map((event) => event.textDelta).join(''), result.response.content)
  assert.equal(result.content, result.response.content)
  assert.ok(result.content.endsWith('\n'))
  assert.ok(result.response.citations.some((citation) => citation.documentId === 'doc_9a2f4c'))
  assert.equal(wire.events.at(-1)?.type, 'completed')
  console.log(
    `completed: stage=${result.stage}, deltas=${deltas.length}, trailing newline, exact content`,
  )
  return result
}

try {
  const first = await complete(completedSession)
  assert.equal(first.stage, 'thought')
  console.log('PASS 1/5 normal completion and delta/newline equality')

  let stopPromise: Promise<void> | undefined
  const run: TutoringRun = client.start(stoppedSession, input, (state) => {
    if (state.status === 'streaming' && state.content && stopPromise === undefined) {
      stopPromise = run.stop()
    }
  })
  const stopped = await run.done
  assert.ok(stopPromise, 'Expected at least one real delta before requesting stop')
  await stopPromise
  assert.equal(stopped.status, 'stopped', stopped.error?.message)
  assert.equal(stopped.stage, 'thought')
  assert.equal(stopped.isComplete, false)
  assert.equal(stopped.response, null)
  assert.ok(stopped.content.length > 0)
  const terminal = latestStream(stoppedSession).events.at(-1)
  assert.equal(terminal?.type, 'stopped')
  assert.ok(terminal?.type === 'stopped')
  assert.equal(terminal.reason, 'client_stop')
  const stopHttp = records.find((record) => record.path.endsWith(`/${stopped.turnId}/stop`))
  assert.equal(stopHttp?.status, 204)
  assert.equal(stopHttp.body, '')
  console.log('PASS 2/5 stop HTTP 204 empty body, stopped/client_stop, partial incomplete')

  const retry = await complete(stoppedSession)
  assert.equal(retry.stage, 'thought')
  assert.notEqual(retry.turnId, stopped.turnId)
  console.log('PASS 3/5 retry creates new turn, stopped stage thought -> thought')

  const unknown = await fetchHttp(
    `/api/v1/tutoring/sessions/${stoppedSession}/turns/turn_unknown_synthetic/stop`,
    { method: 'POST' },
  )
  assert.equal(unknown.status, 404)
  const unknownBody: unknown = await unknown.json()
  assert.ok(typeof unknownBody === 'object' && unknownBody !== null)
  assert.ok('code' in unknownBody && unknownBody.code === 'TUTORING_TURN_NOT_FOUND')
  assert.ok('requestId' in unknownBody && typeof unknownBody.requestId === 'string')
  console.log('PASS 4/5 unknown turn HTTP 404 TUTORING_TURN_NOT_FOUND with requestId')

  const finishedStop = `/api/v1/tutoring/sessions/${completedSession}/turns/${first.turnId}/stop`
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetchHttp(finishedStop, { method: 'POST' })
    assert.equal(response.status, 204)
    assert.equal(await response.text(), '')
  }
  const next = await complete(completedSession)
  assert.equal(next.stage, 'hint')
  assert.notEqual(next.turnId, first.turnId)
  console.log('PASS 5/5 completed stop twice HTTP 204, new turn thought -> hint (one advance)')
  console.log('PASS 5/5 real HTTP groups; synthetic identity/model/retrieval/in-memory only')
} finally {
  clearTimeout(timer)
  overall.abort()
  // No request headers, credentials or question bodies are recorded. Use synthetic data only.
  if (process.env.M2_HTTP_WIRE_PATH) {
    writeFileSync(process.env.M2_HTTP_WIRE_PATH, JSON.stringify({ runId, records }, null, 2))
  }
}
