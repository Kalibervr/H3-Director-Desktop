import { backendFetch } from './backend'

export type H3SceneStatus = 'idle' | 'queued' | 'preparing' | 'submitted' | 'rendering' | 'encoding' | 'verifying' | 'complete' | 'failed' | 'cancelled'
export type H3SceneMode = 'new_shot' | 'continue_previous' | 'same_character_new_shot'
export type H3ReferenceFit = 'fill_crop' | 'fit' | 'stretch'
export type H3AudioMode = 'natural_ambience' | 'dialogue' | 'silent'
export type H3AspectRatio = '1:1 (Square)' | '16:9 (Widescreen)' | '9:16 (Portrait Widescreen)'
export type H3ResolutionMegapixels = 0.4 | 0.6 | 0.8 | 0.9 | 1
export type H3SequenceMode = 'independent_shots' | 'continuous_sequence'
export type H3WorkflowProfileId = 'minimax_h3_image_to_video' | 'minimax_h3_no_reference' | 'ltx_2_5_text_to_video' | 'ltx_2_5_image_to_video'
export type H3WorkflowMode = 'image_to_video' | 'text_to_video'
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
  current_phase: string | null
  progress_value: number | null
  progress_max: number | null
  diagnostics: string | null
}

export interface H3RenderRun {
  id: string
  kind: 'scene' | 'from_here' | 'all'
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
  render_started_at: string | null
  render_completed_at: string | null
  render_elapsed_seconds: number | null
  root: string
  video_file: string
  metadata_file: string
  prompt: string
  final_prompt: string | null
  raw_user_prompt: string | null
  improved_prompt: string | null
  native_enhanced_prompt: string | null
  final_submitted_prompt: string | null
  native_prompt_enhance: boolean | null
  audio_mode: H3AudioMode
  no_speech: boolean
  no_music: boolean
  custom_audio_instruction: string
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
  upscale_variants: H3UpscaleVariant[]
}

export interface H3UpscaleVariant {
  id: string; number: number; created_at: string; processing_elapsed_seconds: number | null; root: string; video_file: string; metadata_file: string
  backend: 'nvidia_rtx_vsr'; source_render_version_id: string; source_width: number; source_height: number
  width: number; height: number; scale: 2; fps: number; duration_seconds: number; audio_preserved: boolean
  prompt_id: string; source_video_sha256: string; output_sha256: string; ffprobe: H3VideoProbe
}

export interface H3UpscaleAvailability { available: boolean; backend: 'nvidia_rtx_vsr'; reason: string }

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
  audio_mode: H3AudioMode
  no_speech: boolean
  no_music: boolean
  custom_audio_instruction: string
  reference_image: string | null
  reference_fit: H3ReferenceFit
  ltx_prompt_enhance: boolean
  workflow_profile_id: H3WorkflowProfileId
  workflow_mode: H3WorkflowMode
  aspect_ratio: H3AspectRatio
  resolution_megapixels: H3ResolutionMegapixels
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
  current_phase: string | null
  progress_value: number | null
  progress_max: number | null
  diagnostics: string | null
}

export interface H3Project {
  schema_version: 15
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
  sequence_mode: H3SequenceMode
  workflow_profile_id: H3WorkflowProfileId
  workflow_mode: H3WorkflowMode
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

export async function createH3Project(name: string, sceneCount: number, sequenceMode: H3SequenceMode = 'independent_shots', workflowProfileId: H3WorkflowProfileId = 'minimax_h3_image_to_video', workflowMode: H3WorkflowMode = 'image_to_video'): Promise<H3Project> {
  return readJson(await backendFetch('/api/comfyui/minimax-h3/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, scene_count: sceneCount, sequence_mode: sequenceMode, workflow_profile_id: workflowProfileId, workflow_mode: workflowMode }),
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

export async function deleteH3Project(projectId: string): Promise<void> {
  const response = await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' })
  if (!response.ok) throw new Error((await response.json() as { message?: string }).message || 'The project could not be moved to H3 Director Trash.')
}

export async function reorderH3Scenes(projectId: string, sceneIds: string[]): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/reorder`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scene_ids: sceneIds }),
  }))
}

export async function prepareH3Continuity(projectId: string, sceneId: string): Promise<{ project: H3Project; artifact: H3ContinuityArtifact }> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/continuity`, { method: 'POST' }))
}

export async function continueH3FromPrevious(projectId: string, sceneId: string): Promise<{ project: H3Project; artifact: H3ContinuityArtifact }> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/continue-from-previous`, { method: 'POST' }))
}

export async function getH3Project(projectId: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`))
}

