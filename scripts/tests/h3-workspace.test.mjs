import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

test('active document and build identity are H3 Director Desktop', () => {
  const html = read('index.html')
  const builder = read('electron-builder.yml')
  const packageJson = JSON.parse(read('package.json'))
  assert.match(html, /<title>H3 Director Desktop<\/title>/)
  assert.doesNotMatch(html, /fonts\.googleapis|fonts\.gstatic/)
  assert.match(builder, /productName: H3 Director Desktop/)
  assert.equal(packageJson.name, 'h3-director-desktop')
})

test('workspace exposes the required first-slice controls without raw graph UI', () => {
  const home = read('frontend/views/Home.tsx')
  for (const label of ['Projects', 'Recent Projects', 'New Project', 'Scene prompt', 'Reference image', 'Width', 'Height', 'FPS', 'Duration', 'Frames', 'Seed', 'Render Scene', 'Storyboard']) {
    assert.match(home, new RegExp(label))
  }
  assert.doesNotMatch(home, /workflow JSON|class_type|node graph|LTX API|FAL AI|API key/)
})

test('renderer calls only local sanitized project and MiniMax H3 backend boundaries', () => {
  const client = read('frontend/lib/h3-generation.ts') + read('frontend/lib/h3-projects.ts')
  assert.match(client, /\/api\/comfyui\/minimax-h3\/status/)
  assert.match(client, /\/api\/comfyui\/minimax-h3\/projects/)
  assert.match(client, /\/scenes\/\$\{encodeURIComponent\(sceneId\)\}\/render/)
  assert.match(client, /http:\/\/127\.0\.0\.1:8188/)
  assert.doesNotMatch(client, /https:\/\//)
  assert.doesNotMatch(client, /class_type|object_info|workflow JSON|node graph|api[_-]?key/i)
})

test('workspace exposes disk persistence, immutable versions and truthful phase status', () => {
  const home = read('frontend/views/Home.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Render version', 'Retry Render', 'Phase status only', 'Preparing input', 'Verifying with ffprobe']) {
    assert.match(home, new RegExp(label))
  }
  assert.match(projectClient, /selected_render_version_id/)
  assert.match(projectClient, /render_versions/)
  assert.doesNotMatch(home, /\d+% complete|progress:\s*\d+/i)
})

test('workspace exposes persistent multi-scene creation and storyboard operations', () => {
  const home = read('frontend/views/Home.tsx')
  const storyboard = read('frontend/components/SceneStoryboard.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Scene count', 'Custom positive scene count', 'Scene name']) assert.match(home, new RegExp(label))
  for (const label of ['Add Scene', 'Duplicate', 'Delete', 'Move']) assert.match(storyboard, new RegExp(label, 'i'))
  for (const operation of ['selectH3Scene', 'addH3Scene', 'duplicateH3Scene', 'deleteH3Scene', 'reorderH3Scenes']) assert.match(projectClient, new RegExp(operation))
  assert.match(storyboard, /overflow-x-auto/)
  assert.doesNotMatch(home + storyboard, /Render All|Render From Here/)
})

test('workspace exposes manual continuity without automatic sequencing claims', () => {
  const home = read('frontend/views/Home.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Scene Mode', 'New Shot', 'Continue Previous', 'Same Character, New Shot', 'Continuity source', 'Extraction strategy', 'Offset from end', 'Extract Continuity Frame']) assert.match(home, new RegExp(label))
  assert.match(projectClient, /prepareH3Continuity/)
  assert.match(projectClient, /continuity_artifacts/)
  assert.doesNotMatch(home, /Render All|Render From Here|automatic sequencing/i)
})
