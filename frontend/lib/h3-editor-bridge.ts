import type { H3Project, H3RenderVersion } from './h3-projects'
import {
  DEFAULT_CLIP_TRANSITION,
  DEFAULT_COLOR_CORRECTION,
  createDefaultTimeline,
  normalizeProject,
  type Asset,
  type Project,
  type TimelineClip,
} from '../types/project-model'

export const h3EditorProjectId = (h3ProjectId: string) => `h3-editor-${h3ProjectId}`

function orderedScenes(project: H3Project) {
  return [...project.scenes].sort((a, b) => a.order - b.order)
}

function selectedVersion(project: H3Project, sceneId: string): H3RenderVersion | null {
  const scene = project.scenes.find(candidate => candidate.id === sceneId)
  return scene?.render_versions.find(version => version.id === scene.selected_render_version_id) ?? null
}

export function getH3AssetDisplayLabel(asset: Asset, includeDuration = true): string | null {
  const source = asset.h3Source
  if (!source?.sceneNumber || !source.renderVersionNumber) return null
  const label = `Scene ${String(source.sceneNumber).padStart(2, '0')} · v${String(source.renderVersionNumber).padStart(3, '0')}`
  return includeDuration && asset.duration != null ? `${label} · ${asset.duration.toFixed(1)}s` : label
}

export function buildH3EditorProject(project: H3Project): Project {
  const timeline = createDefaultTimeline('H3 Assembly')
  const assets: Asset[] = []
  const clips: TimelineClip[] = []
  let startTime = 0

  for (const [sceneIndex, scene] of orderedScenes(project).entries()) {
    const version = selectedVersion(project, scene.id)
    if (!version) continue
    const duration = version.ffprobe.duration_seconds
    const assetId = `h3-asset-${scene.id}-${version.id}`
    const asset: Asset = {
      id: assetId,
      type: 'video',
      path: version.video_file,
      width: version.ffprobe.width,
      height: version.ffprobe.height,
      prompt: version.prompt,
      resolution: `${version.ffprobe.width}x${version.ffprobe.height}`,
      duration,
      createdAt: Date.parse(version.created_at),
      h3Source: {
        projectId: project.id,
        sceneId: scene.id,
        renderVersionId: version.id,
        sceneNumber: sceneIndex + 1,
        renderVersionNumber: version.number,
        outputSha256: version.output_sha256,
        metadataFile: version.metadata_file,
      },
    }
    assets.push(asset)
    clips.push({
      id: `h3-clip-${scene.id}-${version.id}`,
      assetId,
      type: 'video',
      startTime,
      duration,
      trimStart: 0,
      trimEnd: 0,
      speed: 1,
      reversed: false,
      muted: false,
      volume: 1,
      trackIndex: 0,
      asset,
      flipH: false,
      flipV: false,
      transitionIn: DEFAULT_CLIP_TRANSITION,
      transitionOut: DEFAULT_CLIP_TRANSITION,
      colorCorrection: DEFAULT_COLOR_CORRECTION,
      opacity: 100,
    })
    startTime += duration
  }
  timeline.clips = clips
  return normalizeProject({
    version: 2,
    id: h3EditorProjectId(project.id),
    name: `${project.name} — Edit`,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    bins: {},
    assets,
    timelines: [timeline],
    activeTimelineId: timeline.id,
    h3SourceProjectId: project.id,
    h3SourceProjectRoot: project.project_root,
  })
}

export function getH3EditorUpdates(project: H3Project, editorProject: Project): Array<{ sceneId: string; fromVersionId: string; toVersionId: string }> {
  return project.scenes.flatMap(scene => {
    const selected = selectedVersion(project, scene.id)
    if (!selected) return []
    const imported = editorProject.assets.find(asset => asset.h3Source?.sceneId === scene.id)?.h3Source
    if (!imported || imported.renderVersionId === selected.id) return []
    return [{ sceneId: scene.id, fromVersionId: imported.renderVersionId, toVersionId: selected.id }]
  })
}

export function replaceH3EditorVersions(project: H3Project, editorProject: Project): Project {
  const replacements = new Map(project.scenes.flatMap(scene => {
    const version = selectedVersion(project, scene.id)
    return version ? [[scene.id, version] as const] : []
  }))
  const assets = editorProject.assets.map(asset => {
    const source = asset.h3Source
    const version = source ? replacements.get(source.sceneId) : undefined
    if (!source || !version || source.renderVersionId === version.id) return asset
    return {
      ...asset,
      path: version.video_file,
      width: version.ffprobe.width,
      height: version.ffprobe.height,
      prompt: version.prompt,
      resolution: `${version.ffprobe.width}x${version.ffprobe.height}`,
      duration: version.ffprobe.duration_seconds,
      h3Source: {
        projectId: project.id,
        sceneId: source.sceneId,
        renderVersionId: version.id,
        sceneNumber: orderedScenes(project).findIndex(scene => scene.id === source.sceneId) + 1,
        renderVersionNumber: version.number,
        outputSha256: version.output_sha256,
        metadataFile: version.metadata_file,
      },
    }
  })
  const byId = new Map(assets.map(asset => [asset.id, asset]))
  return refreshH3EditorProvenance(project, {
    ...editorProject,
    assets,
    timelines: editorProject.timelines.map(timeline => ({
      ...timeline,
      clips: timeline.clips.map(clip => ({ ...clip, asset: clip.assetId ? byId.get(clip.assetId) ?? clip.asset : clip.asset })),
    })),
    updatedAt: Date.now(),
  })
}

/** Refreshes display-only H3 provenance from the authoritative persisted H3 scene order. */
export function refreshH3EditorProvenance(project: H3Project, editorProject: Project): Project {
  const scenes = orderedScenes(project)
  const sceneNumbers = new Map(scenes.map((scene, index) => [scene.id, index + 1]))
  const versionsByScene = new Map(scenes.map(scene => [scene.id, new Map(scene.render_versions.map(version => [version.id, version]))]))
  const assets = editorProject.assets.map(asset => {
    const source = asset.h3Source
    if (!source || source.projectId !== project.id) return asset
    const sceneNumber = sceneNumbers.get(source.sceneId)
    const version = versionsByScene.get(source.sceneId)?.get(source.renderVersionId)
    if (!sceneNumber || !version) return asset
    return {
      ...asset,
      h3Source: {
        ...source,
        sceneNumber,
        renderVersionNumber: version.number,
      },
    }
  })
  const byId = new Map(assets.map(asset => [asset.id, asset]))
  return {
    ...editorProject,
    assets,
    timelines: editorProject.timelines.map(timeline => ({
      ...timeline,
      clips: timeline.clips.map(clip => ({ ...clip, asset: clip.assetId ? byId.get(clip.assetId) ?? clip.asset : clip.asset })),
    })),
    updatedAt: Date.now(),
  }
}
