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
  outputResolution: null
  settings: Record<string, never>
}

// The installed KJ node exposes an RTX VSR image operation, but the local runtime
// has no nvidia-vfx/nvvfx dependency and no verified video workflow/output contract.
export const RTX_VSR_SETUP_REQUIRED: H3UpscaleAvailability = {
  available: false,
  backend: 'nvidia_rtx_vsr',
  reason: 'RTX Video Super Resolution setup required: install the local NVIDIA nvidia-vfx runtime and provide a verified ComfyUI video upscale workflow before this action can run.',
}

export function createUpscaleVariantPlan(source: H3RenderVersion): H3UpscaleVariantPlan {
  return {
    sourceRenderVersionId: source.id,
    backend: 'nvidia_rtx_vsr',
    sourceResolution: `${source.width}x${source.height}`,
    outputResolution: null,
    settings: {},
  }
}
