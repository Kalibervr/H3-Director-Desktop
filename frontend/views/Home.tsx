import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Aperture, Clapperboard, Film, Folder, ImagePlus,
  Loader2, Plus, Radio, RotateCcw, Sparkles,
} from 'lucide-react'
import { pathToFileUrl } from '../lib/file-url'
import { getH3RuntimeStatus, type ComfyUIStatus } from '../lib/h3-generation'
import {
  createH3Project,
  getH3Project,
  listH3Projects,
  renameH3Project,
  renderH3ProjectScene,
  updateH3Scene,
  type H3Project,
  type H3Scene,
  type H3SceneStatus,
} from '../lib/h3-projects'

const ACTIVE_STATUSES: H3SceneStatus[] = ['queued', 'preparing', 'submitted', 'rendering', 'encoding', 'verifying']
const STATUS_LABELS: Record<H3SceneStatus, string> = {
  idle: 'Ready', queued: 'Queued', preparing: 'Preparing input', submitted: 'Submitted',
  rendering: 'Rendering in ComfyUI', encoding: 'Encoding', verifying: 'Verifying with ffprobe',
  complete: 'Complete', failed: 'Failed', cancelled: 'Cancelled',
}

function StatusPill({ status }: { status: ComfyUIStatus }) {
  const style = status === 'connected'
    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
    : status === 'incompatible'
      ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
      : 'border-red-400/30 bg-red-400/10 text-red-300'
  return <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${style}`}>
    <span className="h-2 w-2 rounded-full bg-current" /> ComfyUI {status}
  </div>
}

function selectedScene(project: H3Project | null): H3Scene | null {
  if (!project) return null
  return project.scenes.find(scene => scene.id === project.selected_scene_id) ?? project.scenes[0] ?? null
}

export function Home() {
  const [projects, setProjects] = useState<H3Project[]>([])
  const [project, setProject] = useState<H3Project | null>(null)
  const [newProjectName, setNewProjectName] = useState('')
  const [showNewProject, setShowNewProject] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<ComfyUIStatus>('unavailable')
  const [runtimeVersion, setRuntimeVersion] = useState<string | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [rendering, setRendering] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const saveTimer = useRef<number | null>(null)
  const scene = selectedScene(project)

  const replaceProject = (next: H3Project) => {
    setProject(next)
    setProjects(current => [next, ...current.filter(item => item.id !== next.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
  }

  useEffect(() => {
    void listH3Projects().then(items => {
      setProjects(items)
      setProject(items[0] ?? null)
    }).catch(error => setWorkspaceError(error instanceof Error ? error.message : 'Projects could not be loaded.'))
  }, [])

  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const status = await getH3RuntimeStatus()
        if (!active) return
        setRuntimeStatus(status.status)
        setRuntimeVersion(status.comfyui_version)
        setRuntimeError(status.errors[0] ?? null)
      } catch {
        if (active) {
          setRuntimeStatus('unavailable')
          setRuntimeVersion(null)
          setRuntimeError('The local ComfyUI runtime could not be reached.')
        }
      }
    }
    void refresh()
    const interval = window.setInterval(() => void refresh(), 10_000)
    return () => { active = false; window.clearInterval(interval) }
  }, [])

  useEffect(() => {
    if (!project || !scene || !ACTIVE_STATUSES.includes(scene.status)) return
    const interval = window.setInterval(() => {
      void getH3Project(project.id).then(replaceProject).catch(() => undefined)
    }, 1_000)
    return () => window.clearInterval(interval)
  }, [project?.id, scene?.id, scene?.status])

  useEffect(() => () => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
  }, [])

  const updateSceneLocally = (changes: Partial<H3Scene>) => {
    if (!project || !scene) return
    setProject({ ...project, scenes: project.scenes.map(item => item.id === scene.id ? { ...item, ...changes } : item) })
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
    setSaveState('saving')
    saveTimer.current = window.setTimeout(() => {
      void updateH3Scene(project.id, scene.id, changes).then(next => {
        replaceProject(next)
        setSaveState('saved')
      }).catch(() => setSaveState('error'))
    }, 500)
  }

  const chooseReferenceImage = async () => {
    if (!project || !scene) return
    const paths = await window.electronAPI.showOpenFileDialog({
      title: 'Choose a reference image',
      filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }],
      properties: ['openFile'],
    })
    if (!paths?.[0]) return
    setSaveState('saving')
    try {
      replaceProject(await updateH3Scene(project.id, scene.id, { reference_image: paths[0] }))
      setSaveState('saved')
      setWorkspaceError(null)
    } catch (error) {
      setSaveState('error')
      setWorkspaceError(error instanceof Error ? error.message : 'The reference image could not be saved.')
    }
  }

  const createProject = async () => {
    if (!newProjectName.trim()) return
    try {
      const next = await createH3Project(newProjectName.trim())
      replaceProject(next)
      setNewProjectName('')
      setShowNewProject(false)
      setWorkspaceError(null)
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The project could not be created.')
    }
  }

  const renderScene = async () => {
    if (!project || !scene || !scene.prompt.trim() || !scene.reference_image || runtimeStatus !== 'connected') return
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
    setRendering(true)
    setWorkspaceError(null)
    try {
      const saved = await updateH3Scene(project.id, scene.id, {
        prompt: scene.prompt, reference_image: scene.reference_image, seed: scene.seed,
        width: scene.width, height: scene.height, fps: scene.fps,
        duration_seconds: scene.duration_seconds, frame_count: scene.frame_count,
      })
      replaceProject({ ...saved, scenes: saved.scenes.map(item => item.id === scene.id ? { ...item, status: 'queued' } : item) })
      replaceProject(await renderH3ProjectScene(project.id, scene.id))
      setSaveState('saved')
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The local render failed.')
      try { replaceProject(await getH3Project(project.id)) } catch { /* retain recoverable local state */ }
    } finally {
      setRendering(false)
    }
  }

  const activeVersion = useMemo(() => scene?.render_versions.find(
    version => version.id === scene.selected_render_version_id,
  ) ?? null, [scene])
  const previewUrl = activeVersion
    ? pathToFileUrl(activeVersion.video_file)
    : scene?.reference_image ? pathToFileUrl(scene.reference_image) : null
  const canRender = Boolean(project && scene?.prompt.trim() && scene.reference_image && runtimeStatus === 'connected' && !rendering)
  const phaseActive = scene ? ACTIVE_STATUSES.includes(scene.status) : false

  return <div className="h-screen overflow-hidden bg-[#07090d] text-zinc-100">
    <div className="grid h-full grid-cols-[250px_minmax(0,1fr)_360px] grid-rows-[minmax(0,1fr)_150px]">
      <aside className="row-span-2 flex min-h-0 flex-col border-r border-white/10 bg-[#0a0d12]">
        <div className="border-b border-white/10 px-5 py-5"><div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 to-orange-600 text-black"><Aperture className="h-5 w-5" /></div>
          <div><div className="font-semibold tracking-wide">H3 Director</div><div className="text-[10px] uppercase tracking-[0.24em] text-zinc-500">Desktop Studio</div></div>
        </div></div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-5">
          <div className="mb-3 flex items-center justify-between px-2"><span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Recent Projects</span><button onClick={() => setShowNewProject(true)} aria-label="New Project"><Plus className="h-4 w-4" /></button></div>
          <div className="space-y-1">{projects.map(item => <button key={item.id} onClick={() => void getH3Project(item.id).then(replaceProject)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm ${project?.id === item.id ? 'bg-amber-300/10 text-amber-200' : 'text-zinc-400 hover:bg-white/5'}`}><Folder className="h-4 w-4" /><span className="truncate">{item.name}</span></button>)}</div>
          {!projects.length && <p className="px-3 py-4 text-xs leading-5 text-zinc-600">Create a disk-backed local project to begin.</p>}
          <div className="mt-8 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Assets</div>
          <button onClick={() => void chooseReferenceImage()} disabled={!scene} className="mt-3 flex w-full items-center gap-3 rounded-lg border border-dashed border-white/10 px-3 py-3 text-left text-xs text-zinc-500 disabled:opacity-30"><ImagePlus className="h-4 w-4" />{scene?.reference_image ? 'Replace reference' : 'Add reference image'}</button>
          {scene?.reference_image && <div className="mt-2 truncate px-3 text-[11px] text-zinc-600">{scene.reference_image.split(/[\\/]/).pop()}</div>}
        </div>
        <div className="border-t border-white/10 p-4"><button onClick={() => setShowNewProject(true)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-100 px-4 py-3 text-sm font-semibold text-zinc-950"><Plus className="h-4 w-4" /> New Project</button></div>
      </aside>

      <main className="min-h-0 min-w-0 bg-[radial-gradient(circle_at_50%_20%,rgba(245,158,11,.07),transparent_36%)] p-6">
        <header className="mb-5 flex items-center justify-between"><div>
          <div className="text-xs uppercase tracking-[0.2em] text-zinc-600">Current production · {saveState}</div>
          <input value={project?.name ?? ''} disabled={!project} onChange={event => project && setProject({ ...project, name: event.target.value })} onBlur={() => project?.name.trim() && void renameH3Project(project.id, project.name).then(replaceProject).catch(() => setSaveState('error'))} className="mt-1 w-96 bg-transparent text-xl font-semibold outline-none disabled:opacity-50" placeholder="No project selected" />
        </div><div className="text-right"><StatusPill status={runtimeStatus} />{runtimeVersion && <div className="mt-1 text-[10px] text-zinc-600">ComfyUI {runtimeVersion}</div>}</div></header>
        <section className="relative flex h-[calc(100%-64px)] min-h-[360px] items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
          {previewUrl ? activeVersion ? <video key={previewUrl} src={previewUrl} controls autoPlay loop className="h-full w-full object-contain" /> : <img src={previewUrl} alt="Selected scene reference" className="h-full w-full object-contain opacity-90" /> : <div className="max-w-sm text-center"><Film className="mx-auto h-10 w-10 text-zinc-700" /><h2 className="mt-5 text-lg text-zinc-300">Your selected render will appear here</h2><p className="mt-2 text-sm text-zinc-600">Create a project and save the scene reference to begin.</p></div>}
          <div className="absolute left-4 top-4 rounded-full border border-white/10 bg-black/60 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-zinc-400">Scene preview</div>
          {scene && <div className={`absolute bottom-4 right-4 rounded-full px-3 py-1.5 text-xs font-semibold ${scene.status === 'failed' ? 'bg-red-400/90 text-red-950' : scene.status === 'complete' ? 'bg-emerald-400/90 text-emerald-950' : 'bg-amber-300/90 text-amber-950'}`}>{STATUS_LABELS[scene.status]}</div>}
        </section>
      </main>

      <aside className="row-span-2 min-h-0 overflow-y-auto border-l border-white/10 bg-[#0b0e13] p-5">
        <div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-amber-300" /> Director controls</div>{scene && <span className="text-[10px] uppercase tracking-wider text-zinc-600">{STATUS_LABELS[scene.status]}</span>}</div>
        <label className="mt-6 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene prompt<textarea value={scene?.prompt ?? ''} disabled={!scene} onChange={event => updateSceneLocally({ prompt: event.target.value })} className="mt-2 h-36 w-full resize-none rounded-xl border border-white/10 bg-black/30 p-3 text-sm normal-case leading-6 tracking-normal outline-none focus:border-amber-300/40" placeholder="Describe the shot, movement, lighting, mood and audio…" /></label>
        <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Reference image<button onClick={() => void chooseReferenceImage()} disabled={!scene} className="mt-2 flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.025] px-3 py-3 text-sm normal-case tracking-normal text-zinc-400"><span className="truncate">{scene?.reference_image?.split(/[\\/]/).pop() ?? 'Choose image'}</span><ImagePlus className="h-4 w-4" /></button></label>
        <div className="mt-6 grid grid-cols-2 gap-3">{scene && [
          ['Width', scene.width], ['Height', scene.height], ['FPS', scene.fps], ['Duration', `${scene.duration_seconds}s`], ['Frames', scene.frame_count],
        ].map(([label, value]) => <div key={label} className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">{label}</div><div className="mt-1 font-mono text-sm text-zinc-300">{value}</div></div>)}
          <label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Seed</div><input type="number" disabled={!scene} value={scene?.seed ?? 0} onChange={event => updateSceneLocally({ seed: Number(event.target.value) })} className="mt-1 w-full bg-transparent font-mono text-sm text-zinc-300 outline-none" /></label>
        </div>
        {!!scene?.render_versions.length && <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Render version<select value={scene.selected_render_version_id ?? ''} onChange={event => void updateH3Scene(project!.id, scene.id, { selected_render_version_id: event.target.value }).then(replaceProject)} className="mt-2 w-full rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm normal-case tracking-normal text-zinc-300">{scene.render_versions.map(version => <option key={version.id} value={version.id}>v{String(version.number).padStart(3, '0')} · {new Date(version.created_at).toLocaleString()}</option>)}</select></label>}
        {runtimeError && runtimeStatus !== 'connected' && <p className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/70">{runtimeError}</p>}
        {(workspaceError || scene?.last_error) && <p className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">{workspaceError ?? scene?.last_error}</p>}
        <button onClick={() => void renderScene()} disabled={!canRender || phaseActive} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-300 to-orange-500 px-4 py-3.5 text-sm font-bold text-zinc-950 disabled:opacity-30">{rendering || phaseActive ? <Loader2 className="h-4 w-4 animate-spin" /> : scene?.status === 'failed' ? <RotateCcw className="h-4 w-4" /> : <Clapperboard className="h-4 w-4" />}{rendering || phaseActive ? STATUS_LABELS[scene?.status ?? 'queued'] : scene?.status === 'failed' ? 'Retry Render' : scene?.render_versions.length ? 'Render New Version' : 'Render Scene'}</button>
        <p className="mt-3 text-center text-[10px] text-zinc-700">Phase status only · no invented percentage</p>
      </aside>

      <section className="min-w-0 border-t border-white/10 bg-[#090c11] px-6 py-4"><div className="mb-3 flex items-center justify-between"><div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Storyboard</div><div className="flex items-center gap-2 text-[10px] text-zinc-600"><Radio className="h-3 w-3" /> Single-scene mode</div></div><div className="flex h-[92px] gap-3"><div className="flex w-64 items-center gap-3 rounded-xl border border-amber-300/30 bg-amber-300/[0.05] p-3"><div className="flex h-14 w-20 items-center justify-center overflow-hidden rounded-lg bg-black">{previewUrl ? <img src={previewUrl} alt="Scene 01" className="h-full w-full object-cover" /> : <Film className="h-5 w-5 text-zinc-700" />}</div><div className="min-w-0"><div className="truncate text-xs font-semibold">{scene?.name ?? 'Scene 01'}</div><div className="mt-1 text-[10px] text-zinc-600">{scene ? `${scene.duration_seconds}s · ${scene.frame_count}f · ${STATUS_LABELS[scene.status]}` : 'No project'}</div></div></div><div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-zinc-700">Additional scenes remain outside this milestone</div></div></section>
    </div>
    {showNewProject && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#10141b] p-6"><h2 className="text-lg font-semibold">New Project</h2><p className="mt-1 text-sm text-zinc-500">Creates an app-owned project folder and one persisted scene.</p><input autoFocus value={newProjectName} onChange={event => setNewProjectName(event.target.value)} onKeyDown={event => event.key === 'Enter' && void createProject()} placeholder="Project name" className="mt-5 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" /><div className="mt-5 flex justify-end gap-3"><button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-zinc-500">Cancel</button><button onClick={() => void createProject()} disabled={!newProjectName.trim()} className="rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-30">Create Project</button></div></div></div>}
  </div>
}
