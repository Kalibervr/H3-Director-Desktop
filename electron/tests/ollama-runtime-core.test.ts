import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { OllamaRuntimeCore } from '../ollama-runtime-core.js'

function child(pid: number) {
  const process = new EventEmitter() as EventEmitter & { pid: number; stdout: EventEmitter; stderr: EventEmitter; kill: () => void; killed: boolean }
  process.pid = pid; process.stdout = new EventEmitter(); process.stderr = new EventEmitter(); process.killed = false
  process.kill = () => { process.killed = true; process.emit('exit', 0, null) }
  return process
}

function core(options: { reachable?: boolean[]; executable?: boolean; autoStart?: boolean } = {}) {
  const saved: unknown[] = []; const children: ReturnType<typeof child>[] = []; const reachable = [...(options.reachable ?? [false])]
  const runtime = new OllamaRuntimeCore({
    getConfig: () => ({ autoStart: Boolean(options.autoStart), endpoint: 'http://127.0.0.1:11434', model: 'qwen3:4b' }),
    saveConfig: value => saved.push(value), existsSync: () => options.executable ?? true,
    execFileSync: (() => { throw new Error('not on PATH') }) as never,
    fetch: (async () => new Response('', { status: reachable.shift() ?? true ? 200 : 503 })) as typeof fetch,
    spawn: (() => { const next = child(100 + children.length); children.push(next); return next }) as never,
  })
  return { runtime, children, saved }
}

test('detects an external local Ollama and never claims ownership', async () => {
  const setup = core({ reachable: [true] })
  const status = await setup.runtime.getStatus()
  assert.equal(status.state, 'ready'); assert.equal(status.owned, false)
  assert.equal((await setup.runtime.start()).owned, false); assert.equal(setup.children.length, 0)
  assert.match(setup.runtime.stop().error ?? '', /managed/)
  assert.match((await setup.runtime.restart()).error ?? '', /managed/)
})

test('starts, reaches readiness, stops, and cleans up only its owned child', async () => {
  const setup = core({ reachable: [false, true, false, true] })
  const ready = await setup.runtime.start()
  assert.equal(ready.state, 'ready'); assert.equal(ready.owned, true); assert.equal(ready.pid, 100)
  const restarted = await setup.runtime.restart()
  assert.equal(setup.children[0].killed, true)
  assert.equal(restarted.owned, true); assert.equal(restarted.pid, 101)
  setup.runtime.shutdown(); assert.equal(setup.children[1].killed, true)
})

test('reports not-installed without spawning and persists only loopback configuration', async () => {
  const setup = core({ executable: false, reachable: [false] })
  assert.equal((await setup.runtime.getStatus()).state, 'not_installed')
  assert.equal(setup.children.length, 0)
  const saved = setup.runtime.saveConfig({ autoStart: true, endpoint: 'http://127.0.0.1:11434', model: 'qwen3:4b' })
  assert.equal(saved.endpoint, 'http://127.0.0.1:11434'); assert.equal(saved.model, 'qwen3:4b'); assert.equal(setup.saved.length, 1)
})

test('auto-start uses the same managed start path only when persisted on', async () => {
  const setup = core({ autoStart: true, reachable: [false, true] })
  const status = await setup.runtime.autoStart()
  assert.equal(status.state, 'ready'); assert.equal(status.owned, true); assert.equal(setup.children.length, 1)
  setup.runtime.shutdown()
})
