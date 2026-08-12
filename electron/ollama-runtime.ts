import { readAppState, writeAppState } from './app-state'
import { OllamaRuntimeCore } from './ollama-runtime-core'
export type { OllamaRuntimeConfig, OllamaRuntimeStatus, OllamaRuntimeState } from './ollama-runtime-core'

const runtime = new OllamaRuntimeCore({
  getConfig: () => {
    const config = (readAppState().comfyuiRuntime ?? {}) as { ollamaAutoStart?: boolean; ollamaEndpoint?: string; ollamaModel?: string }
    return { autoStart: Boolean(config.ollamaAutoStart), endpoint: config.ollamaEndpoint ?? 'http://127.0.0.1:11434', model: config.ollamaModel }
  },
  saveConfig: config => { const state = readAppState(); state.comfyuiRuntime = { ...(state.comfyuiRuntime as object ?? {}), ollamaAutoStart: config.autoStart, ollamaEndpoint: config.endpoint, ollamaModel: config.model }; writeAppState(state) },
})
export const getOllamaRuntimeConfig = () => runtime.getConfig()
export const saveOllamaRuntimeConfig = (config: import('./ollama-runtime-core').OllamaRuntimeConfig) => runtime.saveConfig(config)
export const getOllamaRuntimeStatus = () => runtime.getStatus()
export const startOllamaRuntime = () => runtime.start()
export const stopOllamaRuntime = () => runtime.stop()
export const restartOllamaRuntime = () => runtime.restart()
export const autoStartOllamaRuntime = () => runtime.autoStart()
export const stopManagedOllamaRuntimeOnExit = () => runtime.shutdown()
