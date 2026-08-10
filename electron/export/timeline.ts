export interface ExportClip {
  id?: string; path: string; type: string; startTime: number; duration: number; trimStart: number;
  speed: number; reversed: boolean; flipH: boolean; flipV: boolean; opacity: number; trackIndex: number;
  muted: boolean; volume: number;
  transitionIn?: ExportTransition;
  transitionOut?: ExportTransition;
}

export type ExportTransitionType =
  | 'none'
  | 'dissolve'
  | 'fade-to-black'
  | 'fade-to-white'
  | 'wipe-left'
  | 'wipe-right'
  | 'wipe-up'
  | 'wipe-down'

export interface ExportTransition {
  type: ExportTransitionType
  duration: number
}

export interface FlatSegment {
  sourceClipId?: string; filePath: string; type: string; startTime: number; duration: number; trimStart: number;
  speed: number; reversed: boolean; flipH: boolean; flipV: boolean; opacity: number;
  muted: boolean; volume: number;
}

export interface DissolveBoundary {
  outgoingSegmentIndex: number
  incomingSegmentIndex: number
  duration: number
}

export interface VisualExportPlan {
  segments: FlatSegment[]
  dissolves: DissolveBoundary[]
}

export class TransitionConfigurationError extends Error {}

const CUT_POINT_TOLERANCE = 0.05

function isVisualClip(clip: ExportClip): boolean {
  return clip.type === 'video' || clip.type === 'image'
}

function transitionType(transition: ExportTransition | undefined): ExportTransitionType {
  return transition?.type ?? 'none'
}

function transitionDuration(transition: ExportTransition | undefined): number {
  return transition?.duration ?? 0
}

/**
 * Build the visual plan used by native export.
 *
 * The editor's verified dissolve preview does not move clip boundaries: it
 * blends the outgoing tail into the incoming clip's first frame immediately
 * before their shared cut point. Keeping that plan here preserves the editor
 * timeline duration and makes export match the current monitor behavior.
 */
export function buildVisualExportPlan(clips: ExportClip[]): VisualExportPlan {
  const segments = flattenTimeline(clips)
  const transitionedClips = clips.filter(clip =>
    isVisualClip(clip) && (transitionType(clip.transitionIn) !== 'none' || transitionType(clip.transitionOut) !== 'none'),
  )

  if (transitionedClips.length === 0) return { segments, dissolves: [] }

  for (const clip of transitionedClips) {
    for (const transition of [clip.transitionIn, clip.transitionOut]) {
      const type = transitionType(transition)
      if (type !== 'none' && type !== 'dissolve') {
        throw new TransitionConfigurationError(
          `${type} transitions are preserved but are not supported by local export. Use Dissolve or remove the transition.`,
        )
      }
      if (type === 'dissolve' && (!Number.isFinite(transitionDuration(transition)) || transitionDuration(transition) <= 0)) {
        throw new TransitionConfigurationError('Dissolve duration must be greater than zero.')
      }
    }
  }

  const visualClips = clips.filter(isVisualClip).sort((a, b) => a.startTime - b.startTime)
  const transitionTrack = transitionedClips[0].trackIndex
  if (visualClips.some(clip => clip.trackIndex !== transitionTrack)) {
    throw new TransitionConfigurationError(
      'Dissolve export currently requires all visual clips to be on one video track. Remove the transition or flatten the layered edit first.',
    )
  }

  const dissolves: DissolveBoundary[] = []
  for (let index = 0; index < visualClips.length; index++) {
    const outgoing = visualClips[index]
    if (transitionType(outgoing.transitionOut) !== 'dissolve') continue

    const incoming = visualClips[index + 1]
    if (!incoming || transitionType(incoming.transitionIn) !== 'dissolve') {
      throw new TransitionConfigurationError('A dissolve requires matching Dissolve In and Dissolve Out transitions at the same cut.')
    }

    const outgoingEnd = outgoing.startTime + outgoing.duration
    if (Math.abs(incoming.startTime - outgoingEnd) > CUT_POINT_TOLERANCE) {
      throw new TransitionConfigurationError('A dissolve requires adjacent clips on the same cut point.')
    }

    const duration = transitionDuration(outgoing.transitionOut)
    if (Math.abs(transitionDuration(incoming.transitionIn) - duration) > CUT_POINT_TOLERANCE) {
      throw new TransitionConfigurationError('Dissolve In and Dissolve Out durations must match.')
    }
    if (duration > outgoing.duration || duration > incoming.duration) {
      throw new TransitionConfigurationError('Dissolve duration cannot be longer than either adjacent clip.')
    }

    const outgoingSegmentIndex = segments.findIndex(segment =>
      segment.sourceClipId === outgoing.id && Math.abs(segment.startTime - outgoing.startTime) < CUT_POINT_TOLERANCE,
    )
    const incomingSegmentIndex = segments.findIndex(segment =>
      segment.sourceClipId === incoming.id && Math.abs(segment.startTime - incoming.startTime) < CUT_POINT_TOLERANCE,
    )
    if (outgoingSegmentIndex < 0 || incomingSegmentIndex !== outgoingSegmentIndex + 1) {
      throw new TransitionConfigurationError('Dissolve export could not resolve a simple adjacent visual boundary.')
    }

    dissolves.push({ outgoingSegmentIndex, incomingSegmentIndex, duration })
  }

  for (let index = 0; index < visualClips.length; index++) {
    const incoming = visualClips[index]
    if (transitionType(incoming.transitionIn) !== 'dissolve') continue
    const previous = visualClips[index - 1]
    if (!previous || transitionType(previous.transitionOut) !== 'dissolve') {
      throw new TransitionConfigurationError('A dissolve requires matching Dissolve In and Dissolve Out transitions at the same cut.')
    }
  }

  return { segments, dissolves }
}

