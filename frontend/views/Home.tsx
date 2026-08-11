import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Aperture, Clapperboard, Film, Folder, ImagePlus,
  ChevronLeft, ChevronRight, Loader2, Plus, RotateCcw, Sparkles, Square,
} from 'lucide-react'
import { SceneStoryboard } from '../components/SceneStoryboard'
import { useProjects } from '../contexts/ProjectContext'
import { useView } from '../contexts/ViewContext'
import { pathToFileUrl } from '../lib/file-url'
import { buildH3EditorProject, getH3EditorUpdates, h3EditorProjectId, replaceH3EditorVersions } from '../lib/h3-editor-bridge'
import { readProject, readProjectIds, writeProject, writeProjectIds } from '../lib/project-storage'
import { getH3RuntimeStatus, type ComfyUIStatus } from '../lib/h3-generation'
import {
  createH3Project,
  addH3Scene,
  deleteH3Scene,
  duplicateH3Scene,
  getH3Project,
  listH3Projects,
  prepareH3Continuity,
  renameH3Project,
  startH3Sequence,
  stopH3Sequence,
  reorderH3Scenes,
  selectH3Scene,
  updateH3Scene,
  type H3Project,
  type H3Scene,
  type H3SceneStatus,
  type H3RenderRun,
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
  const editorProjects = useProjects()
  const { openProject } = useView()
  const [projects, setProjects] = useState<H3Project[]>([])
  const [project, setProject] = useState<H3Project | null>(null)
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectSceneCount, setNewProjectSceneCount] = useState(5)
  const [customSceneCount, setCustomSceneCount] = useState('')
  const [showNewProject, setShowNewProject] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<ComfyUIStatus>('unavailable')
  const [runtimeVersion, setRuntimeVersion] = useState<string | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [lifecycle, setLifecycle] = useState<Awaited<ReturnType<typeof window.electronAPI.getComfyRuntimeStatus>> | null>(null)
  const [runtimeConfig, setRuntimeConfig] = useState<Awaited<ReturnType<typeof window.electronAPI.getComfyRuntimeConfig>> | null>(null)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [rendering, setRendering] = useState(false)
  const [preparingContinuity, setPreparingContinuity] = useState(false)
  const [sequenceStarting, setSequenceStarting] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [clock, setClock] = useState(Date.now())
  const saveTimer = useRef<number | null>(null)
  const pendingSave = useRef<{ projectId: string; sceneId: string; changes: Partial<H3Scene> } | null>(null)
  const scene = selectedScene(project)
  const activeRun = project?.render_runs.find(run => run.status === 'running') ?? null
  const latestRun = activeRun ?? project?.render_runs.at(-1) ?? null
  const viewedRun = project?.render_runs.find(run => run.id === selectedRunId) ?? latestRun
  const existingEditorProject = project ? readProject(h3EditorProjectId(project.id)) : null
  const editorUpdates = project && existingEditorProject ? getH3EditorUpdates(project, existingEditorProject) : []

  const openInEditor = (replaceVersions = false) => {
    if (!project) return
    const editorProjectId = h3EditorProjectId(project.id)
    const existing = readProject(editorProjectId)
    const editorProject = existing
      ? replaceVersions ? replaceH3EditorVersions(project, existing) : existing
      : buildH3EditorProject(project)
    writeProject(editorProjectId, editorProject)
    writeProjectIds([editorProjectId, ...readProjectIds().filter(id => id !== editorProjectId)])
    editorProjects.reloadProjectIds()
    openProject(editorProjectId, 'video-editor')
  }

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
    if (!runtimeConfig?.autoLaunch || lifecycle?.state !== 'stopped') return
    void window.electronAPI.startComfyRuntime().then(setLifecycle)
  }, [runtimeConfig?.autoLaunch, lifecycle?.state])

  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const [status, managed] = await Promise.all([getH3RuntimeStatus(), window.electronAPI.getComfyRuntimeStatus()])
        if (!active) return
        setRuntimeStatus(status.status)
        setRuntimeVersion(status.comfyui_version)
        setRuntimeError(status.errors[0] ?? null)
        setLifecycle(managed)
      } catch {
        if (active) {
          setRuntimeStatus('unavailable')
          setRuntimeVersion(null)
          setRuntimeError('The local ComfyUI runtime could not be reached.')
        }
      }
    }
    void refresh()
    void window.electronAPI.getComfyRuntimeConfig().then(setRuntimeConfig)
    const interval = window.setInterval(() => void refresh(), 10_000)
    return () => { active = false; window.clearInterval(interval) }
  }, [])

  useEffect(() => {
    if (!project || (!activeRun && (!scene || !ACTIVE_STATUSES.includes(scene.status)))) return
    const interval = window.setInterval(() => {
      void getH3Project(project.id).then(replaceProject).catch(() => undefined)
    }, 1_000)
    return () => window.clearInterval(interval)
  }, [project?.id, scene?.id, scene?.status, activeRun?.id])

  useEffect(() => () => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
  }, [])

  useEffect(() => {
    const interval = window.setInterval(() => setClock(Date.now()), 1_000)
    return () => window.clearInterval(interval)
  }, [])

  const updateSceneLocally = (changes: Partial<H3Scene>) => {
    if (!project || !scene) return
    setProject({ ...project, scenes: project.scenes.map(item => item.id === scene.id ? { ...item, ...changes } : item) })
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
    const pending = pendingSave.current
    pendingSave.current = {
      projectId: project.id,
      sceneId: scene.id,
      changes: pending?.projectId === project.id && pending.sceneId === scene.id ? { ...pending.changes, ...changes } : changes,
    }
    setSaveState('saving')
    saveTimer.current = window.setTimeout(() => {
      const save = pendingSave.current
      pendingSave.current = null
      if (!save) return
      void updateH3Scene(save.projectId, save.sceneId, save.changes).then(next => {
        replaceProject(next)
        setSaveState('saved')
      }).catch(() => setSaveState('error'))
    }, 500)
  }

  const flushPendingSave = async () => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current)
    saveTimer.current = null
    const save = pendingSave.current
    pendingSave.current = null
    if (!save) return
    replaceProject(await updateH3Scene(save.projectId, save.sceneId, save.changes))
    setSaveState('saved')
  }

  const runSceneOperation = async (operation: () => Promise<H3Project>) => {
    try {
      await flushPendingSave()
      replaceProject(await operation())
      setWorkspaceError(null)
    } catch (error) {
      setSaveState('error')
      setWorkspaceError(error instanceof Error ? error.message : 'The scene change could not be saved.')
    }
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
      const count = customSceneCount ? Number(customSceneCount) : newProjectSceneCount
      if (!Number.isInteger(count) || count < 1 || count > 999) throw new Error('Scene count must be a positive whole number up to 999.')
      const next = await createH3Project(newProjectName.trim(), count)
      replaceProject(next)
      setNewProjectName('')
      setCustomSceneCount('')
      setShowNewProject(false)
      setWorkspaceError(null)
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The project could not be created.')
    }
  }

  const moveScene = (target: H3Scene, direction: -1 | 1) => {
    if (!project) return
    const ids = project.scenes.map(item => item.id)
    const index = ids.indexOf(target.id)
    const destination = index + direction
    if (index < 0 || destination < 0 || destination >= ids.length) return
    ;[ids[index], ids[destination]] = [ids[destination], ids[index]]
    void runSceneOperation(() => reorderH3Scenes(project.id, ids))
  }

  const renderScene = async () => {
    if (!project || !scene || !scene.prompt.trim() || runtimeStatus !== 'connected') return
    setRendering(true)
    setWorkspaceError(null)
    try {
      await flushPendingSave()
      const saved = await updateH3Scene(project.id, scene.id, {
        prompt: scene.prompt, reference_image: scene.reference_image, seed: scene.seed,
        width: scene.width, height: scene.height, fps: scene.fps,
        duration_seconds: scene.duration_seconds, frame_count: scene.frame_count,
      })
      replaceProject({ ...saved, scenes: saved.scenes.map(item => item.id === scene.id ? { ...item, status: 'queued', current_phase: 'Waiting' } : item) })
      const run = await startH3Sequence(project.id, 'scene', scene.id)
      setSelectedRunId(run.id)
      replaceProject(await getH3Project(project.id))
      setSaveState('saved')
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The local render failed.')
      try { replaceProject(await getH3Project(project.id)) } catch { /* retain recoverable local state */ }
    } finally {
      setRendering(false)
    }
  }

  const prepareContinuity = async () => {
    if (!project || !scene || scene.mode !== 'continue_previous') return
    setPreparingContinuity(true)
    setWorkspaceError(null)
    try {
      await flushPendingSave()
      const response = await prepareH3Continuity(project.id, scene.id)
      replaceProject(response.project)
      setSaveState('saved')
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The continuity frame could not be extracted.')
      try { replaceProject(await getH3Project(project.id)) } catch { /* retain recoverable local state */ }
    } finally {
      setPreparingContinuity(false)
    }
  }

  const startSequence = async (kind: 'from_here' | 'all') => {
    if (!project || !scene || runtimeStatus !== 'connected' || activeRun) return
    setSequenceStarting(true)
    setWorkspaceError(null)
    try {
      await flushPendingSave()
      const run = await startH3Sequence(project.id, kind, kind === 'from_here' ? scene.id : undefined)
      setSelectedRunId(run.id)
      replaceProject(await getH3Project(project.id))
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The render queue could not be started.')
    } finally {
      setSequenceStarting(false)
    }
  }

  const stopSequence = async (run: H3RenderRun) => {
    if (!project) return
    try {
      await stopH3Sequence(project.id, run.id)
      replaceProject(await getH3Project(project.id))
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'The render queue could not be stopped safely.')
    }
  }

  const activeVersion = useMemo(() => scene?.render_versions.find(
    version => version.id === scene.selected_render_version_id,
  ) ?? null, [scene])
  const previewUrl = activeVersion
    ? pathToFileUrl(activeVersion.video_file)
    : scene?.reference_image ? pathToFileUrl(scene.reference_image) : null
  const sourceScene = scene && project ? [...project.scenes].sort((a, b) => a.order - b.order)[scene.order - 2] ?? null : null
  const sourceVersion = sourceScene?.render_versions.find(item => item.id === sourceScene.selected_render_version_id) ?? null
  const selectedContinuityArtifact = scene?.continuity_artifacts.find(item => item.id === scene.selected_continuity_artifact_id) ?? null
  const continuityArtifact = selectedContinuityArtifact
    && selectedContinuityArtifact.source_scene_id === sourceScene?.id
    && selectedContinuityArtifact.source_render_version_id === sourceVersion?.id
    && selectedContinuityArtifact.strategy === scene?.continuity_strategy
    && selectedContinuityArtifact.offset_from_end_frames === (scene?.continuity_strategy === 'offset_from_end' ? scene.continuity_offset_frames : 0)
    ? selectedContinuityArtifact : null
  const modeHasInput = scene?.mode === 'continue_previous' ? Boolean(sourceVersion) : scene?.mode === 'new_shot' ? Boolean(scene.reference_image) : false
  const canRender = Boolean(project && scene?.prompt.trim() && modeHasInput && runtimeStatus === 'connected' && !rendering && !preparingContinuity)
  const phaseActive = scene ? ACTIVE_STATUSES.includes(scene.status) : false
  const activeVersionIndex = scene?.render_versions.findIndex(version => version.id === scene.selected_render_version_id) ?? -1
  const selectVersionAt = (index: number) => {
    if (!project || !scene || index < 0 || index >= scene.render_versions.length) return
    void updateH3Scene(project.id, scene.id, { selected_render_version_id: scene.render_versions[index].id }).then(replaceProject)
  }

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
        </div><div className="flex items-center gap-3"><button onClick={() => openInEditor(false)} disabled={!project || !project.scenes.some(item => item.selected_render_version_id)} className="rounded-lg border border-white/10 px-4 py-2 text-xs font-medium text-zinc-300 disabled:opacity-30"><Film className="mr-2 inline h-3.5 w-3.5" />Open in Editor</button>{editorUpdates.length > 0 && <button onClick={() => openInEditor(true)} className="rounded-lg border border-amber-300/30 px-3 py-2 text-xs text-amber-200">Update {editorUpdates.length} selected version{editorUpdates.length === 1 ? '' : 's'}</button>}<div className="text-right"><StatusPill status={runtimeStatus} />{runtimeVersion && <div className="mt-1 text-[10px] text-zinc-600">ComfyUI {runtimeVersion}</div>}</div></div></header>
        <section className="relative flex h-[calc(100%-64px)] min-h-[360px] items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
          {previewUrl ? activeVersion ? <video key={previewUrl} src={previewUrl} controls autoPlay loop className="h-full w-full object-contain" /> : <img src={previewUrl} alt="Selected scene reference" className="h-full w-full object-contain opacity-90" /> : <div className="max-w-sm text-center"><Film className="mx-auto h-10 w-10 text-zinc-700" /><h2 className="mt-5 text-lg text-zinc-300">Your selected render will appear here</h2><p className="mt-2 text-sm text-zinc-600">Create a project and save the scene reference to begin.</p></div>}
          <div className="absolute left-4 top-4 rounded-full border border-white/10 bg-black/60 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-zinc-400">Scene preview</div>
          {scene && <div className={`absolute bottom-4 right-4 rounded-full px-3 py-1.5 text-xs font-semibold ${scene.status === 'failed' ? 'bg-red-400/90 text-red-950' : scene.status === 'complete' ? 'bg-emerald-400/90 text-emerald-950' : 'bg-amber-300/90 text-amber-950'}`}>{STATUS_LABELS[scene.status]}</div>}
        </section>
      </main>

      <aside className="row-span-2 min-h-0 overflow-y-auto border-l border-white/10 bg-[#0b0e13] p-5">
        <div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-amber-300" /> Director controls</div>{scene && <span className="text-[10px] uppercase tracking-wider text-zinc-600">{STATUS_LABELS[scene.status]}</span>}</div>
        <label className="mt-6 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene name<input value={scene?.name ?? ''} disabled={!scene} onChange={event => updateSceneLocally({ name: event.target.value })} className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2.5 text-sm normal-case tracking-normal outline-none focus:border-amber-300/40" /></label>
        <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene prompt<textarea value={scene?.prompt ?? ''} disabled={!scene} onChange={event => updateSceneLocally({ prompt: event.target.value })} className="mt-2 h-32 w-full resize-none rounded-xl border border-white/10 bg-black/30 p-3 text-sm normal-case leading-6 tracking-normal outline-none focus:border-amber-300/40" placeholder="Describe the shot, movement, lighting, mood and audio…" /></label>
        <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene Mode<select value={scene?.mode ?? 'new_shot'} disabled={!scene} onChange={event => updateSceneLocally({ mode: event.target.value as H3Scene['mode'] })} className="mt-2 w-full rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm normal-case tracking-normal text-zinc-300"><option value="new_shot">New Shot</option><option value="continue_previous">Continue Previous</option><option value="same_character_new_shot">Same Character, New Shot — unavailable</option></select></label>
        {scene?.mode === 'same_character_new_shot' && <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/70">Unavailable: the verified MiniMax H3 workflow has one image input and no separate character-reference control.</p>}
        {scene?.mode === 'continue_previous' && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Continuity source</div><div className="mt-2 text-xs text-zinc-300">{sourceScene ? `${sourceScene.name} · ${sourceVersion?.id ?? 'no selected completed version'}` : 'Blocked · no previous scene'}</div><label className="mt-3 block text-[10px] uppercase tracking-wider text-zinc-600">Extraction strategy<select value={scene.continuity_strategy} onChange={event => updateSceneLocally({ continuity_strategy: event.target.value as H3Scene['continuity_strategy'] })} className="mt-1 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-xs normal-case tracking-normal text-zinc-300"><option value="last_valid_frame">Last valid frame</option><option value="offset_from_end">Offset from end</option></select></label>{scene.continuity_strategy === 'offset_from_end' && <label className="mt-3 block text-[10px] uppercase tracking-wider text-zinc-600">Offset from end · frames<input type="number" min="0" value={scene.continuity_offset_frames} onChange={event => updateSceneLocally({ continuity_offset_frames: Math.max(0, Number(event.target.value)) })} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 font-mono text-xs text-zinc-300" /></label>}{continuityArtifact && <div className="mt-3 flex gap-3"><img src={pathToFileUrl(continuityArtifact.image_file)} alt="Extracted continuity frame" className="h-16 w-24 rounded-lg bg-black object-cover" /><div className="text-[10px] leading-5 text-zinc-500">{continuityArtifact.id}<br />Frame {continuityArtifact.frame_index} · {continuityArtifact.timestamp_seconds.toFixed(3)}s<br />Source {continuityArtifact.source_render_version_id}</div></div>}<button onClick={() => void prepareContinuity()} disabled={!sourceVersion || preparingContinuity} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-amber-300/20 px-3 py-2 text-xs text-amber-200 disabled:opacity-30">{preparingContinuity && <Loader2 className="h-3 w-3 animate-spin" />} Extract Continuity Frame</button>{!sourceVersion && <p className="mt-2 text-[10px] text-red-300">Rendering is blocked until the previous scene has a selected completed render.</p>}</div>}
        <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Reference image<button onClick={() => void chooseReferenceImage()} disabled={!scene} className="mt-2 flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.025] px-3 py-3 text-sm normal-case tracking-normal text-zinc-400"><span className="truncate">{scene?.reference_image?.split(/[\\/]/).pop() ?? 'Choose image'}</span><ImagePlus className="h-4 w-4" /></button></label>
        <div className="mt-6 grid grid-cols-2 gap-3">{scene && [
          ['Width', scene.width], ['Height', scene.height], ['FPS', scene.fps], ['Duration', `${scene.duration_seconds}s`], ['Frames', scene.frame_count],
        ].map(([label, value]) => <div key={label} className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">{label}</div><div className="mt-1 font-mono text-sm text-zinc-300">{value}</div></div>)}
          <label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Seed</div><input type="number" disabled={!scene} value={scene?.seed ?? 0} onChange={event => updateSceneLocally({ seed: Number(event.target.value) })} className="mt-1 w-full bg-transparent font-mono text-sm text-zinc-300 outline-none" /></label>
        </div>
        {!!scene?.render_versions.length && <div className="mt-5"><div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Render version</div><div className="mt-2 flex gap-2"><button aria-label="Previous version" disabled={activeVersionIndex <= 0} onClick={() => selectVersionAt(activeVersionIndex - 1)} className="rounded-lg border border-white/10 px-2 disabled:opacity-25"><ChevronLeft className="h-4 w-4" /></button><select value={scene.selected_render_version_id ?? ''} onChange={event => void updateH3Scene(project!.id, scene.id, { selected_render_version_id: event.target.value }).then(replaceProject)} className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm text-zinc-300">{scene.render_versions.map(version => <option key={version.id} value={version.id}>v{String(version.number).padStart(3, '0')} · {new Date(version.created_at).toLocaleString()}</option>)}</select><button aria-label="Next version" disabled={activeVersionIndex < 0 || activeVersionIndex >= scene.render_versions.length - 1} onClick={() => selectVersionAt(activeVersionIndex + 1)} className="rounded-lg border border-white/10 px-2 disabled:opacity-25"><ChevronRight className="h-4 w-4" /></button></div>{activeVersion && <div className="mt-2 rounded-lg bg-white/[0.025] p-2 text-[10px] leading-5 text-zinc-500"><div>{new Date(activeVersion.created_at).toLocaleString()} · {activeVersion.width}×{activeVersion.height} · {activeVersion.duration_seconds}s</div><div>Seed {activeVersion.seed} · Prompt ID {activeVersion.prompt_id}</div></div>}</div>}
        <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><div className="flex items-center justify-between"><span className="font-semibold text-zinc-300">Local backend</span><span className="uppercase text-[10px] text-zinc-500">{lifecycle?.state.replace('_', ' ') ?? 'checking'}</span></div><p className="mt-1 text-[10px] text-zinc-500">{lifecycle?.owned ? 'Started by H3 Director' : lifecycle?.state === 'ready' ? 'Using existing ComfyUI' : lifecycle?.error ?? 'Configure a local ComfyUI runtime.'}</p>{runtimeConfig && <div className="mt-3 grid gap-2"><input value={runtimeConfig.rootPath} onChange={e => setRuntimeConfig({ ...runtimeConfig, rootPath: e.target.value })} placeholder="ComfyUI root" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><input value={runtimeConfig.pythonPath} onChange={e => setRuntimeConfig({ ...runtimeConfig, pythonPath: e.target.value })} placeholder="ComfyUI Python" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><label className="flex items-center gap-2 text-[10px] text-zinc-500">Port <input type="number" value={runtimeConfig.port} onChange={e => setRuntimeConfig({ ...runtimeConfig, port: Number(e.target.value) })} className="w-16 rounded border border-white/10 bg-black/30 px-1 py-1 text-zinc-300" /><input type="checkbox" checked={runtimeConfig.autoLaunch} onChange={e => setRuntimeConfig({ ...runtimeConfig, autoLaunch: e.target.checked })} /> Auto-launch</label><button onClick={() => void window.electronAPI.saveComfyRuntimeConfig({ config: runtimeConfig }).then(setRuntimeConfig)} className="rounded border border-white/10 px-2 py-1.5 text-[10px]">Save runtime settings</button></div>}<div className="mt-3 grid grid-cols-3 gap-1"><button onClick={() => void window.electronAPI.startComfyRuntime().then(setLifecycle)} className="rounded border border-emerald-400/20 px-2 py-1.5 text-[10px] text-emerald-200">Start</button><button disabled={!lifecycle?.owned} onClick={() => void window.electronAPI.stopComfyRuntime().then(setLifecycle)} className="rounded border border-red-400/20 px-2 py-1.5 text-[10px] text-red-200 disabled:opacity-30">Stop</button><button disabled={!lifecycle?.owned} onClick={() => void window.electronAPI.restartComfyRuntime().then(setLifecycle)} className="rounded border border-amber-400/20 px-2 py-1.5 text-[10px] text-amber-200 disabled:opacity-30">Restart</button></div></div>
        {runtimeError && runtimeStatus !== 'connected' && <p className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/70">{runtimeError}</p>}
        {(workspaceError || scene?.last_error) && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300"><p>{workspaceError ?? scene?.last_error}</p>{scene?.diagnostics && <details className="mt-2 text-[10px] text-red-200/60"><summary className="cursor-pointer">Technical diagnostics</summary><div className="mt-1 font-mono">{scene.diagnostics}</div></details>}</div>}
        <button onClick={() => void renderScene()} disabled={!canRender || phaseActive || Boolean(activeRun)} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-300 to-orange-500 px-4 py-3.5 text-sm font-bold text-zinc-950 disabled:opacity-30">{rendering || phaseActive ? <Loader2 className="h-4 w-4 animate-spin" /> : scene?.status === 'failed' ? <RotateCcw className="h-4 w-4" /> : <Clapperboard className="h-4 w-4" />}{rendering || phaseActive ? STATUS_LABELS[scene?.status ?? 'queued'] : scene?.status === 'failed' ? 'Retry Render' : scene?.render_versions.length ? 'Render New Version' : 'Render Scene'}</button>
        <div className="mt-3 grid grid-cols-2 gap-2"><button onClick={() => void startSequence('from_here')} disabled={!project || !scene || runtimeStatus !== 'connected' || Boolean(activeRun) || sequenceStarting} className="rounded-lg border border-amber-300/20 px-3 py-2.5 text-xs text-amber-200 disabled:opacity-30">Render From Here</button><button onClick={() => void startSequence('all')} disabled={!project || runtimeStatus !== 'connected' || Boolean(activeRun) || sequenceStarting} className="rounded-lg border border-amber-300/20 px-3 py-2.5 text-xs text-amber-200 disabled:opacity-30">Render All</button></div>
        {activeRun && <button onClick={() => void stopSequence(activeRun)} disabled={activeRun.stop_after_current_requested} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-red-400/20 px-3 py-2.5 text-xs text-red-300 disabled:opacity-40"><Square className="h-3 w-3" />{activeRun.stop_after_current_requested ? 'Stopping after current scene…' : 'Stop after current scene'}</button>}
        {viewedRun && <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3"><div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500"><span>{viewedRun.kind === 'scene' ? 'Render Scene' : viewedRun.kind === 'from_here' ? 'Render From Here' : 'Render All'}</span><span>{viewedRun.status}</span></div><div className="mt-1 font-mono text-[9px] text-zinc-700">Run {viewedRun.id}</div><div className="mt-2 text-[10px] text-zinc-500">Current scene: {project?.scenes.find(candidate => candidate.id === viewedRun.current_scene_id)?.name ?? 'None'}</div><div className="mt-2 grid grid-cols-2 gap-1 text-[10px] text-zinc-500"><span>Started {new Date(viewedRun.started_at).toLocaleString()}</span><span>Elapsed {Math.max(0, Math.floor(((viewedRun.completed_at ? new Date(viewedRun.completed_at).getTime() : clock) - new Date(viewedRun.started_at).getTime()) / 1000))}s</span><span>Complete {viewedRun.items.filter(item => item.state === 'complete').length}</span><span>Waiting {viewedRun.items.filter(item => item.state === 'waiting').length}</span><span>Failed {viewedRun.items.filter(item => item.state === 'failed').length}</span><span>Cancelled {viewedRun.items.filter(item => item.state === 'cancelled').length}</span></div><div className="mt-2 space-y-1.5">{viewedRun.items.map(item => { const queuedScene = project?.scenes.find(candidate => candidate.id === item.scene_id); const percent = item.progress_value !== null && item.progress_max ? Math.round(item.progress_value / item.progress_max * 100) : null; return <div key={item.scene_id} className={`rounded-lg px-2 py-1.5 text-[11px] ${viewedRun.current_scene_id === item.scene_id ? 'bg-amber-300/10 text-amber-200' : 'bg-white/[0.025] text-zinc-500'}`}><div className="flex justify-between"><span className="truncate">{queuedScene?.name ?? `Scene ${item.scene_order}`}</span><span className="ml-2 uppercase">{item.current_phase ?? item.state}{percent !== null ? ` · ${percent}%` : ''}</span></div>{item.render_version_id && <div className="mt-1 text-[9px] text-zinc-700">{item.render_version_id} · {item.prompt_id}{item.continuity_artifact_id ? ` · ${item.continuity_artifact_id}` : ''}</div>}{item.diagnostics && <details className="mt-1 text-[9px] text-red-300/60"><summary>Diagnostics</summary>{item.diagnostics}</details>}</div> })}</div>{viewedRun.failure_or_cancel_reason && <p className="mt-2 text-[10px] text-red-300">{viewedRun.failure_or_cancel_reason}</p>} {!!project?.render_runs.length && <label className="mt-3 block text-[9px] uppercase tracking-wider text-zinc-600">Run history<select value={viewedRun.id} onChange={event => setSelectedRunId(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-[10px] normal-case text-zinc-400">{[...project.render_runs].reverse().map(run => <option key={run.id} value={run.id}>{run.kind} · {new Date(run.started_at).toLocaleString()} · {run.status}</option>)}</select></label>}</div>}
        <p className="mt-3 text-center text-[10px] text-zinc-700">Real sampler progress only · phase otherwise</p>
      </aside>

      <SceneStoryboard project={project} statusLabels={STATUS_LABELS} onSelect={target => project && target.id !== project.selected_scene_id && void runSceneOperation(() => selectH3Scene(project.id, target.id))} onAdd={() => project && void runSceneOperation(() => addH3Scene(project.id))} onDuplicate={target => project && void runSceneOperation(() => duplicateH3Scene(project.id, target.id))} onDelete={target => project && void runSceneOperation(() => deleteH3Scene(project.id, target.id))} onMove={moveScene} />
    </div>
    {showNewProject && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#10141b] p-6"><h2 className="text-lg font-semibold">New Project</h2><p className="mt-1 text-sm text-zinc-500">Creates an app-owned project folder and persisted scene cards.</p><input autoFocus value={newProjectName} onChange={event => setNewProjectName(event.target.value)} placeholder="Project name" className="mt-5 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" /><div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene count</div><div className="mt-2 grid grid-cols-4 gap-2">{[5, 10, 15].map(count => <button key={count} onClick={() => { setNewProjectSceneCount(count); setCustomSceneCount('') }} className={`rounded-lg border px-3 py-2 text-sm ${!customSceneCount && newProjectSceneCount === count ? 'border-amber-300/50 bg-amber-300/10 text-amber-200' : 'border-white/10 text-zinc-500'}`}>{count}</button>)}<input type="number" min="1" max="999" value={customSceneCount} onChange={event => setCustomSceneCount(event.target.value)} placeholder="Custom" aria-label="Custom positive scene count" className="rounded-lg border border-white/10 bg-black/30 px-2 text-center text-sm outline-none" /></div><div className="mt-5 flex justify-end gap-3"><button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-zinc-500">Cancel</button><button onClick={() => void createProject()} disabled={!newProjectName.trim()} className="rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-30">Create Project</button></div></div></div>}
  </div>
}
