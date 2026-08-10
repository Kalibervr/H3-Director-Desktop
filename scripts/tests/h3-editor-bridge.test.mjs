import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const bridge = readFileSync(new URL('../../frontend/lib/h3-editor-bridge.ts', import.meta.url), 'utf8')
const home = readFileSync(new URL('../../frontend/views/Home.tsx', import.meta.url), 'utf8')
const app = readFileSync(new URL('../../frontend/App.tsx', import.meta.url), 'utf8')
const project = readFileSync(new URL('../../frontend/views/Project.tsx', import.meta.url), 'utf8')
const model = readFileSync(new URL('../../frontend/types/project-model.ts', import.meta.url), 'utf8')
const storage = readFileSync(new URL('../../frontend/lib/project-storage.ts', import.meta.url), 'utf8')
const exportHandler = readFileSync(new URL('../../electron/export/export-handler.ts', import.meta.url), 'utf8')

test('H3 editor bridge uses selected immutable versions in scene order', () => {
  assert.match(bridge, /sort\(\(a, b\) => a\.order - b\.order\)/)
  assert.match(bridge, /selected_render_version_id/)
  assert.match(bridge, /path: version\.video_file/)
  assert.match(bridge, /startTime \+= duration/)
})

test('editor assets retain complete H3 provenance', () => {
  for (const field of ['projectId', 'sceneId', 'renderVersionId', 'outputSha256', 'metadataFile']) {
    assert.match(model, new RegExp(field))
    assert.match(bridge, new RegExp(field))
  }
})

test('existing editor projects are not silently rebuilt', () => {
  assert.match(home, /existing\s*\? replaceVersions \? replaceH3EditorVersions\(project, existing\) : existing/)
  assert.match(home, /Update \{editorUpdates\.length\} selected version/)
})

test('navigation opens existing editor and returns to H3 Director', () => {
  assert.match(app, /currentView === 'project' \? <Project \/> : <Home \/>/)
  assert.match(home, /openProject\(editorProjectId, 'video-editor'\)/)
  assert.match(project, /H3 Director Desktop/)
  assert.match(project, /goHome/)
})

test('editor state is mirrored separately and FFmpeg 9 reads the filtergraph from file', () => {
  assert.match(storage, /editor-project\.json/)
  assert.match(storage, /window\.electronAPI\.saveFile/)
  assert.match(exportHandler, /'-\/filter_complex', filterFile/)
  assert.doesNotMatch(exportHandler, /filter_complex_script/)
})
