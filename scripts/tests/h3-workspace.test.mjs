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
  for (const label of ['Projects', 'Recent Projects', 'New Project', 'Scene prompt', 'Reference image', 'Format', 'Resolution', 'FPS', 'Duration', 'Frames', 'Seed', 'Render Scene', 'Storyboard']) {
    assert.match(home, new RegExp(label))
  }
  assert.doesNotMatch(home, /workflow JSON|class_type|node graph|LTX API|FAL AI|API key/)
})

test('duration is editable and frames use the documented MiniMax H3 17k+5 mapping', () => {
  const home = read('frontend/views/Home.tsx')
  assert.match(home, /h3FrameCountForDuration/)
  assert.match(home, /Math\.round\(durationSeconds \* fps\)/)
  assert.match(home, /17k\+5 grid/)
  assert.match(home, /updateSceneLocally\(\{ duration_seconds: duration, frame_count: h3FrameCountForDuration/)
  assert.equal((home.match(/Duration \(seconds\)/g) || []).length, 1)
  assert.match(home, /<option value="1:1 \(Square\)">1:1<\/option>/)
  assert.match(home, /<option value="16:9 \(Widescreen\)">16:9<\/option>/)
  assert.match(home, /<option value="9:16 \(Portrait Widescreen\)">9:16<\/option>/)
  assert.match(home, /derived from format/)
  assert.match(home, /'16:9 \(Widescreen\)': \{ 0\.4: \[864, 480\]/)
  assert.match(home, /updateSceneLocally\(\{ aspect_ratio: aspectRatio, width, height \}\)/)
  assert.match(home, /resolution_megapixels: resolutionMegapixels, width, height/)
  assert.match(home, /Resolution<\/div><select value=\{scene\.resolution_megapixels\}/)
  assert.equal((home.match(/Duration \(seconds\)/g) || []).length, 1)
  assert.match(home, /Fixed workflow value/)
})

test('renderer calls only local sanitized project and MiniMax H3 backend boundaries', () => {
  const client = read('frontend/lib/h3-generation.ts') + read('frontend/lib/h3-projects.ts')
  assert.match(client, /\/api\/comfyui\/minimax-h3\/status/)
  assert.match(client, /\/api\/comfyui\/minimax-h3\/projects/)
  assert.match(client, /\/scenes\/\$\{encodeURIComponent\(sceneId\)\}\/render/)
  assert.match(client, /base_url: baseUrl/)
  assert.doesNotMatch(client, /127\.0\.0\.1:8188/)
  assert.doesNotMatch(client, /https:\/\//)
  assert.doesNotMatch(client, /class_type|object_info|workflow JSON|node graph|api[_-]?key/i)
})

test('workspace exposes disk persistence, immutable versions and truthful phase status', () => {
  const home = read('frontend/views/Home.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Render version', 'Retry Render', 'Real sampler progress only', 'Preparing input', 'Verifying with ffprobe']) {
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
})

test('workspace exposes manual continuity with ordered queue controls', () => {
  const home = read('frontend/views/Home.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Scene Mode', 'New Shot', 'Continue Previous', 'Same Character, New Shot', 'Continuity source', 'Extraction strategy', 'Offset from end', 'Extract Continuity Frame']) assert.match(home, new RegExp(label))
  assert.match(projectClient, /prepareH3Continuity/)
  assert.match(projectClient, /continuity_artifacts/)
  for (const label of ['Render From Here', 'Render All', 'Run history', 'Stop after current scene']) assert.match(home, new RegExp(label))
  for (const operation of ['startH3Sequence', 'stopH3Sequence', 'render_runs']) assert.match(projectClient, new RegExp(operation))
  assert.doesNotMatch(home, /\d+% complete|automatic retry/i)
})

test('director workspace exposes persistent run history, verified progress and version navigation', () => {
  const home = read('frontend/views/Home.tsx')
  const storyboard = read('frontend/components/SceneStoryboard.tsx')
  const projectClient = read('frontend/lib/h3-projects.ts')
  for (const label of ['Run history', 'Elapsed', 'Technical diagnostics', 'Previous version', 'Next version', 'Prompt ID']) assert.match(home, new RegExp(label))
  assert.match(home + storyboard, /progress_value/)
  assert.match(home + storyboard, /progress_max/)
  assert.match(projectClient, /current_phase/)
  assert.doesNotMatch(home + storyboard, /setInterval\([^)]*progress|estimated progress|smooth/i)
})