export async function updateH3Project(projectId: string, update: Partial<Pick<H3Project, 'name' | 'sequence_mode' | 'workflow_profile_id' | 'workflow_mode'>>): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(update),
  }))
}

export const renameH3Project = (projectId: string, name: string) => updateH3Project(projectId, { name })

export async function updateH3Scene(projectId: string, sceneId: string, update: Partial<Pick<H3Scene, 'name' | 'prompt' | 'audio_mode' | 'no_speech' | 'no_music' | 'custom_audio_instruction' | 'reference_image' | 'reference_fit' | 'ltx_prompt_enhance' | 'workflow_profile_id' | 'workflow_mode' | 'aspect_ratio' | 'resolution_megapixels' | 'width' | 'height' | 'fps' | 'duration_seconds' | 'frame_count' | 'seed' | 'selected_render_version_id' | 'mode' | 'continuity_strategy' | 'continuity_offset_frames'>>): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(update),
  }))
}

export async function renderH3ProjectScene(projectId: string, sceneId: string, baseUrl: string): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/render`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl }),
  }))
}

export async function startH3Sequence(projectId: string, kind: 'scene' | 'from_here' | 'all', startSceneId: string | undefined, baseUrl: string): Promise<H3RenderRun> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/sequences`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl, kind, start_scene_id: startSceneId ?? null }),
  }))
}

export async function stopH3Sequence(projectId: string, runId: string): Promise<H3RenderRun> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/sequences/${encodeURIComponent(runId)}/stop`, { method: 'POST' }))
}

export async function getH3UpscaleAvailability(baseUrl: string): Promise<H3UpscaleAvailability> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/upscale/availability?base_url=${encodeURIComponent(baseUrl)}`))
}

export async function installH3WorkflowProfile(folder: string): Promise<{ profile_id: string; version: string; installed_path: string }> {
  return readJson(await backendFetch('/api/comfyui/minimax-h3/workflow-profiles/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder }) }))
}

export type H3Ltx25AssetState = 'found' | 'missing' | 'duplicate' | 'unknown' | 'wrong_filename' | 'wrong_destination'
export interface H3Ltx25ModelAssetStatus { filename: string; destination_category: string | null; required: boolean; state: H3Ltx25AssetState; file_size_bytes: number | null; message: string }
export interface H3Ltx25ModelImportResult { model_root: string | null; assets: H3Ltx25ModelAssetStatus[]; imported_count: number; checksum_verified: false }
export async function importH3Ltx25Models(filePaths: string[], sharedModelPathsConfig: string): Promise<H3Ltx25ModelImportResult> {
  return readJson(await backendFetch('/api/comfyui/minimax-h3/ltx-2-5/models/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_paths: filePaths, shared_model_paths_config: sharedModelPathsConfig }) }))
}

export async function upscaleH3Render(projectId: string, sceneId: string, versionId: string, config: { baseUrl: string; inputDirectory: string; outputDirectory: string }): Promise<H3Project> {
  return readJson(await backendFetch(`/api/comfyui/minimax-h3/projects/${encodeURIComponent(projectId)}/scenes/${encodeURIComponent(sceneId)}/renders/${encodeURIComponent(versionId)}/upscale`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: config.baseUrl, input_directory: config.inputDirectory, output_directory: config.outputDirectory, scale: 2 }),
  }))
}
