import type { H3Scene } from './h3-projects'

export function composeH3AudioPrompt(scene: Pick<H3Scene, 'prompt' | 'audio_mode' | 'no_speech' | 'no_music' | 'custom_audio_instruction'>): string {
  const prompt = scene.prompt.trim()
  if (!prompt) return ''
  if (scene.audio_mode === 'silent') return `${prompt} No speech, no dialogue, no voices, no vocalizations, no music, no soundtrack, no background score, no singing, no musical elements, no ambient sound.`
  const parts = [prompt]
  if (scene.audio_mode === 'natural_ambience') parts.push('Natural environmental ambience appropriate to the scene.')
  if (scene.custom_audio_instruction.trim()) parts.push(scene.custom_audio_instruction.trim())
  if (scene.no_speech) parts.push('No speech, no dialogue, no voices, no vocalizations.')
  if (scene.no_music) parts.push('No music, no soundtrack, no background score, no singing, no musical elements.')
  return parts.join(' ')
}

export function h3AudioSummary(scene: Pick<H3Scene, 'audio_mode' | 'no_speech' | 'no_music'>): string {
  if (scene.audio_mode === 'silent') return 'Silent'
  const labels = [scene.audio_mode === 'natural_ambience' ? 'Natural ambience' : 'Dialogue']
  if (scene.no_speech) labels.push('No speech')
  if (scene.no_music) labels.push('No music')
  return labels.join(' · ')
}
