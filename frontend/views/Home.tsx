import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Clapperboard, Film, Folder, ImagePlus,
  ChevronDown, ChevronLeft, ChevronRight, Loader2, Plus, RotateCcw, Sparkles, Square,
} from 'lucide-react'
import { SceneStoryboard } from '../components/SceneStoryboard'
import { useProjects } from '../contexts/ProjectContext'
import { useView } from '../contexts/ViewContext'
import { pathToFileUrl } from '../lib/file-url'
import { buildH3EditorProject, getH3EditorUpdates, h3EditorProjectId, refreshH3EditorProvenance, replaceH3EditorVersions } from '../lib/h3-editor-bridge'
import { readProject, readProjectIds, writeProject, writeProjectIds } from '../lib/project-storage'
import { getH3RuntimeStatus, type ComfyUIStatus } from '../lib/h3-generation'
import { composeH3AudioPrompt, h3AudioSummary } from '../lib/h3-audio-guidance'
import { getOllamaStatus, localPromptAssistant, OllamaH3PromptAssistant, type H3OllamaStatus } from '../lib/h3-prompt-assistant'
import { H3_WORKFLOW_PROFILES, LTX_2_5_OFFICIAL_MODEL_PAGE, workflowProfileRegistry } from '../lib/h3-workflow-profiles'
import { RTX_VSR_SETUP_REQUIRED, createUpscaleVariantPlan } from '../lib/h3-upscale'
import {
  createH3Project,
  addH3Scene,
  deleteH3Scene,
  duplicateH3Scene,
  getH3Project,
  listH3Projects,
  prepareH3Continuity,
  renameH3Project,
  updateH3Project,
  startH3Sequence,
  stopH3Sequence,
  getH3UpscaleAvailability,
  upscaleH3Render,
  reorderH3Scenes,
  selectH3Scene,
  updateH3Scene,
  installH3WorkflowProfile,
  importH3Ltx25Models,
  type H3Project,
  type H3Scene,
  type H3SceneStatus,
  type H3AspectRatio,
  type H3ResolutionMegapixels,
  type H3SequenceMode,
  type H3WorkflowProfileId,
  type H3WorkflowMode,
  type H3RenderRun,
  type H3UpscaleAvailability,
  type H3Ltx25ModelImportResult,
} from '../lib/h3-projects'

const ACTIVE_STATUSES: H3SceneStatus[] = ['queued', 'preparing', 'submitted', 'rendering', 'encoding', 'verifying']
const STATUS_LABELS: Record<H3SceneStatus, string> = {
  idle: 'Ready', queued: 'Queued', preparing: 'Preparing input', submitted: 'Submitted',
  rendering: 'Rendering in ComfyUI', encoding: 'Encoding', verifying: 'Verifying with ffprobe',
  complete: 'Complete', failed: 'Failed', cancelled: 'Cancelled',
}
const H3_RESOLUTION_PRESETS: Record<H3AspectRatio, Record<H3ResolutionMegapixels, readonly [number, number]>> = {
  '1:1 (Square)': { 0.4: [640, 640], 0.6: [800, 800], 0.8: [928, 928], 0.9: [960, 960], 1: [1024, 1024] },
  '16:9 (Widescreen)': { 0.4: [864, 480], 0.6: [1056, 608], 0.8: [1216, 672], 0.9: [1280, 704], 1: [1376, 768] },
  '9:16 (Portrait Widescreen)': { 0.4: [480, 864], 0.6: [608, 1056], 0.8: [672, 1216], 0.9: [736, 1280], 1: [768, 1376] },
}

function H3ThemedSelect<T extends string | number>({
  value, options, onChange, ariaLabel,
}: {
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (value: T) => void
  ariaLabel: string
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find(option => option.value === value)
  return <div className="relative mt-1">
    <button type="button" aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(current => !current)} className="flex w-full items-center justify-between rounded-lg border border-white/15 bg-[#11151c] px-2.5 py-2 text-sm text-zinc-100 shadow-sm outline-none transition hover:border-white/25 focus:border-amber-300/70 focus:ring-2 focus:ring-amber-300/20">
      <span>{selected?.label}</span><ChevronDown className={`h-3.5 w-3.5 text-zinc-400 transition ${open ? 'rotate-180' : ''}`} />
    </button>
    {open && <div role="listbox" aria-label={ariaLabel} className="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-white/15 bg-[#11151c] p-1 shadow-2xl shadow-black/60">
      {options.map(option => <button key={String(option.value)} type="button" role="option" aria-selected={option.value === value} onClick={() => { onChange(option.value); setOpen(false) }} className={`block w-full rounded-md px-2.5 py-2 text-left text-sm transition ${option.value === value ? 'bg-amber-300/20 text-amber-100' : 'text-zinc-100 hover:bg-white/10 hover:text-white'}`}>{option.label}</button>)}
    </div>}
  </div>
}

