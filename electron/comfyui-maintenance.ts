import { spawn } from 'child_process'
import path from 'path'
import { app } from 'electron'
import { isGenerationActive } from './python-backend'
import { getComfyRuntimeConfig, getComfyRuntimeStatus, startComfyRuntime, stopComfyRuntime } from './comfyui-runtime'

type Action = 'checkUpdate' | 'reviewUpdate' | 'performUpdate' | 'listSnapshots' | 'performRollback'
let inFlight = false
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

async function waitFor(state: 'stopped' | 'ready', timeoutMs = 90_000) {
  const end=Date.now()+timeoutMs
  while(Date.now()<end){ const current=await getComfyRuntimeStatus(); if(current.state===state) return current; await wait(400) }
  throw new Error(`Managed ComfyUI did not become ${state} before timeout.`)
}
function runInternal(action: 'inspect'|'snapshot'|'update'|'restore', snapshotId?: string): Promise<any> {
  const c=getComfyRuntimeConfig(); const script=path.join(app.getAppPath(),'backend','services','h3_runtime_maintenance_cli.py'); const backup=path.join(app.getPath('userData'),'runtime-backups'); const args=[script,action,'--root',c.rootPath,'--python',c.pythonPath,'--endpoint',`http://127.0.0.1:${c.port}`,'--backup-root',backup]
  if(c.extraModelPathsConfig) args.push('--shared-model-config',c.extraModelPathsConfig); if(snapshotId) args.push('--snapshot-id',snapshotId)
  return new Promise((resolve,reject)=>{const child=spawn(c.pythonPath,args,{cwd:path.dirname(script),windowsHide:true,stdio:['ignore','pipe','pipe']});let out='',err='';child.stdout.on('data',d=>out+=String(d));child.stderr.on('data',d=>err+=String(d));child.once('error',reject);child.once('exit',code=>{if(code!==0)return reject(new Error(err.trim()||`Maintenance transaction exited ${code}.`));try{resolve(JSON.parse(out))}catch{reject(new Error('Maintenance transaction returned invalid data.'))}})})
}
export async function performComfyMaintenance(action: Action, snapshotId?: string): Promise<{status:string; detail?:any}> {
  if(inFlight) throw new Error('A ComfyUI maintenance operation is already running.')
  if(snapshotId && !/^[0-9]{8}T[0-9]{6}Z$/.test(snapshotId)) throw new Error('Invalid backup selection.')
  if(isGenerationActive()) throw new Error('Maintenance is unavailable while a generation is active.')
  const before=await getComfyRuntimeStatus(); if(!before.owned) throw new Error('Only an H3 Director-owned ComfyUI runtime can be maintained.')
  inFlight=true
  try {
    if(action==='checkUpdate'||action==='reviewUpdate'||action==='listSnapshots') return {status:'inspected',detail:await runInternal('inspect')}
    const snapshot=await runInternal('snapshot'); const stopped=stopComfyRuntime(); if(!stopped.owned && stopped.state!=='stopped') throw new Error('Managed ComfyUI could not be stopped.'); await waitFor('stopped')
    if(action==='performUpdate') await runInternal('update'); else await runInternal('restore',snapshotId)
    const ready=await startComfyRuntime(); if(ready.state!=='ready') throw new Error(`Runtime restart failed: ${ready.error??ready.state}. Rollback snapshot remains available.`)
    return {status:'complete',detail:{snapshot,ready}}
  } catch(error) { return {status:'failed',detail:{message:error instanceof Error?error.message:'Maintenance failed.',rollback_available:true}} } finally { inFlight=false }
}