/**
 * Flatten a multi-track timeline into a sequence of segments for ffmpeg concat.
 * At each point in time, the highest trackIndex wins for video (NLE convention).
 */
export function flattenTimeline(clips: ExportClip[]): FlatSegment[] {
  // Only consider video/image clips for visual flattening
  const videoClips = clips.filter(c => c.type === 'video' || c.type === 'image')
  if (videoClips.length === 0) return []

  // Collect all time boundaries
  const boundaries = new Set<number>()
  boundaries.add(0)
  for (const c of videoClips) {
    boundaries.add(c.startTime)
    boundaries.add(c.startTime + c.duration)
  }
  const sorted = [...boundaries].sort((a, b) => a - b)

  const segments: FlatSegment[] = []

  for (let i = 0; i < sorted.length - 1; i++) {
    const t0 = sorted[i]
    const t1 = sorted[i + 1]
    const segDur = t1 - t0
    if (segDur < 0.001) continue

    const mid = (t0 + t1) / 2
    // Find highest-track clip at this time
    const active = videoClips
      .filter(c => mid >= c.startTime && mid < c.startTime + c.duration)
      .sort((a, b) => b.trackIndex - a.trackIndex)

    if (active.length > 0) {
      const c = active[0]
      const offsetInClip = t0 - c.startTime
      segments.push({
        sourceClipId: c.id,
        filePath: c.path,
        type: c.type,
        startTime: t0,
        duration: segDur,
        trimStart: c.trimStart + offsetInClip * c.speed,
        speed: c.speed,
        reversed: c.reversed,
        flipH: c.flipH,
        flipV: c.flipV,
        opacity: c.opacity,
        muted: c.muted,
        volume: c.volume,
      })
    } else {
      segments.push({
        sourceClipId: undefined, filePath: '', type: 'gap', startTime: t0, duration: segDur, trimStart: 0,
        speed: 1, reversed: false, flipH: false, flipV: false, opacity: 100,
        muted: true, volume: 0,
      })
    }
  }

  // Merge adjacent segments from the same file with contiguous trim
  const merged: FlatSegment[] = []
  for (const seg of segments) {
    const prev = merged[merged.length - 1]
    if (prev && prev.sourceClipId === seg.sourceClipId && prev.filePath === seg.filePath && prev.filePath !== '' &&
        prev.speed === seg.speed && prev.reversed === seg.reversed &&
        prev.flipH === seg.flipH && prev.flipV === seg.flipV &&
        prev.opacity === seg.opacity && prev.muted === seg.muted && prev.volume === seg.volume &&
        Math.abs((prev.trimStart + prev.duration * prev.speed) - seg.trimStart) < 0.01) {
      prev.duration += seg.duration
    } else {
      merged.push({ ...seg })
    }
  }

  return merged
}
