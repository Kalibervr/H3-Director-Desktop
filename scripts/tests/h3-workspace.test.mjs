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

test('H3 uses readable native UI typography while technical values remain monospace', () => {
  const css = read('frontend/index.css')
  const home = read('frontend/views/Home.tsx')
  const project = read('frontend/views/Project.tsx')
  assert.match(css, /--ui-font: "Segoe UI", Inter, Arial, sans-serif/)
  assert.match(css, /button,\s*\ninput,\s*\nselect,\s*\ntextarea/)
  assert.match(css, /\.font-mono\s*\{\s*\n\s*font-family: var\(--technical-font\)/)
  assert.match(css, /\.h3-director-ui \.text-zinc-600/)
  assert.match(css, /\.h3-editor-shell \.text-zinc-500/)
  assert.match(home, /h3-director-ui/)
  assert.match(project, /h3-editor-shell/)
  const selectSource = home.slice(home.indexOf('function H3ThemedSelect'), home.indexOf('const H3_RESOLUTION_PRESETS'))
  assert.doesNotMatch(selectSource, /font-mono/)
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
  assert.match(home, /function H3ThemedSelect/)
  assert.match(home, /ariaLabel="Format"/)
  assert.match(home, /ariaLabel="Resolution"/)
  assert.match(home, /bg-\[#11151c\]/)
  assert.match(home, /hover:bg-white\/10/)
  assert.match(home, /bg-amber-300\/20/)
  assert.match(home, /derived from format/)
  assert.match(home, /'16:9 \(Widescreen\)': \{ 0\.4: \[864, 480\]/)
  assert.match(home, /updateSceneLocally\(\{ aspect_ratio: aspectRatio, width, height \}\)/)
  assert.match(home, /resolution_megapixels: resolutionMegapixels, width, height/)
  assert.match(home, /<H3ThemedSelect value=\{scene\.resolution_megapixels\} ariaLabel="Resolution"/)
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

test('workspace exposes deterministic local audio guidance and managed render-file actions', () => {
  const home = read('frontend/views/Home.tsx')
  const audio = read('frontend/lib/h3-audio-guidance.ts')
  const api = read('shared/electron-api-schema.ts')
  for (const label of ['Audio guidance', 'Natural ambience', 'Dialogue', 'Silent', 'No speech', 'No music', 'Custom audio instruction', 'View final prompt', 'Save Copy', 'Show in Folder', 'Open Project Folder']) assert.match(home, new RegExp(label))
  assert.match(audio, /No speech, no voices, no music, no ambient sound/)
  assert.match(audio, /Natural environmental ambience appropriate to the scene/)
  for (const endpoint of ['saveH3RenderCopy', 'revealH3Render', 'openH3ProjectFolder']) assert.match(api, new RegExp(endpoint))
  assert.doesNotMatch(audio, /https?:\/\//)
})

test('workspace exposes Stop Render and H3 Director product branding', () => {
  const home = read('frontend/views/Home.tsx')
  const window = read('electron/window.ts')
  const builder = read('electron-builder.yml')
  const firstRun = read('frontend/components/FirstRunSetup.tsx')
  for (const label of ['Stop Render', 'Cancelling', 'H3D', 'H3 Director']) assert.match(home, new RegExp(label))
  assert.match(window, /h3d-icon\.ico/)
  assert.match(builder, /resources\/h3d-icon\.ico/)
  assert.match(firstRun, /H3 Director Desktop/)
  assert.match(read('NOTICES.md'), /Lightricks|LTX/i)
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
