import type { H3RenderVersion } from './h3-projects'

export interface H3UpscaleAvailability {
  available: boolean
  backend: 'nvidia_rtx_vsr'
  reason: string
}

export interface H3UpscaleVariantPlan {
  sourceRenderVersionId: string
  backend: 'nvidia_rtx_vsr'
  sourceResolution: `${number}x${number}`
  outputResolution: `${number}x${number}`
  settings: { scale: 2 }
}

export const RTX_VSR_SETUP_REQUIRED: H3UpscaleAvailability = {
  available: false,
  backend: 'nvidia_rtx_vsr',
  reason: 'RTX Video Super Resolution is unavailable in the configured local ComfyUI runtime.',
}

export function createUpscaleVariantPlan(source: H3RenderVersion): H3UpscaleVariantPlan {
  return {
    sourceRenderVersionId: source.id,
    backend: 'nvidia_rtx_vsr',
    sourceResolution: `${source.width}x${source.height}`,
    outputResolution: `${source.width * 2}x${source.height * 2}`,
    settings: { scale: 2 },
  }
}
