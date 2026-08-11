import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const manager = readFileSync(new URL('../../electron/comfyui-runtime.ts', import.meta.url), 'utf8')
const core = readFileSync(new URL('../../electron/comfyui-runtime-core.ts', import.meta.url), 'utf8')
const main = readFileSync(new URL('../../electron/main.ts', import.meta.url), 'utf8')

test('managed runtime uses only the verified local-only launch arguments', () => {
  for (const argument of ['-s', 'main.py', '--listen', '127.0.0.1', '--feature-flag', 'enable_telemetry=false', 'show_signin_button=false']) assert.ok(core.includes(argument))
  assert.match(core, /windowsHide:\s*true/)
  assert.doesNotMatch(core, /from 'electron'/)
})

test('external runtimes cannot be stopped or restarted', () => {
  assert.match(core, /Only an H3 Director-owned ComfyUI process can be stopped/)
  assert.match(core, /Only an H3 Director-owned ComfyUI process can be restarted/)
  assert.match(core, /now\.state==='ready'\|\|now\.state==='incompatible'/)
  assert.match(manager, /new ComfyRuntimeCore/)
})

test('app exit stops only the managed runtime', () => {
  assert.match(main, /stopManagedComfyRuntimeOnExit\(\)/)
})
