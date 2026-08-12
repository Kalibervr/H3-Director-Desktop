import type { H3AspectRatio, H3ResolutionMegapixels, H3WorkflowMode, H3WorkflowProfileId } from './h3-projects'

export interface H3ModelManifestEntry { id: string; displayName: string; role: 'diffusion_model' | 'text_encoder' | 'vae' | 'audio_encoder' | 'lora' | 'other'; expectedFilename: string | null; destinationCategory: string | null; required: boolean; source: null; downloadUrl: null; sha256: null }
export interface H3WorkflowModeProfile { id: H3WorkflowMode; label: string; verified: boolean; capabilities: { imageToVideo: boolean; textToVideo: boolean; continuePrevious: boolean; multiShot: boolean; audio: boolean; referenceImage: boolean }; aspectRatios: readonly H3AspectRatio[]; resolutionMegapixels: readonly H3ResolutionMegapixels[]; fpsPresets: readonly number[]; seed: boolean; referenceFit: boolean; audioGuidance: boolean; postProcessing: readonly string[] }
export interface H3WorkflowProfile { id: H3WorkflowProfileId; label: string; displayName: string; providerFamily: string; version: string; profileSchemaVersion: 1; status: 'verified' | 'missing_models' | 'missing_nodes' | 'incompatible' | 'not_verified'; reason?: string; modes: readonly H3WorkflowModeProfile[]; requiredModels: readonly H3ModelManifestEntry[]; apiWorkflow: string; requiredNodes: readonly string[] }

export const H3_WORKFLOW_PROFILES: readonly H3WorkflowProfile[] = [{
  id: 'minimax_h3_image_to_video', label: 'Image-to-Video', displayName: 'MiniMax H3', providerFamily: 'MiniMax H3', version: '1', profileSchemaVersion: 1, status: 'verified', apiWorkflow: 'workflows/minimax_h3_single_scene_api.json',
  requiredNodes: ['CLIPLoader', 'LoadImage', 'ResolutionSelector', 'SaveVideo'],
  modes: [{ id: 'image_to_video', label: 'Image to Video', verified: true, capabilities: { imageToVideo: true, textToVideo: false, continuePrevious: true, multiShot: false, audio: true, referenceImage: true }, aspectRatios: ['1:1 (Square)', '16:9 (Widescreen)', '9:16 (Portrait Widescreen)'], resolutionMegapixels: [0.4, 0.6, 0.8, 1], fpsPresets: [24], seed: true, referenceFit: true, audioGuidance: true, postProcessing: ['nvidia_rtx_vsr'] }],
  requiredModels: [
    { id: 'minimax-h3-video-vae', displayName: 'Video VAE', role: 'vae', expectedFilename: 'minimax_h3_video_vae_fp16.safetensors', destinationCategory: 'vae', required: true, source: null, downloadUrl: null, sha256: null },
    { id: 'minimax-h3-audio-vae', displayName: 'Audio VAE', role: 'vae', expectedFilename: 'minimax_h3_audio_vae_fp32.safetensors', destinationCategory: 'vae', required: true, source: null, downloadUrl: null, sha256: null },
    { id: 'minimax-h3-diffusion', displayName: 'Diffusion model', role: 'diffusion_model', expectedFilename: 'minimax_h3_fl2va_pruned_int8_convrot.safetensors', destinationCategory: 'diffusion_models', required: true, source: null, downloadUrl: null, sha256: null },
    { id: 'minimax-h3-text-encoder', displayName: 'Text encoder', role: 'text_encoder', expectedFilename: 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors', destinationCategory: 'text_encoders', required: true, source: null, downloadUrl: null, sha256: null },
  ],
}]

export const workflowProfileRegistry = { list: () => H3_WORKFLOW_PROFILES, get: (id: H3WorkflowProfileId) => H3_WORKFLOW_PROFILES.find(profile => profile.id === id) ?? null, mode: (profileId: H3WorkflowProfileId, mode: H3WorkflowMode) => H3_WORKFLOW_PROFILES.find(profile => profile.id === profileId)?.modes.find(item => item.id === mode) ?? null }
export function modelManifestStatus(profile: H3WorkflowProfile, installedFilenames: ReadonlySet<string>): { ready: boolean; missing: string[] } { const missing = profile.requiredModels.filter(model => model.required && model.expectedFilename && !installedFilenames.has(model.expectedFilename)).map(model => model.expectedFilename!); return { ready: profile.status === 'verified' && missing.length === 0, missing } }
