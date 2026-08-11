import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ComfyRuntimeCore } from '../electron/comfyui-runtime-core.ts'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const output = path.join(root, 'artifacts', 'verification', 'comfyui-lifecycle-node-step1.json')
const backendUrl = process.env.H3_VERIFY_BACKEND_URL
const token = process.env.H3_VERIFY_AUTH_TOKEN
if (!backendUrl || !token) throw new Error('H3_VERIFY_BACKEND_URL and H3_VERIFY_AUTH_TOKEN are required.')
const config = { rootPath: 'D:\\comfy desktop\\ComfyUI (1)\\ComfyUI', pythonPath: 'D:\\comfy desktop\\ComfyUI (1)\\ComfyUI\\.venv\\Scripts\\python.exe', port: 8188, autoLaunch: false }
const core = new ComfyRuntimeCore({ getConfig: () => config, saveConfig: () => {}, getBackend: () => ({ url: backendUrl, token }) })
const detected = await core.getStatus()
const stopped = core.stop()
const restarted = await core.restart()
const artifact = { timestamp: new Date().toISOString(), runtimePathValidation: detected.state !== 'failed', launchArgs: core.launchArgs(), externalEndpointDetection: detected.state, externalOwnership: detected.owned, stopProtection: stopped.error, restartProtection: restarted.error }
fs.mkdirSync(path.dirname(output), { recursive: true })
fs.writeFileSync(output, JSON.stringify(artifact, null, 2))
console.log(JSON.stringify(artifact))
