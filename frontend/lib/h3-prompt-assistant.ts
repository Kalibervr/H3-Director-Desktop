import type { H3AspectRatio, H3AudioMode, H3SceneMode } from './h3-projects'

export interface H3PromptAssistantContext {
  rawPrompt: string
  previousScenePrompt?: string
  mode: H3SceneMode
  continuitySourceVersionId?: string
  aspectRatio: H3AspectRatio
  width: number
  height: number
  durationSeconds: number
  audioMode: H3AudioMode
  noSpeech: boolean
  noMusic: boolean
  continuityFramePath?: string
}

export interface H3PromptAssistantResult {
  provider: 'deterministic_local' | 'ollama'
  available: boolean
  suggestion: string | null
  message: string
}

export interface H3PromptAssistantProvider {
  improve(context: H3PromptAssistantContext): Promise<H3PromptAssistantResult>
}

/** Local-only fallback. It never calls a network service or overwrites the user prompt. */
export class DeterministicH3PromptAssistant implements H3PromptAssistantProvider {
  async improve(context: H3PromptAssistantContext): Promise<H3PromptAssistantResult> {
    const rawPrompt = context.rawPrompt.trim()
    if (!rawPrompt) return { provider: 'deterministic_local', available: false, suggestion: null, message: 'Write a scene prompt before requesting a suggestion.' }
    const continuity = context.mode === 'continue_previous'
      ? ` Continue directly from the supplied final-frame reference${context.continuitySourceVersionId ? ` from ${context.continuitySourceVersionId}` : ''}; preserve the established subject, environment, lighting, and visual continuity.`
      : ''
    const audio = context.audioMode === 'silent'
      ? ' Keep the requested audio silent.'
      : ` Keep audio appropriate to the scene${context.noSpeech ? ', with no speech' : ''}${context.noMusic ? ', with no music' : ''}.`
    return {
      provider: 'deterministic_local',
      available: true,
      suggestion: `${rawPrompt}${continuity} Describe deliberate camera motion, subject movement, and the environment for this ${context.width}×${context.height}, ${context.durationSeconds}s shot.${audio}`,
      message: 'Ollama is not configured. This is a deterministic local template suggestion.',
    }
  }
}

export const localPromptAssistant: H3PromptAssistantProvider = new DeterministicH3PromptAssistant()
