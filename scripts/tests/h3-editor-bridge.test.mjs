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
const assetsPanel = readFileSync(new URL('../../frontend/views/editor/VideoEditorAssetsPanel.tsx', import.meta.url), 'utf8')
const timelinePanel = readFileSync(new URL('../../frontend/views/editor/VideoEditorTimelineEditingPanel.tsx', import.meta.url), 'utf8')

test('H3 editor bridge uses selected immutable versions in scene order', () => {
  assert.match(bridge, /sort\(\(a, b\) => a\.order - b\.order\)/)
  assert.match(bridge, /selected_render_version_id/)
  assert.match(bridge, /path: version\.video_file/)
  assert.match(bridge, /startTime \+= duration/)
})

test('editor assets retain complete H3 provenance', () => {
  for (const field of ['projectId', 'sceneId', 'renderVersionId', 'sceneNumber', 'renderVersionNumber', 'outputSha256', 'metadataFile']) {
    assert.match(model, new RegExp(field))
    assert.match(bridge, new RegExp(field))
  }
})

test('H3 labels use persisted project scene order and render version numbers, not filenames', () => {
  assert.match(bridge, /orderedScenes\(project\)/)
  assert.match(bridge, /sceneNumber: sceneIndex \+ 1/)
  assert.match(bridge, /renderVersionNumber: version\.number/)
  assert.match(bridge, /Scene \$\{String\(source\.sceneNumber\)/)
  assert.match(bridge, /refreshH3EditorProvenance/)
})

test('H3 provenance labels are rendered in asset grid, list, and existing timeline clip labels', () => {
  assert.match(assetsPanel, /const h3Label = getH3AssetDisplayLabel\(asset\)/)
  assert.match(assetsPanel, /\{h3Label \?\? \(asset\.type === 'adjustment'/)
  assert.match(assetsPanel, /const name = h3Label \?\? \(/)
  assert.match(timelinePanel, /getH3AssetDisplayLabel\(clip\.asset, false\)/)
})

test('Director keeps backend details collapsed until Advanced backend settings is opened', () => {
  assert.match(home, /<details className="mt-3 border-t border-white\/10 pt-3"><summary[^>]*>Advanced backend settings<\/summary>/)
  assert.match(home, /Ready \/ \$\{lifecycle\.owned \? 'H3 managed' : 'External'\}/)
  assert.match(home, /lifecycle\?\.diagnostics\.length/)
  assert.doesNotMatch(home, /Managed runtime settings/)
})

test('existing editor projects retain their edits while display provenance is refreshed', () => {
  assert.match(home, /existing\s*\? replaceVersions \? replaceH3EditorVersions\(project, existing\) : refreshH3EditorProvenance\(project, existing\)/)
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
