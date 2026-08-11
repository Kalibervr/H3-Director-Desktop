import { readAppState, writeAppState } from './app-state'
import { getBackendUrl, getAuthToken } from './python-backend'
import { ComfyRuntimeCore } from './comfyui-runtime-core'
export type { ComfyRuntimeConfig, ComfyRuntimeStatus, ComfyRuntimeState } from './comfyui-runtime-core'

const runtime = new ComfyRuntimeCore({
  getConfig: () => readAppState().comfyuiRuntime as import('./comfyui-runtime-core').ComfyRuntimeConfig,
  saveConfig: (config) => { const state = readAppState(); state.comfyuiRuntime = config; writeAppState(state) },
  getBackend: () => ({ url: getBackendUrl(), token: getAuthToken() }),
})
export const getComfyRuntimeConfig = () => runtime.getConfig()
export const saveComfyRuntimeConfig = (config: import('./comfyui-runtime-core').ComfyRuntimeConfig) => runtime.saveConfig(config)
export const getComfyRuntimeStatus = () => runtime.getStatus()
export const startComfyRuntime = () => runtime.start()
export const stopComfyRuntime = () => runtime.stop()
export const restartComfyRuntime = () => runtime.restart()
export const stopManagedComfyRuntimeOnExit = () => runtime.shutdown()
