# H3 Director editor reuse audit

Status: source audit completed 2026-08-10 before H3/editor bridge implementation.

This audit covers the editor that remains in the LTX Desktop fork. Classifications describe verified source behavior, not product claims. Runtime verification is still required for the H3 bridge and final export.

| Subsystem | Classification | Verified source evidence and H3 action |
| --- | --- | --- |
| Timeline | REUSE_WITH_CHANGES | `VideoEditorTimelineEditingPanel.tsx`, `editor-actions.ts`, selectors and store implement a multitrack timeline. Reuse it; provide an H3-created initial timeline. |
| Tracks | REUSE_AS_IS | `DEFAULT_TRACKS` defines three video and two audio tracks; actions support adding, locking, muting, soloing and source patching. |
| Clips | REUSE_WITH_CHANGES | The clip model supports video, audio, image, adjustment and text clips with trim, speed and effects. Add immutable H3 provenance fields without changing source files. |
| Asset/media bin | H3_ADAPTER_REQUIRED | Existing bins, asset cards, import and thumbnails are reusable. H3 selected render versions must be referenced as assets without copying their immutable videos. |
| Video preview/player | REUSE_AS_IS | `ProgramMonitor.tsx` composites active clips, plays video and renders verified preview transitions. |
| Trimming | REUSE_AS_IS | Timeline actions and clip properties persist `trimStart`, `trimEnd` and duration independently of source media. |
| Clip movement/reordering | REUSE_AS_IS | Drag/action code moves clips and supports ripple/overwrite behavior; it updates editor state only. |
| Audio playback | REUSE_AS_IS | Program monitor and playback audio synchronization use video-embedded and audio-clip media. |
| Audio tracks | REUSE_AS_IS | Linked audio clips, dedicated tracks, mute/solo/volume and export mixdown are implemented. Initial H3 video clips retain embedded audio without a duplicate linked clip. |
| Transitions | REUSE_WITH_CHANGES | Dissolve/fade/wipe controls and preview rendering exist. The current native export filter concatenates flat segments and does not consume clip transition fields, so transition export is UNSUPPORTED_OR_UNKNOWN until separately implemented and verified. |
| Text clips/titles | REUSE_AS_IS | Text clips, presets and property controls exist in the editor model and program monitor. |
| Source monitor | REUSE_AS_IS | `VideoEditorSourceMonitor.tsx` and source-edit actions implement source loading, in/out and timeline insertion. |
| Gap handling/fill | REMOVE_LTX_SPECIFIC_INTEGRATION | Gap detection and close-gap editing are reusable, but `GapGenerationModal` and suggestion/generation paths call legacy generation. Hide generation actions; retain ordinary gap display/editing. |
| Editor project persistence | REUSE_WITH_CHANGES | Project schema/migration and autosave exist. Use a distinct deterministic editor project keyed to an H3 project, retain the existing local cache, and mirror the normalized editor state to `editor-project.json` in the app-owned H3 project root. Do not write editor changes into H3 `project.json`. |
| Editor undo/redo | REUSE_AS_IS | `editor-store.tsx` maintains bounded undo/redo snapshots for assets, bins and timelines. |
| Shortcuts | REUSE_AS_IS | `useEditorKeyboard.ts` and menu definitions cover transport, editing, undo/redo, tools and zoom. |
| Playback controls | REUSE_AS_IS | Playback engine supports play/stop, shuttle and in/out playback. |
| Zoom/scrubbing | REUSE_AS_IS | Timeline zoom, playhead scrubbing, source/program scrub bars and marker dragging are implemented. |
| Export/render pipeline | REUSE_WITH_CHANGES | `ExportModal.tsx` and Electron `export/*` implement local FFmpeg H.264/ProRes/VP9 export, subtitles and audio mixdown. Reuse for H3 media; do not claim exported transitions until verified. |
| FFmpeg integration | REUSE_AS_IS | Export resolves the bundled FFmpeg, validates allowed paths, invokes argument arrays and mixes embedded/source audio. |
| Project save/reopen | H3_ADAPTER_REQUIRED | Editor autosave/reopen exists. Add deterministic H3 editor-project creation/opening and explicit version update semantics. |
| Proxy/performance handling | UNSUPPORTED_OR_UNKNOWN | Thumbnails and pooled media elements exist, but no verified proxy-media generation or proxy switching was found. |
| Multi-asset handling | REUSE_AS_IS | Assets, bins, takes, multiple timelines and visual/audio imports are implemented. |
| LTX generation coupling | REMOVE_LTX_SPECIFIC_INTEGRATION | `useRegeneration`, gap generation, Regenerate, Retake, IC-LoRA, image/video generation and Gen Space navigation are legacy generation surfaces. They must not be reachable from the H3 editor. |
| Branding/navigation | H3_ADAPTER_REQUIRED | `Project.tsx` still exposes LTX logo, Gen Space and “About LTX Desktop”. H3 editor mode needs H3 branding and Back to Director navigation. |

## Bridge invariants

- H3 `project.json`, scene order and immutable render directories remain generation source of truth.
- One deterministic editor project belongs to one H3 project.
- First open imports only each active scene's selected render version, in scene order, with actual ffprobe duration.
- Assets record H3 project ID, scene ID, render-version ID and source metadata.
- Timeline edits never mutate H3 scenes or render metadata.
- A later H3 selection never silently changes an existing editor asset or clip. Replacement is an explicit user action.
- The editor persists independently and Back to Director leaves that state intact.

## First integration slice

Create/open the deterministic editor project from the Director workspace, populate its initial primary video timeline with selected immutable H3 renders, retain embedded audio, hide legacy generation surfaces, reuse editor autosave/player/timeline/export, and expose explicit update availability without automatic replacement.
