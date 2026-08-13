import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

test('MiniMax H3 Prompt Only is registered for its exact runtime-verified scope', () => {
  const profiles = read('frontend/lib/h3-workflow-profiles.ts')
  const home = read('frontend/views/Home.tsx')
  assert.match(profiles, /minimax_h3_no_reference/)
  assert.match(profiles, /status: 'runtime_verified'/)
  assert.match(profiles, /label: 'Prompt Only'/)
  assert.match(profiles, /verified: true/)
  assert.match(home, /miniMaxH3ModeOptions/)
  assert.match(home, /Generate without a reference image/)
  assert.match(home, /profile\.status === 'verified' \|\| profile\.status === 'runtime_verified'/)
})
