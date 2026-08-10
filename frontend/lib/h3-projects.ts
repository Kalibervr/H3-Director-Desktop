import { backendFetch } from './backend'

export type H3SceneStatus = 'idle' | 'queued' | 'preparing' | 'submitted' | 'rendering' | 'encoding' | 'verifying' | 'complete' | 'failed' | 'cancelled'

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
  status: H3SceneStatus
  selected_render_version_id: string | null
  render_versions: H3RenderVersion[]
  last_error: string | null
  active_prompt_id: string | null
}

export interface H3Project {
  schema_version: 2
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

export async function getH3Project(projectId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`))
}

export async function renameH3Project(projectId: string, name: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  }))
}

export async function updateH3Scene(projectId: string, sceneId: string, update: Partial<Pick<H3Scene, 'name' | 'prompt' | 'reference_image' | 'width' | 'height' | 'fps' | 'duration_seconds' | 'frame_count' | 'seed' | 'selected_render_version_id'>>): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(update),
  }))
}

export async function renderH3ProjectScene(projectId: string, sceneId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/render`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: 'http://127.0.0.1:8188' }),
  }))
}
