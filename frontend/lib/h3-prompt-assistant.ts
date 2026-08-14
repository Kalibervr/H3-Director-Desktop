import { backendFetch } from './backend'
import type { H3AspectRatio, H3AudioMode, H3SceneMode, H3SequenceMode } from './h3-projects'

export interface H3PromptAssistantContext {
  rawPrompt: string; sceneNumber: number; sceneName: string; projectName: string; sequenceMode: H3SequenceMode
  previousSceneNumber?: number; previousSceneName?: string; previousScenePrompt?: string; previousFinalPrompt?: string
  mode: H3SceneMode; continuitySourceVersionId?: string; aspectRatio: H3AspectRatio; width: number; height: number
  durationSeconds: number; fps: number; audioMode: H3AudioMode; noSpeech: boolean; noMusic: boolean; customAudioInstruction: string
  continuityFramePath?: string; referenceImagePath?: string
  requestId?: string
}
export interface H3PromptAssistantResult { provider: 'deterministic_local' | 'ollama'; available: boolean; suggestion: string | null; message: string; model?: string; visionContext: 'used' | 'not_available' }
export interface H3PromptAssistantProvider { improve(context: H3PromptAssistantContext): Promise<H3PromptAssistantResult> }
export interface H3OllamaStatus { status: 'ready' | 'not_running' | 'model_not_installed' | 'unavailable'; endpoint: string; models: Array<{ name: string; vision_capable: boolean }>; selected_model: string | null; selected_model_available: boolean; vision_capable: boolean; model_state: 'cold' | 'warming' | 'warm' | 'unknown'; model_vram_bytes: number | null; message: string }

async function readJson<T>(response: Response): Promise<T> { const body = await response.json() as T | { message?: string }; if (!response.ok) throw new Error(typeof body === 'object' && body && 'message' in body ? body.message || 'Local Ollama request failed.' : 'Local Ollama request failed.'); return body as T }
export const getOllamaStatus = async (endpoint: string, model?: string) => readJson<H3OllamaStatus>(await backendFetch(`/api/comfyui/minimax-h3/prompt-assistant/status?endpoint=${encodeURIComponent(endpoint)}${model ? `&selected_model=${encodeURIComponent(model)}` : ''}`))
export const warmH3PromptAssistant = async (endpoint: string, model: string) => readJson<H3OllamaStatus>(await backendFetch('/api/comfyui/minimax-h3/prompt-assistant/warm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint, model }) }))
export const releaseH3PromptAssistant = async (endpoint: string, model: string) => readJson<H3OllamaStatus>(await backendFetch('/api/comfyui/minimax-h3/prompt-assistant/release', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint, model }) }))

/** Local-only fallback. It never calls a network service or overwrites the user prompt. */
export class DeterministicH3PromptAssistant implements H3PromptAssistantProvider {
  async improve(context: H3PromptAssistantContext): Promise<H3PromptAssistantResult> {
    const rawPrompt = context.rawPrompt.trim()
    if (!rawPrompt) return { provider: 'deterministic_local', available: false, suggestion: null, message: 'Write a scene prompt before requesting a suggestion.', visionContext: 'not_available' }
    const continuity = context.mode === 'continue_previous' ? ` Continue directly from the supplied final-frame reference${context.continuitySourceVersionId ? ` from ${context.continuitySourceVersionId}` : ''}; preserve the established subject, environment, lighting, and visual continuity.` : ''
    const audio = context.audioMode === 'silent' ? ' No speech, no dialogue, no voices, no vocalizations. No music, no soundtrack, no background score, no singing, no musical elements.' : ` Keep audio appropriate to the scene${context.noSpeech ? ', with no speech, dialogue, voices, or vocalizations' : ''}${context.noMusic ? ', with no music, soundtrack, background score, singing, or musical elements' : ''}.`
    return { provider: 'deterministic_local', available: true, suggestion: `${rawPrompt}${continuity} Describe deliberate camera motion, subject movement, and the environment for this ${context.width}×${context.height}, ${context.durationSeconds}s shot.${audio}`, message: 'Basic local suggestion — Local Ollama is unavailable.', visionContext: 'not_available' }
  }
}

export class OllamaH3PromptAssistant implements H3PromptAssistantProvider {
  constructor(private readonly endpoint: string, private readonly model: string) {}
  async improve(context: H3PromptAssistantContext): Promise<H3PromptAssistantResult> {
    const response = await readJson<{ suggestion: string; model: string; vision_context: 'used' | 'not_available'; message: string }>(await backendFetch('/api/comfyui/minimax-h3/prompt-assistant/improve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: this.endpoint, model: this.model, raw_prompt: context.rawPrompt, scene_number: context.sceneNumber, scene_name: context.sceneName, project_name: context.projectName, sequence_mode: context.sequenceMode, scene_mode: context.mode, continuity_source_version_id: context.continuitySourceVersionId, aspect_ratio: context.aspectRatio, width: context.width, height: context.height, duration_seconds: context.durationSeconds, fps: context.fps, previous_scene_number: context.previousSceneNumber, previous_scene_name: context.previousSceneName, previous_scene_prompt: context.previousScenePrompt, previous_final_prompt: context.previousFinalPrompt, continuity_frame_path: context.continuityFramePath, reference_image_path: context.referenceImagePath, audio_mode: context.audioMode, no_speech: context.noSpeech, no_music: context.noMusic, custom_audio_instruction: context.customAudioInstruction, request_id: context.requestId }) }))
    return { provider: 'ollama', available: true, suggestion: response.suggestion, model: response.model, message: response.message, visionContext: response.vision_context }
  }
}
export const localPromptAssistant: H3PromptAssistantProvider = new DeterministicH3PromptAssistant()
