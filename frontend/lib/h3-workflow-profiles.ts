export type H3WorkflowProfileId = 'minimax_h3_image_to_video' | 'minimax_h3_text_to_video'

export interface H3RequiredModel {
  role: string
  expectedFilename: string | null
  destinationCategory: string | null
  source: null
  checksum: null
}

export interface H3WorkflowProfile {
  id: H3WorkflowProfileId
  label: string
  status: 'verified' | 'unavailable'
  reason?: string
  requiredModels: readonly H3RequiredModel[]
}

// Filenames and categories below are read from the verified image-to-video workflow only.
export const H3_WORKFLOW_PROFILES: readonly H3WorkflowProfile[] = [
  {
    id: 'minimax_h3_image_to_video', label: 'Image-to-Video', status: 'verified', requiredModels: [
      { role: 'video VAE', expectedFilename: 'minimax_h3_video_vae_fp16.safetensors', destinationCategory: 'vae', source: null, checksum: null },
      { role: 'audio VAE', expectedFilename: 'minimax_h3_audio_vae_fp32.safetensors', destinationCategory: 'vae', source: null, checksum: null },
      { role: 'diffusion model', expectedFilename: 'minimax_h3_fl2va_pruned_int8_convrot.safetensors', destinationCategory: 'diffusion_models', source: null, checksum: null },
      { role: 'text encoder', expectedFilename: 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', destinationCategory: 'text_encoders', source: null, checksum: null },
    ],
  },
  {
    id: 'minimax_h3_text_to_video', label: 'Text-to-Video', status: 'unavailable',
    reason: 'A verified local ComfyUI API workflow, node metadata, model manifest, source and checksum evidence are required before Text-to-Video can be enabled.',
    requiredModels: [],
  },
]

export function modelManifestStatus(profile: H3WorkflowProfile, installedFilenames: ReadonlySet<string>): { ready: boolean; missing: string[] } {
  const missing: string[] = []
  for (const model of profile.requiredModels) {
    if (model.expectedFilename && !installedFilenames.has(model.expectedFilename)) missing.push(model.expectedFilename)
  }
  return { ready: profile.status === 'verified' && missing.length === 0, missing }
}
