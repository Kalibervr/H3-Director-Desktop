import { ChevronLeft, ChevronRight, Copy, Film, Plus, Trash2 } from 'lucide-react'
import { pathToFileUrl } from '../lib/file-url'
import type { H3Project, H3Scene, H3SceneStatus } from '../lib/h3-projects'

interface Props {
  project: H3Project | null
  statusLabels: Record<H3SceneStatus, string>
  onSelect: (scene: H3Scene) => void
  onAdd: () => void
  onDuplicate: (scene: H3Scene) => void
  onDelete: (scene: H3Scene) => void
  onMove: (scene: H3Scene, direction: -1 | 1) => void
}

function thumbnail(scene: H3Scene): { url: string; video: boolean } | null {
  const version = scene.render_versions.find(item => item.id === scene.selected_render_version_id)
  if (version) return { url: pathToFileUrl(version.video_file), video: true }
  return scene.reference_image ? { url: pathToFileUrl(scene.reference_image), video: false } : null
}

export function SceneStoryboard({ project, statusLabels, onSelect, onAdd, onDuplicate, onDelete, onMove }: Props) {
  return <section className="min-w-0 border-t border-white/10 bg-[#090c11] px-6 py-3">
    <div className="mb-2 flex items-center justify-between"><div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Storyboard</div><button onClick={onAdd} disabled={!project} className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-[10px] text-zinc-400 disabled:opacity-30"><Plus className="h-3 w-3" /> Add Scene</button></div>
    <div className="flex h-[96px] gap-3 overflow-x-auto pb-1">
      {project?.scenes.map((scene, index) => {
        const media = thumbnail(scene)
        const selected = scene.id === project.selected_scene_id
        return <div key={scene.id} className={`group relative flex w-64 shrink-0 items-center gap-3 rounded-xl border p-2.5 ${selected ? 'border-amber-300/40 bg-amber-300/[0.06]' : 'border-white/10 bg-white/[0.02]'}`}>
          <button onClick={() => onSelect(scene)} className="flex min-w-0 flex-1 items-center gap-3 text-left"><div className="flex h-14 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-black">{media ? media.video ? <video src={media.url} muted preload="metadata" className="h-full w-full object-cover" /> : <img src={media.url} alt={`${scene.name} reference`} className="h-full w-full object-cover" /> : <Film className="h-5 w-5 text-zinc-700" />}</div><div className="min-w-0"><div className="text-[9px] uppercase tracking-wider text-zinc-600">Scene {String(index + 1).padStart(2, '0')}</div><div className="truncate text-xs font-semibold">{scene.name}</div><div className="mt-1 truncate text-[9px] text-zinc-600">{scene.duration_seconds}s · {statusLabels[scene.status]}</div></div></button>
          <div className="absolute right-1 top-1 hidden gap-0.5 rounded-md bg-black/80 p-0.5 group-hover:flex group-focus-within:flex"><button aria-label={`Move ${scene.name} left`} disabled={index === 0} onClick={() => onMove(scene, -1)} className="p-1 disabled:opacity-25"><ChevronLeft className="h-3 w-3" /></button><button aria-label={`Move ${scene.name} right`} disabled={index === project.scenes.length - 1} onClick={() => onMove(scene, 1)} className="p-1 disabled:opacity-25"><ChevronRight className="h-3 w-3" /></button><button aria-label={`Duplicate ${scene.name}`} onClick={() => onDuplicate(scene)} className="p-1"><Copy className="h-3 w-3" /></button><button aria-label={`Delete ${scene.name}`} disabled={project.scenes.length === 1} onClick={() => onDelete(scene)} className="p-1 text-red-300 disabled:opacity-25"><Trash2 className="h-3 w-3" /></button></div>
        </div>
      })}
      {!project && <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-zinc-700">Create a project to build its storyboard</div>}
    </div>
  </section>
}
