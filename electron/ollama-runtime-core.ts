import { ChildProcess, execFileSync, spawn } from 'child_process'
import fs from 'fs'
import path from 'path'

export type OllamaRuntimeState = 'not_installed' | 'starting' | 'ready' | 'not_running' | 'failed'
export interface OllamaRuntimeConfig { autoStart: boolean; endpoint: string; model?: string }
export interface OllamaRuntimeStatus { state: OllamaRuntimeState; owned: boolean; pid: number | null; endpoint: string; executable: string | null; error: string | null; diagnostics: string[] }
export interface OllamaRuntimeDependencies { getConfig: () => OllamaRuntimeConfig; saveConfig: (config: OllamaRuntimeConfig) => void; spawn?: typeof spawn; existsSync?: typeof fs.existsSync; execFileSync?: typeof execFileSync; fetch?: typeof fetch; env?: NodeJS.ProcessEnv }

const defaults: OllamaRuntimeConfig = { autoStart: false, endpoint: 'http://127.0.0.1:11434' }
const loopbackEndpoint = 'http://127.0.0.1:11434'

export class OllamaRuntimeCore {
  private managed: ChildProcess | null = null
  private status: OllamaRuntimeStatus = { state: 'not_running', owned: false, pid: null, endpoint: loopbackEndpoint, executable: null, error: null, diagnostics: [] }
  constructor(private readonly deps: OllamaRuntimeDependencies) {}
  private config() { return { ...defaults, ...this.deps.getConfig(), endpoint: loopbackEndpoint } }
  private set(next: Partial<OllamaRuntimeStatus>) { this.status = { ...this.status, ...next } }
  private exists(value: string) { return (this.deps.existsSync ?? fs.existsSync)(value) }
  private findExecutable(): string | null {
    const candidates = [
      path.join(process.env.LOCALAPPDATA ?? '', 'Programs', 'Ollama', 'ollama.exe'),
      path.join(process.env.ProgramFiles ?? '', 'Ollama', 'ollama.exe'),
    ].filter(Boolean)
    for (const candidate of candidates) if (this.exists(candidate)) return candidate
    try {
      const where = (this.deps.execFileSync ?? execFileSync)('where.exe', ['ollama.exe'], { encoding: 'utf8', windowsHide: true }).split(/\r?\n/).find(Boolean)
      return where && this.exists(where) ? where : null
    } catch { return null }
  }
  private async reachable(): Promise<boolean> {
    try {
      const response = await (this.deps.fetch ?? fetch)(`${loopbackEndpoint}/api/tags`, { signal: AbortSignal.timeout(2500) })
      return response.ok
    } catch { return false }
  }
  getConfig() { return this.config() }
  saveConfig(config: OllamaRuntimeConfig) { const next = { ...config, endpoint: loopbackEndpoint }; this.deps.saveConfig(next); return next }
  async getStatus(): Promise<OllamaRuntimeStatus> {
    const executable = this.findExecutable()
    if (await this.reachable()) {
      const owned = this.managed !== null
      this.set({ state: 'ready', owned, pid: owned ? this.managed?.pid ?? null : null, endpoint: loopbackEndpoint, executable, error: null, diagnostics: owned ? ['H3 Director-managed local Ollama.'] : ['External local Ollama.'] })
      return this.status
    }
    if (!executable) { this.set({ state: 'not_installed', owned: false, pid: null, endpoint: loopbackEndpoint, executable: null, error: 'Local Ollama is not installed.', diagnostics: [] }); return this.status }
    if (this.managed) { this.set({ state: 'failed', owned: true, pid: this.managed.pid ?? null, endpoint: loopbackEndpoint, executable, error: 'H3-managed Ollama is not responding.', diagnostics: [] }); return this.status }
    this.set({ state: 'not_running', owned: false, pid: null, endpoint: loopbackEndpoint, executable, error: null, diagnostics: ['Local Ollama is installed but not running.'] })
    return this.status
  }
  async start(): Promise<OllamaRuntimeStatus> {
    const current = await this.getStatus()
    if (current.state === 'ready' || current.state === 'not_installed') return current
    const executable = current.executable
    if (!executable) return current
    const child = (this.deps.spawn ?? spawn)(executable, ['serve'], { cwd: path.dirname(executable), env: { ...(this.deps.env ?? process.env), OLLAMA_HOST: '127.0.0.1:11434' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    this.managed = child
    const diagnostics: string[] = []
    const tail = (text: string) => { diagnostics.push(text); if (diagnostics.join('').length > 3000) diagnostics.splice(0, diagnostics.length - 12) }
    child.stdout?.on('data', value => tail(String(value)))
    child.stderr?.on('data', value => tail(String(value)))
    child.once('exit', (code, signal) => {
      const expected = this.status.state === 'not_running'
      if (this.managed === child) this.managed = null
      this.set({ state: expected ? 'not_running' : 'failed', owned: false, pid: null, error: expected ? null : `Local Ollama exited (${code ?? 'unknown'}${signal ? `, ${signal}` : ''}).`, diagnostics: diagnostics.join('').split(/\r?\n/).filter(Boolean).slice(-8) })
    })
    this.set({ state: 'starting', owned: true, pid: child.pid ?? null, endpoint: loopbackEndpoint, executable, error: null, diagnostics: ['Launching local Ollama on 127.0.0.1:11434.'] })
    const deadline = Date.now() + 30000
    while (Date.now() < deadline) {
      if (this.managed !== child) return this.status
      if (await this.reachable()) { this.set({ state: 'ready', owned: true, pid: child.pid ?? null, endpoint: loopbackEndpoint, executable, error: null, diagnostics: ['H3 Director-managed local Ollama.'] }); return this.status }
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    this.stop()
    this.set({ state: 'failed', owned: false, pid: null, error: 'Local Ollama did not become ready before the 30 second timeout.' })
    return this.status
  }
  stop(): OllamaRuntimeStatus { if (!this.managed) return { ...this.status, error: 'Only an H3 Director-managed Ollama process can be stopped.' }; this.set({ state: 'not_running' }); this.managed.kill(); return this.status }
  async restart(): Promise<OllamaRuntimeStatus> { if (!this.managed) return { ...this.status, error: 'Only an H3 Director-managed Ollama process can be restarted.' }; this.stop(); await new Promise(resolve => setTimeout(resolve, 500)); return this.start() }
  async autoStart(): Promise<OllamaRuntimeStatus> { return this.config().autoStart ? this.start() : this.getStatus() }
  shutdown() { if (this.managed) { this.set({ state: 'not_running' }); this.managed.kill() } }
}