export function h3FrameCountForDuration(durationSeconds: number, fps: number): number {
  const sampledFrames = Math.max(5, Math.round(durationSeconds * fps))
  return sampledFrames + (5 - (sampledFrames % 17)) % 17
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

function frameCountForWorkflow(profileId: H3WorkflowProfileId | undefined, durationSeconds: number, fps: number): number {
  // Captured LTX I2V node 398:378 is exactly `duration * fps + 1`.
  return profileId === 'ltx_2_5_image_to_video'
    ? Math.max(1, Math.round(durationSeconds * fps) + 1)
    : h3FrameCountForDuration(durationSeconds, fps)
}

export function Home() {
  const editorProjects = useProjects()
  const { openProject } = useView()
  const [projects, setProjects] = useState<H3Project[]>([])
  const [project, setProject] = useState<H3Project | null>(null)
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectSceneCount, setNewProjectSceneCount] = useState(5)
  const [customSceneCount, setCustomSceneCount] = useState('')
  const [newProjectSequenceMode, setNewProjectSequenceMode] = useState<H3SequenceMode>('independent_shots')
  const [showNewProject, setShowNewProject] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<ComfyUIStatus>('unavailable')
  const [runtimeVersion, setRuntimeVersion] = useState<string | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [lifecycle, setLifecycle] = useState<Awaited<ReturnType<typeof window.electronAPI.getComfyRuntimeStatus>> | null>(null)
  const [ollamaLifecycle, setOllamaLifecycle] = useState<Awaited<ReturnType<typeof window.electronAPI.getOllamaRuntimeStatus>> | null>(null)
  const [runtimeConfig, setRuntimeConfig] = useState<Awaited<ReturnType<typeof window.electronAPI.getComfyRuntimeConfig>> | null>(null)
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved')
  const [rendering, setRendering] = useState(false)
  const [preparingContinuity, setPreparingContinuity] = useState(false)
  const [sequenceStarting, setSequenceStarting] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [fileActionMessage, setFileActionMessage] = useState<string | null>(null)
  const [ltx25Models, setLtx25Models] = useState<H3Ltx25ModelImportResult | null>(null)
  const [ltx25Importing, setLtx25Importing] = useState(false)
  const [upscaleAvailability, setUpscaleAvailability] = useState<H3UpscaleAvailability>(RTX_VSR_SETUP_REQUIRED)
  const [upscaling, setUpscaling] = useState(false)
  const [selectedUpscaleVariantId, setSelectedUpscaleVariantId] = useState<string | null>(null)
  const [promptAssistantMessage, setPromptAssistantMessage] = useState<string | null>(null)
  const [promptSuggestion, setPromptSuggestion] = useState<string | null>(null)
  const [promptAssistantBusy, setPromptAssistantBusy] = useState(false)
  const [ollamaStatus, setOllamaStatus] = useState<H3OllamaStatus | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [clock, setClock] = useState(Date.now())
  const saveTimer = useRef<number | null>(null)
  const previewVideoRef = useRef<HTMLVideoElement | null>(null)
  const pendingSave = useRef<{ projectId: string; sceneId: string; changes: Partial<H3Scene> } | null>(null)
  const scene = selectedScene(project)
  const selectedWorkflowProfile = project ? workflowProfileRegistry.get(project.workflow_profile_id) : null
  const selectedWorkflowMode = selectedWorkflowProfile && project ? workflowProfileRegistry.mode(project.workflow_profile_id, project.workflow_mode) : null
  const profileAspectRatios = selectedWorkflowMode?.aspectRatios.length ? selectedWorkflowMode.aspectRatios : ['1:1 (Square)', '16:9 (Widescreen)', '9:16 (Portrait Widescreen)'] as const
  const profileResolutionMegapixels = selectedWorkflowMode?.resolutionMegapixels.length ? selectedWorkflowMode.resolutionMegapixels : [0.4, 0.6, 0.8, 1] as const
  const managedBaseUrl = lifecycle?.endpoint ?? `http://127.0.0.1:${runtimeConfig?.port ?? 8190}`
  const ollamaEndpoint = 'http://127.0.0.1:11434'
  const activeRun = project?.render_runs.find(run => run.status === 'running') ?? null
  const latestRun = activeRun ?? project?.render_runs.at(-1) ?? null
  const viewedRun = project?.render_runs.find(run => run.id === selectedRunId) ?? latestRun
  const existingEditorProject = project ? readProject(h3EditorProjectId(project.id)) : null
  const editorUpdates = project && existingEditorProject ? getH3EditorUpdates(project, existingEditorProject) : []

  useEffect(() => {
    if (lifecycle?.state !== 'ready') { setUpscaleAvailability(RTX_VSR_SETUP_REQUIRED); return }
    void getH3UpscaleAvailability(managedBaseUrl).then(setUpscaleAvailability).catch(() => setUpscaleAvailability(RTX_VSR_SETUP_REQUIRED))
  }, [lifecycle?.state, managedBaseUrl])

  const refreshLtx25Models = async (filePaths: string[] = []) => {
    if (!runtimeConfig?.extraModelPathsConfig) throw new Error('Configure and save Extra model paths config before importing LTX 2.5 files.')
    const result = await importH3Ltx25Models(filePaths, runtimeConfig.extraModelPathsConfig)
    setLtx25Models(result)
    return result
  }

  const importLtx25Models = async () => {
    try {
      setLtx25Importing(true); setWorkspaceError(null); setFileActionMessage(null)
      const files = await window.electronAPI.showOpenFileDialog({ title: 'Import official LTX 2.5 model files', filters: [{ name: 'SafeTensor model files', extensions: ['safetensors'] }], properties: ['multiSelections'] })
      if (!files?.length) return
      const result = await refreshLtx25Models(files)
      setFileActionMessage(result.imported_count ? `Imported ${result.imported_count} selected official LTX 2.5 model file${result.imported_count === 1 ? '' : 's'}. Workflow verification is still required before rendering.` : 'No files were imported. Existing files are preserved and unknown files are rejected.')
    } catch (error) { setWorkspaceError(error instanceof Error ? error.message : 'LTX 2.5 model import failed.') } finally { setLtx25Importing(false) }
  }

  const upscaleActiveVersion = async () => {
    if (!project || !scene || !activeVersion || !runtimeConfig || !upscaleAvailability.available) return
    const existing = activeVersion.upscale_variants.find(item => item.backend === 'nvidia_rtx_vsr' && item.scale === 2)
    if (existing) {
      setSelectedUpscaleVariantId(existing.id)
      setFileActionMessage('Showing the existing immutable RTX VSR 2× version. Create a new source render before making another upscale version.')
      return
    }
    setUpscaling(true); setFileActionMessage(null); setWorkspaceError(null)
    try {
      replaceProject(await upscaleH3Render(project.id, scene.id, activeVersion.id, {
        baseUrl: managedBaseUrl, inputDirectory: runtimeConfig.inputDirectory ?? '', outputDirectory: runtimeConfig.outputDirectory ?? '',
      }))
      setSelectedUpscaleVariantId(null)
      setFileActionMessage(`Created immutable 2× RTX VSR version from ${createUpscaleVariantPlan(activeVersion).sourceResolution}.`)
    } catch (error) { setWorkspaceError(error instanceof Error ? error.message : 'Local RTX VSR upscaling failed.') } finally { setUpscaling(false) }
  }

  const openInEditor = (replaceVersions = false) => {
    if (!project) return
    previewVideoRef.current?.pause()
    const editorProjectId = h3EditorProjectId(project.id)
    const existing = readProject(editorProjectId)
    const editorProject = existing
      ? replaceVersions ? replaceH3EditorVersions(project, existing) : refreshH3EditorProvenance(project, existing)
      : buildH3EditorProject(project)
    writeProject(editorProjectId, editorProject)
    writeProjectIds([editorProjectId, ...readProjectIds().filter(id => id !== editorProjectId)])
    editorProjects.reloadProjectIds()
    openProject(editorProjectId, 'video-editor')
  }

  const openActiveMediaInEditor = () => {
    if (!project || !scene || !activeVersion || !activeUpscaleVariant) { openInEditor(false); return }
    previewVideoRef.current?.pause()
    const derivedProject: H3Project = {
      ...project,
      scenes: project.scenes.map(candidate => candidate.id !== scene.id ? candidate : {
        ...candidate,
        render_versions: candidate.render_versions.map(version => version.id !== activeVersion.id ? version : {
          ...version,
          video_file: activeUpscaleVariant.video_file,
          metadata_file: activeUpscaleVariant.metadata_file,
          output_sha256: activeUpscaleVariant.output_sha256,
          width: activeUpscaleVariant.width, height: activeUpscaleVariant.height,
          duration_seconds: activeUpscaleVariant.duration_seconds, frame_count: activeUpscaleVariant.ffprobe.frame_count,
          ffprobe: activeUpscaleVariant.ffprobe,
        }),
      }),
    }
    const editorProjectId = h3EditorProjectId(project.id)
    writeProject(editorProjectId, buildH3EditorProject(derivedProject))
    writeProjectIds([editorProjectId, ...readProjectIds().filter(id => id !== editorProjectId)])
    editorProjects.reloadProjectIds()
    openProject(editorProjectId, 'video-editor')
  }

  const replaceProject = (next: H3Project) => {
    setProject(next)
    setProjects(current => [next, ...current.filter(item => item.id !== next.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
  }

  const saveRuntimeSettings = async () => {
    if (!runtimeConfig) return
    setSaveState('saving')
    try {
      const saved = await window.electronAPI.saveComfyRuntimeConfig({ config: { ...runtimeConfig, ollamaEndpoint } })
      setRuntimeConfig(saved)
      setSaveState('saved')
    } catch (error) {
      setSaveState('error')
      setWorkspaceError(error instanceof Error ? error.message : 'Runtime settings could not be saved.')
    }
  }

  const startManagedRuntime = async () => {
    setWorkspaceError(null)
    setLifecycle(current => current ? { ...current, state: 'starting', error: null } : current)
    try {
      const next = await window.electronAPI.startComfyRuntime()
      setLifecycle(next)
      if (next.state === 'failed') setWorkspaceError(next.error ?? 'Managed runtime failed to start.')
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'Managed runtime failed to start.')
      setLifecycle(current => current ? { ...current, state: 'failed' } : current)
    }
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
        const profileId = project?.workflow_profile_id === 'minimax_h3_no_reference'
          ? 'minimax_h3_no_reference'
          : 'minimax_h3_image_to_video'
        const [status, managed, ollama] = await Promise.all([getH3RuntimeStatus(managedBaseUrl, profileId), window.electronAPI.getComfyRuntimeStatus(), window.electronAPI.getOllamaRuntimeStatus()])
        if (!active) return
        setRuntimeStatus(status.status)
        setRuntimeVersion(status.comfyui_version)
        setRuntimeError(status.errors[0] ?? null)
        setLifecycle(managed)
        setOllamaLifecycle(ollama)
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
  }, [managedBaseUrl, project?.workflow_profile_id])

  useEffect(() => {
    if (!runtimeConfig) return
    void getOllamaStatus(ollamaEndpoint, runtimeConfig.ollamaModel).then(setOllamaStatus).catch(() => setOllamaStatus(null))
  }, [runtimeConfig?.ollamaModel])

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
      const next = await createH3Project(newProjectName.trim(), count, newProjectSequenceMode)
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

  const applyContinuePrevious = async () => {
    if (!project) return
    const ordered = [...project.scenes].sort((a, b) => a.order - b.order)
    try {
      for (const target of ordered.slice(1)) {
        await updateH3Scene(project.id, target.id, { mode: 'continue_previous' })
      }
      replaceProject(await getH3Project(project.id))
      setWorkspaceError(null)
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : 'Continue Previous could not be applied to every later scene.')
    }
  }

  const renderScene = async () => {
    if (!project || !scene || !scene.prompt.trim() || runtimeStatus !== 'connected') return
    setRendering(true)
    setWorkspaceError(null)
    try {
      await flushPendingSave()
      const saved = await updateH3Scene(project.id, scene.id, {
        prompt: scene.prompt, reference_image: scene.reference_image, reference_fit: scene.reference_fit, aspect_ratio: scene.aspect_ratio, resolution_megapixels: scene.resolution_megapixels, seed: scene.seed,
        width: scene.width, height: scene.height, fps: scene.fps,
        duration_seconds: scene.duration_seconds, frame_count: scene.frame_count,
      })
      replaceProject({ ...saved, scenes: saved.scenes.map(item => item.id === scene.id ? { ...item, status: 'queued', current_phase: 'Waiting' } : item) })
      const run = await startH3Sequence(project.id, 'scene', scene.id, managedBaseUrl)
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
      const run = await startH3Sequence(project.id, kind, kind === 'from_here' ? scene.id : undefined, managedBaseUrl)
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
  const activeUpscaleVariant = activeVersion?.upscale_variants.find(item => item.id === selectedUpscaleVariantId) ?? null
  const promptOnly = project?.workflow_profile_id === 'minimax_h3_no_reference'
  const miniMaxH3 = selectedWorkflowProfile?.displayName === 'MiniMax H3'
  const miniMaxH3ModeOptions = [
    { value: 'image_to_video' as H3WorkflowMode, label: 'Image to Video' },
    { value: 'text_to_video' as H3WorkflowMode, label: 'Prompt Only' },
  ]
  const activeMedia = activeUpscaleVariant ?? activeVersion
  const previewUrl = activeMedia
    ? pathToFileUrl(activeMedia.video_file)
    : !promptOnly && scene?.reference_image ? pathToFileUrl(scene.reference_image) : null
  useEffect(() => {
    previewVideoRef.current?.pause()
  }, [project?.id, scene?.id, activeVersion?.id, activeUpscaleVariant?.id])
  useEffect(() => () => previewVideoRef.current?.pause(), [])
  const sourceScene = scene && project ? [...project.scenes].sort((a, b) => a.order - b.order)[scene.order - 2] ?? null : null
  const sourceVersion = sourceScene?.render_versions.find(item => item.id === sourceScene.selected_render_version_id) ?? null
  const selectedContinuityArtifact = scene?.continuity_artifacts.find(item => item.id === scene.selected_continuity_artifact_id) ?? null
  const continuityArtifact = selectedContinuityArtifact
    && selectedContinuityArtifact.source_scene_id === sourceScene?.id
    && selectedContinuityArtifact.source_render_version_id === sourceVersion?.id
    && selectedContinuityArtifact.strategy === scene?.continuity_strategy
    && selectedContinuityArtifact.offset_from_end_frames === (scene?.continuity_strategy === 'offset_from_end' ? scene.continuity_offset_frames : 0)
    ? selectedContinuityArtifact : null
  const modeHasInput = promptOnly ? scene?.mode === 'new_shot' : scene?.mode === 'continue_previous' ? Boolean(sourceVersion) : scene?.mode === 'new_shot' ? Boolean(scene.reference_image) : false
  const canRender = Boolean(project && selectedWorkflowProfile?.status === 'verified' && scene?.prompt.trim() && modeHasInput && lifecycle?.state === 'ready' && !rendering && !preparingContinuity)
  const phaseActive = scene ? ACTIVE_STATUSES.includes(scene.status) : false
  const activeVersionIndex = scene?.render_versions.findIndex(version => version.id === scene.selected_render_version_id) ?? -1
  const finalPrompt = scene ? composeH3AudioPrompt(scene) : ''
  const saveRenderCopy = async () => {
    if (!project || !scene || !activeMedia || !activeVersion) return
    setFileActionMessage(null)
    const date = new Date().toISOString().slice(0, 10)
    const suffix = activeUpscaleVariant ? '_RTX-VSR-2x' : ''
    const defaultName = `${project.name.replace(/[<>:"/\\|?*]/g, '-').trim() || 'H3-Project'}_Scene${String(scene.order).padStart(2, '0')}_v${String(activeVersion.number).padStart(3, '0')}${suffix}_${date}.mp4`
    const result = await window.electronAPI.saveH3RenderCopy({ projectRoot: project.project_root, videoFile: activeMedia.video_file, defaultName })
    setFileActionMessage(result.success ? `Saved copy: ${result.path}` : result.error || 'Save copy failed.')
  }
  const revealRender = async () => {
    if (!project || !activeMedia) return
    const result = await window.electronAPI.revealH3Render({ projectRoot: project.project_root, videoFile: activeMedia.video_file })
    setFileActionMessage(result.success ? 'Opened render in Explorer.' : result.error || 'Could not show the render.')
  }
  const openProjectFolder = async () => {
    if (!project) return
    const result = await window.electronAPI.openH3ProjectFolder({ projectRoot: project.project_root })
    setFileActionMessage(result.success ? 'Opened project folder.' : result.error || 'Could not open the project folder.')
  }
  const selectVersionAt = (index: number) => {
    if (!project || !scene || index < 0 || index >= scene.render_versions.length) return
    setSelectedUpscaleVariantId(null)
    void updateH3Scene(project.id, scene.id, { selected_render_version_id: scene.render_versions[index].id }).then(replaceProject)
  }
  const updateDuration = (value: string) => {
    const duration = Number(value)
    if (!scene || !Number.isFinite(duration) || duration <= 0) return
    updateSceneLocally({ duration_seconds: duration, frame_count: frameCountForWorkflow(project?.workflow_profile_id, duration, scene.fps) })
  }
  const updateAspectRatio = (aspectRatio: H3AspectRatio) => {
    const [width, height] = H3_RESOLUTION_PRESETS[aspectRatio][scene?.resolution_megapixels ?? 0.4]
    updateSceneLocally({ aspect_ratio: aspectRatio, width, height })
  }
  const updateResolution = (resolutionMegapixels: H3ResolutionMegapixels) => {
    if (!scene) return
    const [width, height] = H3_RESOLUTION_PRESETS[scene.aspect_ratio][resolutionMegapixels]
    updateSceneLocally({ resolution_megapixels: resolutionMegapixels, width, height })
  }
  const improvePrompt = async () => {
    if (!scene || !project || promptAssistantBusy) return
    setPromptAssistantBusy(true); setPromptAssistantMessage('Improving prompt…')
    const context = {
      rawPrompt: scene.prompt,
      sceneNumber: scene.order, sceneName: scene.name, projectName: project.name, sequenceMode: project.sequence_mode,
      previousSceneNumber: sourceScene?.order, previousSceneName: sourceScene?.name,
      previousScenePrompt: sourceScene?.prompt,
      previousFinalPrompt: sourceVersion?.final_prompt ?? undefined,
      mode: scene.mode,
      continuitySourceVersionId: sourceVersion?.id,
      aspectRatio: scene.aspect_ratio,
      width: scene.width,
      height: scene.height,
      durationSeconds: scene.duration_seconds,
      fps: scene.fps,
      audioMode: scene.audio_mode,
      noSpeech: scene.no_speech,
      noMusic: scene.no_music,
      customAudioInstruction: scene.custom_audio_instruction,
      continuityFramePath: continuityArtifact?.image_file,
      referenceImagePath: scene.reference_image ?? undefined,
    }
    try {
      const canUseOllama = Boolean(runtimeConfig?.ollamaModel && ollamaStatus?.status === 'ready' && ollamaStatus.selected_model_available)
      const result = await (canUseOllama ? new OllamaH3PromptAssistant(ollamaEndpoint, runtimeConfig!.ollamaModel!) : localPromptAssistant).improve(context)
      setPromptAssistantMessage(result.provider === 'ollama' ? `${result.message} Vision context: ${result.visionContext === 'used' ? 'Used' : 'Not available'}.` : result.message)
      setPromptSuggestion(result.suggestion)
    } catch (error) {
      setPromptAssistantMessage(`${error instanceof Error ? error.message : 'Local Ollama failed.'} Basic local suggestion is available.`)
      setPromptSuggestion((await localPromptAssistant.improve(context)).suggestion)
    } finally { setPromptAssistantBusy(false) }
  }

  return <div className="h3-director-ui h-screen overflow-hidden bg-[#07090d] text-zinc-100">
    <div className="grid h-full grid-cols-[250px_minmax(0,1fr)_360px] grid-rows-[minmax(0,1fr)_150px]">
      <aside className="row-span-2 flex min-h-0 flex-col border-r border-white/10 bg-[#0a0d12]">
        <div className="border-b border-white/10 px-5 py-5"><div className="flex items-center gap-3">
          <div aria-label="H3D" className="flex h-10 w-10 items-center justify-center rounded-xl border border-amber-300/60 bg-[#11151c] text-xs font-black tracking-tight text-amber-200">H3D</div>
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
        </div><div className="flex items-center gap-3"><button onClick={() => void openProjectFolder()} disabled={!project} className="rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-zinc-300 disabled:opacity-30"><Folder className="mr-2 inline h-3.5 w-3.5" />Open Project Folder</button><button onClick={() => openInEditor(false)} disabled={!project || !project.scenes.some(item => item.selected_render_version_id)} className="rounded-lg border border-white/10 px-4 py-2 text-xs font-medium text-zinc-300 disabled:opacity-30"><Film className="mr-2 inline h-3.5 w-3.5" />Open in Editor</button>{editorUpdates.length > 0 && <button onClick={() => openInEditor(true)} className="rounded-lg border border-amber-300/30 px-3 py-2 text-xs text-amber-200">Update {editorUpdates.length} selected version{editorUpdates.length === 1 ? '' : 's'}</button>}<div className="text-right"><StatusPill status={runtimeStatus} />{runtimeVersion && <div className="mt-1 text-[10px] text-zinc-600">ComfyUI {runtimeVersion}</div>}</div></div></header>
        <section className="relative flex h-[calc(100%-64px)] min-h-[360px] items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
          {previewUrl ? activeVersion ? <video ref={previewVideoRef} key={previewUrl} src={previewUrl} controls preload="metadata" className="h-full w-full object-contain" /> : <img src={previewUrl} alt="Selected scene reference" className="h-full w-full object-contain opacity-90" /> : <div className="max-w-sm text-center"><Film className="mx-auto h-10 w-10 text-zinc-700" /><h2 className="mt-5 text-lg text-zinc-300">Your selected render will appear here</h2><p className="mt-2 text-sm text-zinc-600">{promptOnly ? 'Add a prompt to begin.' : 'Create a project and save the scene reference to begin.'}</p></div>}
          <div className="absolute left-4 top-4 rounded-full border border-white/10 bg-black/60 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-zinc-400">Scene preview</div>
          {scene && <div className={`absolute bottom-4 right-4 rounded-full px-3 py-1.5 text-xs font-semibold ${scene.status === 'failed' ? 'bg-red-400/90 text-red-950' : scene.status === 'complete' ? 'bg-emerald-400/90 text-emerald-950' : 'bg-amber-300/90 text-amber-950'}`}>{STATUS_LABELS[scene.status]}</div>}
        </section>
      </main>

      <aside className="row-span-2 min-h-0 overflow-y-auto border-l border-white/10 bg-[#0b0e13] p-5">
        <div className="flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-amber-300" /> Director controls</div>{scene && <span className="text-[10px] uppercase tracking-wider text-zinc-600">{STATUS_LABELS[scene.status]}</span>}</div>
        <label className="mt-6 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene name<input value={scene?.name ?? ''} disabled={!scene} onChange={event => updateSceneLocally({ name: event.target.value })} className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2.5 text-sm normal-case tracking-normal outline-none focus:border-amber-300/40" /></label>
        <div className="mt-5"><div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500"><span>Scene prompt</span><button type="button" onClick={() => void improvePrompt()} disabled={!scene?.prompt.trim()} className="rounded border border-amber-300/25 px-2 py-1 text-[10px] text-amber-200 disabled:opacity-30">Improve Prompt</button></div><textarea value={scene?.prompt ?? ''} disabled={!scene} onChange={event => { setPromptSuggestion(null); updateSceneLocally({ prompt: event.target.value }) }} className="mt-2 h-32 w-full resize-none rounded-xl border border-white/10 bg-black/30 p-3 text-sm normal-case leading-6 tracking-normal outline-none focus:border-amber-300/40" placeholder="Describe the shot, movement, lighting and mood…" />{promptAssistantMessage && <p className="mt-2 text-[10px] text-zinc-500">{promptAssistantMessage}</p>}{promptSuggestion && <div className="mt-2 rounded-lg border border-amber-300/20 bg-amber-300/[0.04] p-3 text-xs"><div className="text-zinc-500">Original</div><p className="mt-1 whitespace-pre-wrap text-zinc-300">{scene?.prompt}</p><div className="mt-3 text-zinc-500">Suggested</div><textarea value={promptSuggestion} onChange={event => setPromptSuggestion(event.target.value)} className="mt-1 h-28 w-full resize-y rounded border border-white/10 bg-black/30 p-2 text-xs text-zinc-200 outline-none" /><div className="mt-2 flex gap-2"><button type="button" onClick={() => { updateSceneLocally({ prompt: promptSuggestion }); setPromptSuggestion(null) }} className="rounded border border-emerald-400/25 px-2 py-1 text-[10px] text-emerald-200">Accept</button><button type="button" onClick={() => setPromptSuggestion(null)} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-300">Cancel / Edit</button></div></div>}</div>
        {scene && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Audio guidance</div><label className="mt-2 block text-[10px] uppercase tracking-wider text-zinc-600">Audio mode<select value={scene.audio_mode} onChange={event => updateSceneLocally({ audio_mode: event.target.value as H3Scene['audio_mode'] })} className="mt-1 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-xs normal-case tracking-normal text-zinc-200"><option value="natural_ambience">Natural ambience</option><option value="dialogue">Dialogue</option><option value="silent">Silent</option></select></label><div className="mt-3 flex gap-4 text-xs text-zinc-300"><label className="flex items-center gap-2"><input type="checkbox" checked={scene.no_speech} disabled={scene.audio_mode === 'silent'} onChange={event => updateSceneLocally({ no_speech: event.target.checked })} />No speech</label><label className="flex items-center gap-2"><input type="checkbox" checked={scene.no_music} disabled={scene.audio_mode === 'silent'} onChange={event => updateSceneLocally({ no_music: event.target.checked })} />No music</label></div><label className="mt-3 block text-[10px] uppercase tracking-wider text-zinc-600">Custom audio instruction<input value={scene.custom_audio_instruction} disabled={scene.audio_mode === 'silent'} onChange={event => updateSceneLocally({ custom_audio_instruction: event.target.value })} placeholder="e.g. footsteps in snow and light winter wind" className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-xs normal-case tracking-normal text-zinc-200" /></label><div className="mt-3 text-[10px] text-zinc-500">Audio: {h3AudioSummary(scene)}</div><details className="mt-2 text-[10px] text-zinc-500"><summary className="cursor-pointer">View final prompt</summary><p className="mt-2 whitespace-pre-wrap leading-5 text-zinc-300">{finalPrompt || 'Add a scene prompt to preview the final prompt.'}</p></details></div>}
        <label style={{ display: selectedWorkflowProfile?.id === 'ltx_2_5_image_to_video' || promptOnly ? 'none' : undefined }} className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene Mode<select value={scene?.mode ?? 'new_shot'} disabled={!scene} onChange={event => updateSceneLocally({ mode: event.target.value as H3Scene['mode'] })} className="mt-2 w-full rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm normal-case tracking-normal text-zinc-300"><option value="new_shot">New Shot</option><option value="continue_previous">Continue Previous</option><option value="same_character_new_shot">Same Character, New Shot — unavailable</option></select></label>
        {promptOnly && <p className="mt-5 rounded-lg border border-amber-300/20 bg-amber-300/[0.035] p-3 text-xs text-amber-100">Prompt Only generates an independent new shot. Image-based Continue Previous is available only in Image to Video.</p>}
        <label style={{ display: selectedWorkflowProfile?.id === 'ltx_2_5_image_to_video' || promptOnly ? 'none' : undefined }} className="mt-4 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Reference fit<select value={scene?.reference_fit ?? 'fill_crop'} disabled={!scene} onChange={event => updateSceneLocally({ reference_fit: event.target.value as H3Scene['reference_fit'] })} className="mt-2 w-full rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm normal-case tracking-normal text-zinc-300"><option value="fill_crop">Fill / Crop</option><option value="fit">Fit</option><option value="stretch">Stretch (may distort)</option></select><span className="mt-1 block normal-case tracking-normal text-[10px] text-zinc-600">The original image is never changed; H3 stages an exact-size render copy.</span></label>
        {project && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><label className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Sequence mode<select value={project.sequence_mode ?? 'independent_shots'} onChange={event => void updateH3Project(project.id, { sequence_mode: event.target.value as H3SequenceMode }).then(replaceProject).catch(error => setWorkspaceError(error instanceof Error ? error.message : 'Sequence mode could not be saved.'))} className="mt-2 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-xs normal-case tracking-normal text-zinc-300"><option value="independent_shots">Independent shots</option><option value="continuous_sequence">Continuous sequence</option></select></label><button onClick={() => void applyContinuePrevious()} disabled={project.scenes.length < 2} className="mt-3 w-full rounded-lg border border-amber-300/20 px-2 py-2 text-xs text-amber-200 disabled:opacity-30">Apply Continue Previous to remaining scenes</button></div>}
        {runtimeConfig && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="flex items-center justify-between"><span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Sage Attention</span><label className="flex items-center gap-2 text-xs text-zinc-300"><input type="checkbox" checked={Boolean(runtimeConfig.sageAttention)} onChange={event => setRuntimeConfig({ ...runtimeConfig, sageAttention: event.target.checked })} />{runtimeConfig.sageAttention ? 'On' : 'Off'}</label></div><p className="mt-2 text-[10px] text-zinc-600">{lifecycle?.state === 'ready' ? `Effective: ${runtimeConfig.sageAttention ? 'On' : 'Off'} after Restart required.` : 'Saved setting applies when the managed backend starts.'}</p></div>}
        {scene && <details className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><summary className="cursor-pointer font-semibold text-zinc-300">Scene Details</summary><dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px] text-zinc-500"><dt>Scene</dt><dd className="text-right text-zinc-300">{String(scene.order).padStart(2, '0')} · {scene.name}</dd><dt>Mode</dt><dd className="text-right text-zinc-300">{scene.mode}</dd><dt>Output</dt><dd className="text-right text-zinc-300">{scene.width}×{scene.height} · {scene.fps} FPS</dd><dt>Duration / frames</dt><dd className="text-right text-zinc-300">{scene.duration_seconds}s · {scene.frame_count}</dd><dt>Seed / fit</dt><dd className="text-right text-zinc-300">{scene.seed} · {scene.reference_fit}</dd><dt>Render status</dt><dd className="text-right text-zinc-300">{STATUS_LABELS[scene.status]}</dd>{activeVersion && <><dt>Selected version</dt><dd className="text-right text-zinc-300">v{String(activeVersion.number).padStart(3, '0')}</dd><dt>Last render</dt><dd className="text-right text-zinc-300">{activeVersion.duration_seconds.toFixed(1)}s</dd><dt>Prompt ID</dt><dd className="truncate text-right text-zinc-300">{activeVersion.prompt_id}</dd></>}{selectedContinuityArtifact && <><dt>Continuity source</dt><dd className="truncate text-right text-zinc-300">{selectedContinuityArtifact.source_scene_id}</dd><dt>Source version</dt><dd className="truncate text-right text-zinc-300">{selectedContinuityArtifact.source_render_version_id}</dd></>}</dl></details>}
        {scene?.mode === 'same_character_new_shot' && <p className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/70">Unavailable: the verified MiniMax H3 workflow has one image input and no separate character-reference control.</p>}
        {scene?.mode === 'continue_previous' && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Continuity source</div><div className="mt-2 text-xs text-zinc-300">{sourceScene ? `${sourceScene.name} · ${sourceVersion?.id ?? 'no selected completed version'}` : 'Blocked · no previous scene'}</div><label className="mt-3 block text-[10px] uppercase tracking-wider text-zinc-600">Extraction strategy<select value={scene.continuity_strategy} onChange={event => updateSceneLocally({ continuity_strategy: event.target.value as H3Scene['continuity_strategy'] })} className="mt-1 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-xs normal-case tracking-normal text-zinc-300"><option value="last_valid_frame">Last valid frame</option><option value="offset_from_end">Offset from end</option></select></label>{scene.continuity_strategy === 'offset_from_end' && <label className="mt-3 block text-[10px] uppercase tracking-wider text-zinc-600">Offset from end · frames<input type="number" min="0" value={scene.continuity_offset_frames} onChange={event => updateSceneLocally({ continuity_offset_frames: Math.max(0, Number(event.target.value)) })} className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 font-mono text-xs text-zinc-300" /></label>}{continuityArtifact && <div className="mt-3 flex gap-3"><img src={pathToFileUrl(continuityArtifact.image_file)} alt="Extracted continuity frame" className="h-16 w-24 rounded-lg bg-black object-cover" /><div className="text-[10px] leading-5 text-zinc-500">{continuityArtifact.id}<br />Frame {continuityArtifact.frame_index} · {continuityArtifact.timestamp_seconds.toFixed(3)}s<br />Source {continuityArtifact.source_render_version_id}</div></div>}<button onClick={() => void prepareContinuity()} disabled={!sourceVersion || preparingContinuity} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-amber-300/20 px-3 py-2 text-xs text-amber-200 disabled:opacity-30">{preparingContinuity && <Loader2 className="h-3 w-3 animate-spin" />} Extract Continuity Frame</button>{!sourceVersion && <p className="mt-2 text-[10px] text-red-300">Rendering is blocked until the previous scene has a selected completed render.</p>}</div>}
        {!promptOnly && <label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Reference image<button onClick={() => void chooseReferenceImage()} disabled={!scene} className="mt-2 flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.025] px-3 py-3 text-sm normal-case tracking-normal text-zinc-400"><span className="truncate">{scene?.reference_image?.split(/[\\/]/).pop() ?? 'Choose image'}</span><ImagePlus className="h-4 w-4" /></button></label>}
        {scene && <div className="mt-5 grid grid-cols-2 gap-3"><label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Duration (seconds)</div><input type="number" min="0.1" step="0.1" value={scene.duration_seconds} onChange={event => updateDuration(event.target.value)} className="mt-1 w-full bg-transparent font-mono text-sm text-zinc-300 outline-none" /></label><div className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Frames (calculated)</div><div className="mt-1 font-mono text-sm text-zinc-300">{scene.frame_count}</div><div className="mt-1 text-[9px] text-zinc-600">MiniMax H3 17k+5 grid</div></div></div>}
        <div className="mt-6 grid grid-cols-2 gap-3">{scene && <><label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Format</div><H3ThemedSelect value={scene.aspect_ratio} ariaLabel="Format" onChange={updateAspectRatio} options={profileAspectRatios.map(ratio => ({ value: ratio, label: ratio.startsWith('1:1') ? '1:1' : ratio.startsWith('16:9') ? '16:9' : '9:16' }))} /></label><label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Resolution</div><H3ThemedSelect value={scene.resolution_megapixels} ariaLabel="Resolution" onChange={updateResolution} options={profileResolutionMegapixels.map(megapixels => { const [width, height] = H3_RESOLUTION_PRESETS[scene.aspect_ratio][megapixels]; return { value: megapixels, label: `${width}×${height}` } })} /><div className="mt-1 text-[9px] text-zinc-600">{scene.resolution_megapixels.toFixed(1)} MP · derived from format</div></label><div className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">FPS</div><div className="mt-1 font-mono text-sm text-zinc-300">{scene.fps}</div><div className="mt-1 text-[9px] text-zinc-600">Fixed workflow value</div></div></>}
          <label className="rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Seed</div><input type="number" disabled={!scene} value={scene?.seed ?? 0} onChange={event => updateSceneLocally({ seed: Number(event.target.value) })} className="mt-1 w-full bg-transparent font-mono text-sm text-zinc-300 outline-none" /></label>
        </div>
        {!!scene?.render_versions.length && <div className="mt-5"><div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Render version</div><div className="mt-2 flex gap-2"><button aria-label="Previous version" disabled={activeVersionIndex <= 0} onClick={() => selectVersionAt(activeVersionIndex - 1)} className="rounded-lg border border-white/10 px-2 disabled:opacity-25"><ChevronLeft className="h-4 w-4" /></button><select value={scene.selected_render_version_id ?? ''} onChange={event => { setSelectedUpscaleVariantId(null); void updateH3Scene(project!.id, scene.id, { selected_render_version_id: event.target.value }).then(replaceProject) }} className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#11151c] px-3 py-3 text-sm text-zinc-300">{scene.render_versions.map(version => <option key={version.id} value={version.id}>v{String(version.number).padStart(3, '0')} · {new Date(version.created_at).toLocaleString()}</option>)}</select><button aria-label="Next version" disabled={activeVersionIndex < 0 || activeVersionIndex >= scene.render_versions.length - 1} onClick={() => selectVersionAt(activeVersionIndex + 1)} className="rounded-lg border border-white/10 px-2 disabled:opacity-25"><ChevronRight className="h-4 w-4" /></button></div>{activeVersion && <div className="mt-2 rounded-lg bg-white/[0.025] p-2 text-[10px] leading-5 text-zinc-500"><div className="font-medium text-zinc-200">{activeUpscaleVariant ? 'RTX VSR 2× derived version' : 'Original render'}</div><div>{activeMedia?.width}×{activeMedia?.height} · {activeMedia?.duration_seconds}s · {activeMedia?.fps} FPS</div>{!activeUpscaleVariant && <div>Seed {activeVersion.seed} · Prompt ID {activeVersion.prompt_id}</div>}{activeVersion.upscale_variants.length > 0 && <div className="mt-2 rounded border border-emerald-400/15 bg-emerald-400/[0.04] p-2"><div className="text-emerald-200">RTX VSR 2× derived versions</div><div className="mt-1 flex flex-wrap gap-1"><button onClick={() => setSelectedUpscaleVariantId(null)} className={`rounded border px-2 py-1 ${!activeUpscaleVariant ? 'border-zinc-300/40 text-zinc-100' : 'border-white/10 text-zinc-400'}`}>Original</button>{activeVersion.upscale_variants.map(variant => <button key={variant.id} onClick={() => setSelectedUpscaleVariantId(variant.id)} className={`rounded border px-2 py-1 ${activeUpscaleVariant?.id === variant.id ? 'border-emerald-300/50 text-emerald-100' : 'border-white/10 text-zinc-400'}`}>RTX VSR 2× · v{String(variant.number).padStart(3, '0')}</button>)}</div></div>}<div className="mt-2 flex flex-wrap gap-2"><button onClick={() => setSelectedUpscaleVariantId(activeUpscaleVariant?.id ?? null)} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-200">Preview</button><button onClick={() => void saveRenderCopy()} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-200">Save Copy…</button><button onClick={() => void revealRender()} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-200">Show in Folder</button><button onClick={() => openActiveMediaInEditor()} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-200">Open in Editor</button>{!activeUpscaleVariant && <button disabled={!upscaleAvailability.available || upscaling} onClick={() => void upscaleActiveVersion()} className="rounded border border-amber-300/25 px-2 py-1 text-[10px] text-amber-200 disabled:opacity-40">{upscaling ? 'Upscaling…' : activeVersion.upscale_variants.some(variant => variant.backend === 'nvidia_rtx_vsr' && variant.scale === 2) ? 'Show RTX VSR 2×' : 'Upscale Video 2×'}</button>}</div><p className={`mt-2 text-[9px] ${upscaleAvailability.available ? 'text-emerald-200/80' : 'text-amber-200/80'}`}>RTX VSR: {activeUpscaleVariant ? 'Viewing immutable derived output. Original remains available.' : upscaleAvailability.available ? `${createUpscaleVariantPlan(activeVersion).sourceResolution} → ${createUpscaleVariantPlan(activeVersion).outputResolution}. Original preserved.` : upscaleAvailability.reason}</p></div>}</div>}
        {runtimeConfig && <details className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><summary className="cursor-pointer font-semibold text-zinc-300">Prompt Assistant · Local Ollama</summary><p className={`mt-2 text-[10px] ${ollamaStatus?.status === 'ready' ? 'text-emerald-300' : 'text-amber-200'}`}>{ollamaStatus?.status === 'ready' && ollamaStatus.selected_model_available ? 'Local Ollama · Ready' : ollamaStatus?.status === 'model_not_installed' ? 'Model not installed' : 'Local Ollama · Not running'}</p><input value={runtimeConfig.ollamaEndpoint ?? 'http://127.0.0.1:11434'} onChange={event => setRuntimeConfig({ ...runtimeConfig, ollamaEndpoint: event.target.value })} placeholder="Local Ollama endpoint" className="mt-2 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><label className="mt-2 block text-[10px] text-zinc-500">Installed model<select value={runtimeConfig.ollamaModel ?? ''} onChange={event => setRuntimeConfig({ ...runtimeConfig, ollamaModel: event.target.value || undefined })} className="mt-1 w-full rounded border border-white/10 bg-[#11151c] px-2 py-1.5 text-xs text-zinc-200"><option value="">Choose local model</option>{ollamaStatus?.models.map(model => <option key={model.name} value={model.name}>{model.name}{model.vision_capable ? ' · vision' : ''}</option>)}</select></label><button type="button" onClick={() => void getOllamaStatus(runtimeConfig.ollamaEndpoint || 'http://127.0.0.1:11434', runtimeConfig.ollamaModel).then(setOllamaStatus).catch(() => setOllamaStatus(null))} className="mt-2 rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-300">Refresh models</button><p className="mt-2 text-[10px] text-zinc-500">Local only. No prompts, images, or project data leave this device.</p></details>}
        {runtimeConfig && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><div className="font-semibold text-zinc-300">Prompt Assistant</div><div className={`mt-1 text-[10px] ${ollamaLifecycle?.state === 'ready' ? 'text-emerald-300' : 'text-amber-200'}`}>{ollamaLifecycle?.state === 'ready' ? 'Ready · Local Ollama' : ollamaLifecycle?.state === 'starting' ? 'Starting…' : ollamaLifecycle?.state === 'not_installed' ? 'Not installed' : ollamaLifecycle?.state === 'failed' ? 'Failed' : 'Not running'}</div><div className="mt-1 text-[10px] text-zinc-500">{ollamaLifecycle?.state === 'ready' ? `${ollamaLifecycle.owned ? 'H3 managed' : 'External'} · Model: ${runtimeConfig.ollamaModel ?? 'none selected'}` : 'Local-only prompt suggestions remain available.'}</div>{ollamaLifecycle?.error && <p className="mt-2 text-[10px] text-red-300">{ollamaLifecycle.error}</p>}<details className="mt-3 border-t border-white/10 pt-3"><summary className="cursor-pointer text-[10px] font-semibold text-zinc-400">Advanced Prompt Assistant settings</summary><div className="mt-3 grid gap-2"><label className="flex items-center gap-2 text-[10px] text-zinc-400"><input type="checkbox" checked={Boolean(runtimeConfig.ollamaAutoStart)} onChange={event => setRuntimeConfig({ ...runtimeConfig, ollamaAutoStart: event.target.checked })} />Auto-start Ollama</label><div className="text-[10px] text-zinc-500">Endpoint: 127.0.0.1:11434 (loopback only)</div><div className="grid grid-cols-3 gap-2"><button onClick={() => void window.electronAPI.startOllamaRuntime().then(setOllamaLifecycle)} disabled={ollamaLifecycle?.state === 'starting' || ollamaLifecycle?.state === 'ready'} className="rounded border border-emerald-400/20 px-2 py-1.5 text-[10px] text-emerald-200 disabled:opacity-30">Start</button><button onClick={() => void window.electronAPI.stopOllamaRuntime().then(setOllamaLifecycle)} disabled={!ollamaLifecycle?.owned} className="rounded border border-red-400/20 px-2 py-1.5 text-[10px] text-red-200 disabled:opacity-30">Stop</button><button onClick={() => void window.electronAPI.restartOllamaRuntime().then(setOllamaLifecycle)} disabled={!ollamaLifecycle?.owned} className="rounded border border-amber-400/20 px-2 py-1.5 text-[10px] text-amber-200 disabled:opacity-30">Restart</button></div><button onClick={() => void saveRuntimeSettings()} className="rounded border border-white/10 px-2 py-1.5 text-[10px] text-zinc-300">Save Prompt Assistant settings</button>{ollamaLifecycle?.diagnostics.length ? <details className="font-mono text-[9px] text-zinc-500"><summary>Diagnostics</summary>{ollamaLifecycle.diagnostics.join('\n')}</details> : null}</div></details></div>}
        <details className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><summary className="cursor-pointer font-semibold text-zinc-300">Models</summary>{H3_WORKFLOW_PROFILES.filter(profile => profile.status === 'verified').map(profile => <div key={profile.id} className="mt-3"><div className="flex justify-between"><span>{profile.displayName}</span><span className="text-emerald-300">Verified at runtime</span></div><div className="mt-1 text-[10px] text-zinc-500">{profile.requiredModels.length} declared local model files.</div></div>)}<div className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/[0.035] p-3"><div className="flex justify-between gap-2"><span className="font-semibold text-amber-100">LTX 2.5</span><span className="text-[10px] text-amber-200">Access required</span></div><p className="mt-2 text-[10px] leading-4 text-zinc-400">Official weights require Hugging Face approval and acceptance of Lightricks model terms. H3 Director does not bypass gated access and does not bundle model files.</p><div className="mt-3 flex flex-wrap gap-2"><button onClick={() => void window.electronAPI.openExternalUrl({ url: LTX_2_5_OFFICIAL_MODEL_PAGE })} className="rounded border border-amber-300/30 px-2 py-1 text-[10px] text-amber-100">Open Official Model Page</button><button onClick={() => void importLtx25Models()} disabled={ltx25Importing} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-200 disabled:opacity-40">{ltx25Importing ? 'Importing…' : 'Import Downloaded Models…'}</button><button onClick={() => void refreshLtx25Models().catch(error => setWorkspaceError(error instanceof Error ? error.message : 'LTX 2.5 readiness could not be checked.'))} disabled={!runtimeConfig?.extraModelPathsConfig || ltx25Importing} className="rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-300 disabled:opacity-40">Refresh readiness</button></div><p className="mt-3 text-[10px] text-zinc-500">LTX-2.x Community License applies. Filename/layout validation only; no official checksum is currently available.</p>{ltx25Models && <div className="mt-3 space-y-1 text-[10px]">{ltx25Models.assets.map(asset => <div key={`${asset.filename}-${asset.destination_category ?? 'unknown'}`} className="flex gap-2"><span className={asset.state === 'found' ? 'text-emerald-300' : asset.state === 'missing' ? 'text-amber-200' : 'text-red-300'}>{asset.state === 'found' ? 'Found' : asset.state === 'missing' ? 'Missing' : asset.state}</span><span className="min-w-0 truncate text-zinc-400">{asset.filename}{asset.destination_category ? ` → ${asset.destination_category}` : ''}</span></div>)}<p className="pt-1 text-zinc-600">Models: {ltx25Models.assets.filter(asset => asset.required && asset.state === 'found').length}/{ltx25Models.assets.filter(asset => asset.required).length} · Workflow: Not verified · Nodes: Not verified · 16 GB VRAM: Unverified</p><p className="text-amber-200">Overall: Not ready to render.</p></div>}</div></details>
        {project && <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Model</div><H3ThemedSelect value={miniMaxH3 ? 'minimax_h3_image_to_video' : project.workflow_profile_id} ariaLabel="Model profile" onChange={profileId => { const profile = workflowProfileRegistry.get(profileId as H3WorkflowProfileId); const mode = profile?.modes[0]?.id as H3WorkflowMode | undefined; if (!mode) return; void updateH3Project(project.id, { workflow_profile_id: profileId as H3WorkflowProfileId, workflow_mode: mode }).then(async next => { if (profileId === 'ltx_2_5_image_to_video' && scene) return updateH3Scene(next.id, scene.id, { aspect_ratio: '16:9 (Widescreen)', resolution_megapixels: 0.9, width: 1280, height: 704, fps: 24, frame_count: 121, ltx_prompt_enhance: true }); return next }).then(replaceProject).catch(error => setWorkspaceError(error instanceof Error ? error.message : 'Model profile could not be saved.')) }} options={workflowProfileRegistry.list().filter(profile => (profile.status === 'verified' || profile.status === 'runtime_verified') && profile.id !== 'minimax_h3_no_reference').map(profile => ({ value: profile.id, label: profile.displayName }))} /><div className="mt-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Mode</div><H3ThemedSelect value={project.workflow_mode} ariaLabel="Workflow mode" onChange={mode => { const targetProfileId = miniMaxH3 ? (mode === 'text_to_video' ? 'minimax_h3_no_reference' : 'minimax_h3_image_to_video') : project.workflow_profile_id; void updateH3Project(project.id, { workflow_profile_id: targetProfileId, workflow_mode: mode as H3WorkflowMode }).then(async next => { if (targetProfileId === 'minimax_h3_no_reference' && scene) return updateH3Scene(next.id, scene.id, { mode: 'new_shot', aspect_ratio: '1:1 (Square)', resolution_megapixels: 0.4, width: 640, height: 640, fps: 24, duration_seconds: 5, frame_count: 124 }); return next }).then(replaceProject).catch(error => setWorkspaceError(error instanceof Error ? error.message : 'Workflow mode could not be saved.')) }} options={miniMaxH3 ? miniMaxH3ModeOptions : (selectedWorkflowProfile?.modes ?? []).filter(mode => mode.verified).map(mode => ({ value: mode.id, label: mode.label }))} />{selectedWorkflowMode && <p className="mt-2 text-[10px] text-zinc-500">{promptOnly ? "Generate without a reference image using MiniMax H3's optional image inputs. Enabled only for 1:1, 640×640, 24 FPS, 5 seconds and 124 frames." : selectedWorkflowMode.capabilities.imageToVideo ? 'Reference image required for new shots.' : 'This profile mode is not verified.'} {!promptOnly && 'Advanced workflow details remain hidden.'}</p>}</div>}
        {scene && selectedWorkflowProfile?.id === 'ltx_2_5_image_to_video' && <div className="mt-3 rounded-xl border border-indigo-300/20 bg-indigo-300/[0.035] p-3"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-indigo-200">Native LTX controls</div><label className="mt-2 flex items-center justify-between gap-3 text-xs text-zinc-200"><span>Prompt Enhance</span><input type="checkbox" checked={scene.ltx_prompt_enhance} onChange={event => updateSceneLocally({ ltx_prompt_enhance: event.target.checked })} /></label><p className="mt-2 text-[10px] leading-4 text-zinc-400">This uses the captured local LTX prompt-enhancement model, separately from H3 Director’s local Ollama Improve Prompt. The template decodes synchronized audio, but no separate audio-guidance input is mapped.</p><p className="mt-2 text-[10px] text-emerald-200">Enabled only for the verified I2V profile: 16:9 / 0.9 MP / 1280×704 output / 24 FPS / 5 seconds.</p></div>}
        <button onClick={() => void window.electronAPI.showOpenDirectoryDialog({ title: 'Install validated local workflow profile' }).then(async folder => { if (!folder) return; const installed = await installH3WorkflowProfile(folder); setFileActionMessage(`Installed profile ${installed.profile_id} v${installed.version}. Restart or refresh to use future verified modes.`) }).catch(error => setWorkspaceError(error instanceof Error ? error.message : 'Workflow profile installation failed.'))} className="mt-3 rounded border border-white/10 px-2 py-1 text-[10px] text-zinc-300">Install Workflow Profile…</button>
        {fileActionMessage && <p className="mt-3 text-[10px] text-zinc-400">{fileActionMessage}</p>}
        <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-xs"><div className="flex items-center justify-between"><div><div className="font-semibold text-zinc-300">Backend</div><div className="mt-1 text-[10px] text-zinc-500">{lifecycle?.state === 'ready' ? `Ready / ${lifecycle.owned ? 'H3 managed' : 'External'}` : lifecycle?.state.replace('_', ' ') ?? 'Checking'}{runtimeConfig ? ` / Sage: ${runtimeConfig.sageAttention ? 'On' : 'Off'}` : ''}</div></div><span className={`rounded-full px-2 py-1 text-[9px] uppercase ${lifecycle?.state === 'ready' ? 'bg-emerald-400/10 text-emerald-300' : lifecycle?.state === 'failed' || lifecycle?.state === 'incompatible' ? 'bg-red-400/10 text-red-300' : 'bg-amber-300/10 text-amber-200'}`}>{lifecycle?.state ?? 'checking'}</span></div>{(lifecycle?.error || (runtimeError && lifecycle?.state !== 'ready')) && <p className="mt-2 text-[10px] text-red-300">{lifecycle?.error ?? runtimeError}</p>}<details className="mt-3 border-t border-white/10 pt-3"><summary className="cursor-pointer text-[10px] font-semibold text-zinc-400">Advanced backend settings</summary>{runtimeConfig && <div className="mt-3 grid gap-2"><input value={runtimeConfig.rootPath} onChange={e => setRuntimeConfig({ ...runtimeConfig, rootPath: e.target.value })} placeholder="ComfyUI root" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><input value={runtimeConfig.pythonPath} onChange={e => setRuntimeConfig({ ...runtimeConfig, pythonPath: e.target.value })} placeholder="ComfyUI Python" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><label className="text-[10px] text-zinc-500">Port <input type="number" value={runtimeConfig.port} onChange={e => setRuntimeConfig({ ...runtimeConfig, port: Number(e.target.value) })} className="ml-2 w-16 rounded border border-white/10 bg-black/30 px-1 py-1 text-zinc-300" /></label><label className="flex items-center gap-2 text-[10px] text-zinc-500"><input type="checkbox" checked={runtimeConfig.autoLaunch} onChange={e => setRuntimeConfig({ ...runtimeConfig, autoLaunch: e.target.checked })} /> Auto-launch</label><input value={runtimeConfig.extraModelPathsConfig ?? ''} onChange={e => setRuntimeConfig({ ...runtimeConfig, extraModelPathsConfig: e.target.value })} placeholder="Extra model paths config" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><input value={runtimeConfig.inputDirectory ?? ''} onChange={e => setRuntimeConfig({ ...runtimeConfig, inputDirectory: e.target.value })} placeholder="ComfyUI input directory" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><input value={runtimeConfig.outputDirectory ?? ''} onChange={e => setRuntimeConfig({ ...runtimeConfig, outputDirectory: e.target.value })} placeholder="ComfyUI output directory" className="rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[10px]" /><label className="flex items-center gap-2 text-[10px] text-zinc-500"><input type="checkbox" checked={Boolean(runtimeConfig.sageAttention)} onChange={e => setRuntimeConfig({ ...runtimeConfig, sageAttention: e.target.checked })} /> Sage Attention {lifecycle?.state === 'ready' ? '(Restart required)' : ''}</label><div className="grid grid-cols-2 gap-2"><button disabled={saveState === 'saving'} onClick={() => void saveRuntimeSettings()} className="rounded border border-white/10 px-2 py-1.5 text-[10px] disabled:opacity-40">{saveState === 'saving' ? 'Saving...' : 'Save runtime settings'}</button><button disabled={lifecycle?.state === 'starting' || lifecycle?.state === 'checking'} onClick={() => void startManagedRuntime()} className="rounded border border-emerald-400/20 px-2 py-1.5 text-[10px] text-emerald-200 disabled:opacity-40">{lifecycle?.state === 'starting' ? 'Starting...' : lifecycle?.state === 'checking' ? 'Checking...' : 'Start'}</button><button disabled={!lifecycle?.owned} onClick={() => void window.electronAPI.stopComfyRuntime().then(setLifecycle)} className="rounded border border-red-400/20 px-2 py-1.5 text-[10px] text-red-200 disabled:opacity-30">Stop</button><button disabled={!lifecycle?.owned} onClick={() => void window.electronAPI.restartComfyRuntime().then(setLifecycle)} className="rounded border border-amber-400/20 px-2 py-1.5 text-[10px] text-amber-200 disabled:opacity-30">Restart</button></div>{lifecycle?.diagnostics.length ? <details className="text-[10px] text-zinc-500"><summary className="cursor-pointer">Diagnostics</summary><div className="mt-1 font-mono">{lifecycle.diagnostics.join('\n')}</div></details> : null}</div>}</details></div>
        {runtimeError && runtimeStatus !== 'connected' && lifecycle?.state !== 'ready' && <p className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/70">{runtimeError}</p>}
        {(workspaceError || scene?.last_error) && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300"><p>{workspaceError ?? scene?.last_error}</p>{scene?.diagnostics && <details className="mt-2 text-[10px] text-red-200/60"><summary className="cursor-pointer">Technical diagnostics</summary><div className="mt-1 font-mono">{scene.diagnostics}</div></details>}</div>}
        {activeRun?.kind === 'scene' ? <button onClick={() => void stopSequence(activeRun)} disabled={activeRun.stop_after_current_requested} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-red-400/40 bg-red-400/10 px-4 py-3.5 text-sm font-bold text-red-100 disabled:opacity-40"><Square className="h-4 w-4" />{activeRun.stop_after_current_requested ? 'Cancelling…' : 'Stop Render'}</button> : <button onClick={() => void renderScene()} disabled={!canRender || phaseActive || Boolean(activeRun)} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-300 to-orange-500 px-4 py-3.5 text-sm font-bold text-zinc-950 disabled:opacity-30">{rendering || phaseActive ? <Loader2 className="h-4 w-4 animate-spin" /> : scene?.status === 'failed' ? <RotateCcw className="h-4 w-4" /> : <Clapperboard className="h-4 w-4" />}{rendering || phaseActive ? STATUS_LABELS[scene?.status ?? 'queued'] : scene?.status === 'failed' ? 'Retry Render' : scene?.render_versions.length ? 'Render New Version' : 'Render Scene'}</button>}
        <div className="mt-3 grid grid-cols-2 gap-2"><button onClick={() => void startSequence('from_here')} disabled={!project || !scene || promptOnly || selectedWorkflowProfile?.status !== 'verified' || runtimeStatus !== 'connected' || Boolean(activeRun) || sequenceStarting} className="rounded-lg border border-amber-300/20 px-3 py-2.5 text-xs text-amber-200 disabled:opacity-30">Render From Here</button><button onClick={() => void startSequence('all')} disabled={!project || promptOnly || selectedWorkflowProfile?.status !== 'verified' || runtimeStatus !== 'connected' || Boolean(activeRun) || sequenceStarting} className="rounded-lg border border-amber-300/20 px-3 py-2.5 text-xs text-amber-200 disabled:opacity-30">Render All</button></div>
        {activeRun && activeRun.kind !== 'scene' && <button onClick={() => void stopSequence(activeRun)} disabled={activeRun.stop_after_current_requested} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-red-400/20 px-3 py-2.5 text-xs text-red-300 disabled:opacity-40"><Square className="h-3 w-3" />{activeRun.stop_after_current_requested ? 'Stopping after current scene…' : 'Stop after current scene'}</button>}
        {viewedRun && <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3"><div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500"><span>{viewedRun.kind === 'scene' ? 'Render Scene' : viewedRun.kind === 'from_here' ? 'Render From Here' : 'Render All'}</span><span>{viewedRun.status}</span></div><div className="mt-1 font-mono text-[9px] text-zinc-700">Run {viewedRun.id}</div><div className="mt-2 text-[10px] text-zinc-500">Current scene: {project?.scenes.find(candidate => candidate.id === viewedRun.current_scene_id)?.name ?? 'None'}</div><div className="mt-2 grid grid-cols-2 gap-1 text-[10px] text-zinc-500"><span>Started {new Date(viewedRun.started_at).toLocaleString()}</span><span>Elapsed {Math.max(0, Math.floor(((viewedRun.completed_at ? new Date(viewedRun.completed_at).getTime() : clock) - new Date(viewedRun.started_at).getTime()) / 1000))}s</span><span>Complete {viewedRun.items.filter(item => item.state === 'complete').length}</span><span>Waiting {viewedRun.items.filter(item => item.state === 'waiting').length}</span><span>Failed {viewedRun.items.filter(item => item.state === 'failed').length}</span><span>Cancelled {viewedRun.items.filter(item => item.state === 'cancelled').length}</span></div><div className="mt-2 space-y-1.5">{viewedRun.items.map(item => { const queuedScene = project?.scenes.find(candidate => candidate.id === item.scene_id); const percent = item.progress_value !== null && item.progress_max ? Math.round(item.progress_value / item.progress_max * 100) : null; return <div key={item.scene_id} className={`rounded-lg px-2 py-1.5 text-[11px] ${viewedRun.current_scene_id === item.scene_id ? 'bg-amber-300/10 text-amber-200' : 'bg-white/[0.025] text-zinc-500'}`}><div className="flex justify-between"><span className="truncate">{queuedScene?.name ?? `Scene ${item.scene_order}`}</span><span className="ml-2 uppercase">{item.current_phase ?? item.state}{percent !== null ? ` · ${percent}%` : ''}</span></div>{item.render_version_id && <div className="mt-1 text-[9px] text-zinc-700">{item.render_version_id} · {item.prompt_id}{item.continuity_artifact_id ? ` · ${item.continuity_artifact_id}` : ''}</div>}{item.diagnostics && <details className="mt-1 text-[9px] text-red-300/60"><summary>Diagnostics</summary>{item.diagnostics}</details>}</div> })}</div>{viewedRun.failure_or_cancel_reason && <p className="mt-2 text-[10px] text-red-300">{viewedRun.failure_or_cancel_reason}</p>} {!!project?.render_runs.length && <label className="mt-3 block text-[9px] uppercase tracking-wider text-zinc-600">Run history<select value={viewedRun.id} onChange={event => setSelectedRunId(event.target.value)} className="mt-1 w-full rounded-lg border border-white/10 bg-[#11151c] px-2 py-2 text-[10px] normal-case text-zinc-400">{[...project.render_runs].reverse().map(run => <option key={run.id} value={run.id}>{run.kind} · {new Date(run.started_at).toLocaleString()} · {run.status}</option>)}</select></label>}</div>}
        <p className="mt-3 text-center text-[10px] text-zinc-700">Real sampler progress only · phase otherwise</p>
      </aside>

      <SceneStoryboard project={project} statusLabels={STATUS_LABELS} onSelect={target => project && target.id !== project.selected_scene_id && void runSceneOperation(() => selectH3Scene(project.id, target.id))} onAdd={() => project && void runSceneOperation(() => addH3Scene(project.id))} onDuplicate={target => project && void runSceneOperation(() => duplicateH3Scene(project.id, target.id))} onDelete={target => project && void runSceneOperation(() => deleteH3Scene(project.id, target.id))} onMove={moveScene} />
    </div>
    {showNewProject && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#10141b] p-6"><h2 className="text-lg font-semibold">New Project</h2><p className="mt-1 text-sm text-zinc-500">Creates an app-owned project folder and persisted scene cards.</p><input autoFocus value={newProjectName} onChange={event => setNewProjectName(event.target.value)} placeholder="Project name" className="mt-5 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none" /><div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene count</div><div className="mt-2 grid grid-cols-4 gap-2">{[5, 10, 15].map(count => <button key={count} onClick={() => { setNewProjectSceneCount(count); setCustomSceneCount('') }} className={`rounded-lg border px-3 py-2 text-sm ${!customSceneCount && newProjectSceneCount === count ? 'border-amber-300/50 bg-amber-300/10 text-amber-200' : 'border-white/10 text-zinc-500'}`}>{count}</button>)}<input type="number" min="1" max="999" value={customSceneCount} onChange={event => setCustomSceneCount(event.target.value)} placeholder="Custom" aria-label="Custom positive scene count" className="rounded-lg border border-white/10 bg-black/30 px-2 text-center text-sm outline-none" /></div><label className="mt-5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Sequence mode<select value={newProjectSequenceMode} onChange={event => setNewProjectSequenceMode(event.target.value as H3SequenceMode)} className="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm normal-case tracking-normal text-zinc-300"><option value="independent_shots">Independent shots</option><option value="continuous_sequence">Continuous sequence</option></select></label><div className="mt-5 flex justify-end gap-3"><button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-zinc-500">Cancel</button><button onClick={() => void createProject()} disabled={!newProjectName.trim()} className="rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-30">Create Project</button></div></div></div>}
  </div>
}
