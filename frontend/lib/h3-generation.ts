import { backendFetch } from './backend'

export type ComfyUIStatus = 'connected' | 'unavailable' | 'incompatible'

export interface H3RuntimeStatus {
  status: ComfyUIStatus
  comfyui_version: string | null
  workflow_contract_valid: boolean
  errors: string[]
}

export interface H3RenderRequest {
  prompt: string
  input_image: string
  seed: number
  width: number
  height: number
  duration_seconds: number
  fps: number
  output_filename_prefix: string
}

export interface H3RenderResult {
  status: 'complete'
  prompt_id: string
  output_file: string
  metadata_file: string
  video: {
    codec: string
    width: number
    height: number
    fps: string
    duration_seconds: number
    frame_count: number | null
    audio_present: boolean
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json() as T | { message?: string }
  if (!response.ok) {
    const message = typeof payload === 'object' && payload && 'message' in payload
      ? payload.message
      : undefined
    throw new Error(message || 'The local H3 backend request failed.')
  }
  return payload as T
}

export async function getH3RuntimeStatus(): Promise<H3RuntimeStatus> {
  const response = await backendFetch('/api/comfyui/minimax-h3/status')
  return readJson<H3RuntimeStatus>(response)
}

export async function renderH3Scene(request: H3RenderRequest): Promise<H3RenderResult> {
  const response = await backendFetch('/api/comfyui/minimax-h3/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      base_url: 'http://127.0.0.1:8188',
      ...request,
    }),
  })
  return readJson<H3RenderResult>(response)
}
