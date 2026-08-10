import { backendFetch } from './backend'

export type H3SceneStatus = 'idle' | 'queued' | 'preparing' | 'submitted' | 'rendering' | 'encoding' | 'verifying' | 'complete' | 'failed' | 'cancelled'
export type H3SceneMode = 'new_shot' | 'continue_previous' | 'same_character_new_shot'
export type H3ContinuityStrategy = 'last_valid_frame' | 'offset_from_end'
export type H3QueueState = 'waiting' | 'preparing' | 'rendering' | 'verifying' | 'complete' | 'failed' | 'skipped' | 'cancelled'

export interface H3SequenceItem {
  scene_id: string
  scene_order: number
  state: H3QueueState
  started_at: string | null
  completed_at: string | null
  render_version_id: string | null
  prompt_id: string | null
  continuity_artifact_id: string | null
  error: string | null
}

export interface H3RenderRun {
  id: string
  kind: 'from_here' | 'all'
  status: 'running' | 'complete' | 'failed' | 'cancelled'
  started_at: string
  completed_at: string | null
  ordered_scene_ids: string[]
  current_scene_id: string | null
  stop_after_current_requested: boolean
  failure_or_cancel_reason: string | null
  items: H3SequenceItem[]
}

export interface H3VideoProbe {
  codec: string
  width: number
  height: number
  fps: string
  duration_seconds: number
  frame_count: number | null
  audio_present: boolean
}

export interface H3RenderVersion {
  id: string
  number: number
  created_at: string
  root: string
  video_file: string
  metadata_file: string
  prompt: string
  input_image_reference: string
  seed: number
  width: number
  height: number
  fps: number
  duration_seconds: number
  frame_count: number | null
  prompt_id: string
  input_image_sha256: string
  workflow_sha256: string
  output_sha256: string
  ffprobe: H3VideoProbe
}

export interface H3ContinuityArtifact {
  id: string
  number: number
  created_at: string
  root: string
  image_file: string
  metadata_file: string
  image_sha256: string
  source_scene_id: string
  source_render_version_id: string
  source_video_reference: string
  source_video_sha256: string
  frame_index: number
  timestamp_seconds: number
  strategy: H3ContinuityStrategy
  offset_from_end_frames: number
  source_frame_count: number
  source_fps: string
}

export interface H3Scene {
  id: string
  storage_name: string
  order: number
  name: string
  prompt: string
  reference_image: string | null
  width: number
  height: number
  fps: number
  duration_seconds: number
  frame_count: number
  seed: number
  mode: H3SceneMode
  continuity_strategy: H3ContinuityStrategy
  continuity_offset_frames: number
  selected_continuity_artifact_id: string | null
  continuity_artifacts: H3ContinuityArtifact[]
  status: H3SceneStatus
  selected_render_version_id: string | null
  render_versions: H3RenderVersion[]
  last_error: string | null
  active_prompt_id: string | null
}

export interface H3Project {
  schema_version: 4
  id: string
  name: string
  created_at: string
  updated_at: string
  project_root: string
  settings: {
    width: number
    height: number
    fps: number
    duration_seconds: number
    frame_count: number
  }
  scenes: H3Scene[]
  selected_scene_id: string
  render_runs: H3RenderRun[]
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json() as T | { message?: string }
  if (!response.ok) {
    const message = typeof payload === 'object' && payload && 'message' in payload ? payload.message : undefined
    throw new Error(message || 'The local project request failed.')
  }
  return payload as T
}

export async function listH3Projects(): Promise<H3Project[]> {
  return readJson(await backendFetch('/api/comfyui/minimax-h3/projects'))
}

export async function createH3Project(name: string, sceneCount: number): Promise<H3Project> {
  return readJson(await backendFetch('/api/comfyui/minimax-h3/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, scene_count: sceneCount }),
  }))
}

export async function selectH3Scene(projectId: string, sceneId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/select`, { method: 'POST' }))
}

export async function addH3Scene(projectId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes`, { method: 'POST' }))
}

export async function duplicateH3Scene(projectId: string, sceneId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/duplicate`, { method: 'POST' }))
}

export async function deleteH3Scene(projectId: string, sceneId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}`, { method: 'DELETE' }))
}

export async function reorderH3Scenes(projectId: string, sceneIds: string[]): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/reorder`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scene_ids: sceneIds }),
  }))
}

export async function prepareH3Continuity(projectId: string, sceneId: string): Promise<{ project: H3Project; artifact: H3ContinuityArtifact }> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/continuity`, { method: 'POST' }))
}

export async function getH3Project(projectId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`))
}

export async function renameH3Project(projectId: string, name: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  }))
}

export async function updateH3Scene(projectId: string, sceneId: string, update: Partial<Pick<H3Scene, 'name' | 'prompt' | 'reference_image' | 'width' | 'height' | 'fps' | 'duration_seconds' | 'frame_count' | 'seed' | 'selected_render_version_id' | 'mode' | 'continuity_strategy' | 'continuity_offset_frames'>>): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(update),
  }))
}

export async function renderH3ProjectScene(projectId: string, sceneId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/render`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: 'http://127.0.0.1:8188' }),
  }))
}

export async function startH3Sequence(projectId: string, kind: 'from_here' | 'all', startSceneId?: string): Promise<H3RenderRun> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/sequences`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: 'http://127.0.0.1:8188', kind, start_scene_id: startSceneId ?? null }),
  }))
}

export async function stopH3Sequence(projectId: string, runId: string): Promise<H3RenderRun> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/sequences/${encodeURIComponent(runId)}/stop`, { method: 'POST' }))
}
