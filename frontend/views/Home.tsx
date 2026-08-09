import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Aperture,
  CheckCircle2,
  Clapperboard,
  Film,
  Folder,
  ImagePlus,
  Loader2,
  Plus,
  Radio,
  Sparkles,
} from 'lucide-react'
import { useProjects } from '../contexts/ProjectContext'
import { useProjectReferencesMigration } from '../hooks/useProjectReferencesMigration'
import { pathToFileUrl } from '../lib/file-url'
import {
  getH3RuntimeStatus,
  renderH3Scene,
  type ComfyUIStatus,
  type H3RenderResult,
} from '../lib/h3-generation'
import type { Project } from '../types/project-model'

const VERIFIED_WIDTH = 640
const VERIFIED_HEIGHT = 640
const VERIFIED_FPS = 24
const VERIFIED_DURATION = 5
const VERIFIED_FRAMES = 124

function StatusPill({ status }: { status: ComfyUIStatus }) {
  const style = status === 'connected'
    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
    : status === 'incompatible'
      ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
      : 'border-red-400/30 bg-red-400/10 text-red-300'
  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${style}`}>
      <span className="relative flex h-2 w-2">
        {status === 'connected' && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />}
        <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
      </span>
      ComfyUI {status}
    </div>
  )
}

export function Home() {
  const { projectIds, getProject, createProject } = useProjects()
  const { migrationStatus, migrateProjects } = useProjectReferencesMigration()
  const migrationStarted = useRef(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(projectIds[0] ?? null)
  const [newProjectName, setNewProjectName] = useState('')
  const [showNewProject, setShowNewProject] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [referenceImage, setReferenceImage] = useState<string | null>(null)
  const [seed, setSeed] = useState(193554738272393)
  const [runtimeStatus, setRuntimeStatus] = useState<ComfyUIStatus>('unavailable')
  const [runtimeVersion, setRuntimeVersion] = useState<string | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isRendering, setIsRendering] = useState(false)
  const [renderError, setRenderError] = useState<string | null>(null)
  const [result, setResult] = useState<H3RenderResult | null>(null)

  useEffect(() => {
    if (migrationStatus.status !== 'needed' || migrationStarted.current) return
    migrationStarted.current = true
    void migrateProjects()
  }, [migrateProjects, migrationStatus.status])

  const projects = useMemo(() => projectIds
    .map(id => getProject(id))
    .filter((project): project is Project => project !== null), [getProject, projectIds])

  useEffect(() => {
    if (!selectedProjectId && projects[0]) setSelectedProjectId(projects[0].id)
  }, [projects, selectedProjectId])

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
        if (!active) return
        setRuntimeStatus('unavailable')
        setRuntimeVersion(null)
        setRuntimeError('The local ComfyUI runtime could not be reached.')
      }
    }
    void refresh()
    const interval = window.setInterval(() => void refresh(), 10_000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [])

  const selectedProject = projects.find(project => project.id === selectedProjectId) ?? null
  const canRender = runtimeStatus === 'connected'
    && Boolean(prompt.trim())
    && Boolean(referenceImage)
    && !isRendering

  const chooseReferenceImage = async () => {
    const paths = await window.electronAPI.showOpenFileDialog({
      title: 'Choose a reference image',
      filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }],
      properties: ['openFile'],
    })
    if (paths?.[0]) {
      setReferenceImage(paths[0])
      setResult(null)
      setRenderError(null)
    }
  }

  const createNewProject = () => {
    const name = newProjectName.trim()
    if (!name) return
    const project = createProject(name)
    setSelectedProjectId(project.id)
    setNewProjectName('')
    setShowNewProject(false)
  }

  const renderScene = async () => {
    if (!canRender || !referenceImage) return
    setIsRendering(true)
    setRenderError(null)
    try {
      const response = await renderH3Scene({
        prompt: prompt.trim(),
        input_image: referenceImage,
        seed,
        width: VERIFIED_WIDTH,
        height: VERIFIED_HEIGHT,
        duration_seconds: VERIFIED_DURATION,
        fps: VERIFIED_FPS,
        output_filename_prefix: 'MiniMax_H3',
      })
      setResult(response)
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : 'The local render failed.')
    } finally {
      setIsRendering(false)
    }
  }

  if (migrationStatus.status === 'needed' || migrationStatus.status === 'inProgress') {
    return (
      <div className="flex h-screen items-center justify-center bg-[#07090d] text-zinc-300">
        <Loader2 className="mr-3 h-5 w-5 animate-spin text-amber-300" />
        Preparing local projects…
      </div>
    )
  }

  const previewUrl = result ? pathToFileUrl(result.output_file) : referenceImage ? pathToFileUrl(referenceImage) : null

  return (
    <div className="h-screen overflow-hidden bg-[#07090d] text-zinc-100">
      <div className="grid h-full grid-cols-[250px_minmax(0,1fr)_360px] grid-rows-[minmax(0,1fr)_150px]">
        <aside className="row-span-2 flex min-h-0 flex-col border-r border-white/10 bg-[#0a0d12]">
          <div className="border-b border-white/10 px-5 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 to-orange-600 text-black shadow-[0_0_30px_rgba(251,146,60,.18)]">
                <Aperture className="h-5 w-5" />
              </div>
              <div>
                <div className="font-semibold tracking-wide">H3 Director</div>
                <div className="text-[10px] uppercase tracking-[0.24em] text-zinc-500">Desktop Studio</div>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-5">
            <div className="mb-3 flex items-center justify-between px-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Recent Projects</span>
              <button onClick={() => setShowNewProject(true)} className="rounded-md p-1 text-zinc-500 hover:bg-white/5 hover:text-amber-300" aria-label="New Project">
                <Plus className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1">
              {projects.map(project => (
                <button
                  key={project.id}
                  onClick={() => setSelectedProjectId(project.id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${selectedProjectId === project.id ? 'bg-amber-300/10 text-amber-200' : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'}`}
                >
                  <Folder className="h-4 w-4 shrink-0" />
                  <span className="truncate">{project.name}</span>
                </button>
              ))}
              {projects.length === 0 && <p className="px-3 py-4 text-xs leading-5 text-zinc-600">Create a local project to begin directing your first scene.</p>}
            </div>

            <div className="mt-8 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Assets</div>
            <button onClick={chooseReferenceImage} className="mt-3 flex w-full items-center gap-3 rounded-lg border border-dashed border-white/10 px-3 py-3 text-left text-xs text-zinc-500 hover:border-amber-300/30 hover:text-zinc-300">
              <ImagePlus className="h-4 w-4" />
              {referenceImage ? 'Replace reference' : 'Add reference image'}
            </button>
            {referenceImage && <div className="mt-2 truncate px-3 text-[11px] text-zinc-600">{referenceImage.split(/[\\/]/).pop()}</div>}
          </div>

          <div className="border-t border-white/10 p-4">
            <button onClick={() => setShowNewProject(true)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-100 px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-amber-200">
              <Plus className="h-4 w-4" /> New Project
            </button>
          </div>
        </aside>

        <main className="min-h-0 min-w-0 bg-[radial-gradient(circle_at_50%_20%,rgba(245,158,11,.07),transparent_36%)] p-6">
          <header className="mb-5 flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-zinc-600">Current production</div>
              <h1 className="mt-1 text-xl font-semibold">{selectedProject?.name ?? 'Untitled Project'}</h1>
            </div>
            <div className="text-right">
              <StatusPill status={runtimeStatus} />
              {runtimeVersion && <div className="mt-1 text-[10px] text-zinc-600">ComfyUI {runtimeVersion}</div>}
            </div>
          </header>

          <section className="relative flex h-[calc(100%-64px)] min-h-[360px] items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
            {previewUrl ? (
              result ? (
                <video key={previewUrl} src={previewUrl} controls autoPlay loop className="h-full w-full object-contain" />
              ) : (
                <img src={previewUrl} alt="Selected scene reference" className="h-full w-full object-contain opacity-90" />
              )
            ) : (
              <div className="max-w-sm text-center">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03]">
                  <Film className="h-7 w-7 text-zinc-600" />
                </div>
                <h2 className="mt-5 text-lg font-medium text-zinc-300">Your scene will appear here</h2>
                <p className="mt-2 text-sm leading-6 text-zinc-600">Select a reference image, describe the shot, and render locally with MiniMax H3.</p>
              </div>
            )}
            <div className="absolute left-4 top-4 rounded-full border border-white/10 bg-black/60 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-zinc-400 backdrop-blur">Scene preview</div>
            {result && <div className="absolute bottom-4 right-4 flex items-center gap-2 rounded-full bg-emerald-400/90 px-3 py-1.5 text-xs font-semibold text-emerald-950"><CheckCircle2 className="h-4 w-4" /> Verified render</div>}
          </section>
        </main>

        <aside className="row-span-2 min-h-0 overflow-y-auto border-l border-white/10 bg-[#0b0e13] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-amber-300" /> Director controls</div>
          <div className="mt-6">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Scene prompt</label>
            <textarea
              value={prompt}
              onChange={event => setPrompt(event.target.value)}
              placeholder="Describe the shot, camera movement, subject action, lighting, mood and audio…"
              className="mt-2 h-40 w-full resize-none rounded-xl border border-white/10 bg-black/30 p-3 text-sm leading-6 text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-amber-300/40"
            />
          </div>

          <div className="mt-5">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Reference image</label>
            <button onClick={chooseReferenceImage} className="mt-2 flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.025] px-3 py-3 text-sm text-zinc-400 hover:border-amber-300/30">
              <span className="truncate">{referenceImage?.split(/[\\/]/).pop() ?? 'Choose image'}</span>
              <ImagePlus className="ml-3 h-4 w-4 shrink-0" />
            </button>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3">
            {[['Width', `${VERIFIED_WIDTH}`], ['Height', `${VERIFIED_HEIGHT}`], ['FPS', `${VERIFIED_FPS}`], ['Duration', `${VERIFIED_DURATION}s`], ['Frames', `${VERIFIED_FRAMES}`]].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
                <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">{label}</div>
                <div className="mt-1 font-mono text-sm text-zinc-300">{value}</div>
              </div>
            ))}
            <label className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Seed</div>
              <input type="number" value={seed} onChange={event => setSeed(Number(event.target.value))} className="mt-1 w-full bg-transparent font-mono text-sm text-zinc-300 outline-none" />
            </label>
          </div>

          {runtimeError && runtimeStatus !== 'connected' && <p className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-5 text-amber-200/70">{runtimeError}</p>}
          {renderError && <p className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-300">{renderError}</p>}

          <button
            onClick={() => void renderScene()}
            disabled={!canRender}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-300 to-orange-500 px-4 py-3.5 text-sm font-bold text-zinc-950 shadow-[0_12px_40px_rgba(249,115,22,.16)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {isRendering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
            {isRendering ? 'Rendering locally…' : 'Render Scene'}
          </button>
          <p className="mt-3 text-center text-[10px] leading-4 text-zinc-700">Single scene · local ComfyUI · no cloud fallback</p>
        </aside>

        <section className="min-w-0 border-t border-white/10 bg-[#090c11] px-6 py-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Storyboard</div>
            <div className="flex items-center gap-2 text-[10px] text-zinc-600"><Radio className="h-3 w-3" /> Single-scene mode</div>
          </div>
          <div className="flex h-[92px] gap-3">
            <div className="flex w-52 items-center gap-3 rounded-xl border border-amber-300/30 bg-amber-300/[0.05] p-3">
              <div className="flex h-14 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-black">
                {previewUrl ? <img src={previewUrl} alt="Scene 1" className="h-full w-full object-cover" /> : <Film className="h-5 w-5 text-zinc-700" />}
              </div>
              <div className="min-w-0"><div className="text-xs font-semibold text-zinc-200">Scene 01</div><div className="mt-1 text-[10px] text-zinc-600">{VERIFIED_DURATION}s · {VERIFIED_FRAMES}f</div></div>
            </div>
            <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-zinc-700">Additional scenes arrive in a later milestone</div>
          </div>
        </section>
      </div>

      {showNewProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#10141b] p-6 shadow-2xl">
            <h2 className="text-lg font-semibold">New Project</h2>
            <p className="mt-1 text-sm text-zinc-500">Create a local H3 Director project.</p>
            <input autoFocus value={newProjectName} onChange={event => setNewProjectName(event.target.value)} onKeyDown={event => event.key === 'Enter' && createNewProject()} placeholder="Project name" className="mt-5 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-amber-300/40" />
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => setShowNewProject(false)} className="rounded-lg px-4 py-2 text-sm text-zinc-500 hover:text-zinc-200">Cancel</button>
              <button onClick={createNewProject} disabled={!newProjectName.trim()} className="rounded-lg bg-amber-300 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-30">Create Project</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
