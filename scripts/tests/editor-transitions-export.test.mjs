import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const timeline = readFileSync(new URL('../../electron/export/timeline.ts', import.meta.url), 'utf8')
const videoFilter = readFileSync(new URL('../../electron/export/video-filter.ts', import.meta.url), 'utf8')
const exportHandler = readFileSync(new URL('../../electron/export/export-handler.ts', import.meta.url), 'utf8')

test('native export resolves only the editor’s verified paired dissolve contract', () => {
  assert.match(timeline, /buildVisualExportPlan/)
  assert.match(timeline, /matching Dissolve In and Dissolve Out/)
  assert.match(timeline, /adjacent clips on the same cut point/)
  assert.match(timeline, /duration cannot be longer than either adjacent clip/)
})

test('native export rejects unsupported persisted transition metadata instead of changing it silently', () => {
  assert.match(timeline, /transitions are preserved but are not supported by local export/)
  assert.match(exportHandler, /TransitionConfigurationError/)
})

test('filter graph uses local FFmpeg xfade while retaining the editor cut timing', () => {
  assert.match(videoFilter, /xfade=transition=fade/)
  assert.match(videoFilter, /select='eq\(n\\\\,0\)'/)
  assert.match(videoFilter, /loop=loop=-1:size=1:start=0/)
  assert.match(videoFilter, /concat=n=2:v=1:a=0/)
})
