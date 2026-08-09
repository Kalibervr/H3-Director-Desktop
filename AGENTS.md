# AGENTS.md — H3 Director Desktop (LTX Desktop Fork, Local Only)

## Mission

Fork and transform the open-source Lightricks/LTX-Desktop repository into a Windows-first local desktop application named **H3 Director Desktop**.

The application must reuse the proven desktop shell, editor infrastructure, project handling, Electron integration, React UI patterns, FastAPI backend structure, FFmpeg integration, settings system, and installer foundation where technically appropriate.

The application must replace LTX-specific video generation with a local **ComfyUI + MiniMax H3** generation provider.

The first production target is **fully local operation**. No cloud generation, no paid API, no remote prompt enhancement, and no mandatory online account.

## Source repository

Use:

```text
https://github.com/Lightricks/LTX-Desktop
```

Do not copy isolated source snippets into an unrelated blank application unless a documented architectural reason requires it.

Start from a clean fork or clone and preserve:

- Apache-2.0 license requirements;
- relevant copyright notices;
- applicable third-party notices;
- attribution for reused source;
- a written modification record.

Do not imply that H3 Director Desktop is an official Lightricks or MiniMax product.

## Absolute local-only requirement

Phase 1 must not require or call:

- LTX API;
- Gemini API;
- fal.ai;
- OpenAI API;
- cloud text encoding;
- cloud video generation;
- remote image generation;
- remote prompt enhancement;
- analytics or telemetry endpoints;
- login or account systems;
- credit systems.

Disable or remove API-only paths from the user interface and production execution path.

Network access is allowed only for clearly user-initiated development or installation tasks such as cloning the source repository or optionally downloading dependencies. The running application must not send prompts, images, videos, project metadata, or usage analytics to external services.

Prompt enhancement in Phase 1 may use:

1. deterministic local templates;
2. optional local Ollama;
3. no enhancement.

If Ollama is unavailable, the app must remain functional.

## Non-negotiable truthfulness rules

1. Never invent a ComfyUI endpoint, node type, workflow field, model filename, model capability, custom node, resolution, duration, FPS value, or memory-management operation.
2. Inspect the actual source repository before editing.
3. Inspect the actual user-supplied MiniMax H3 workflow JSON before creating the renderer.
4. Inspect the running local ComfyUI API and node metadata before binding workflow fields.
5. Mark all unverified behavior as blocked or pending verification.
6. Never label a mock as a working renderer.
7. Never claim a render succeeded unless the output file exists, is readable, and passes FFmpeg probing.
8. Never claim RAM, VRAM, CUDA cache, model memory, or ComfyUI cache was cleared unless the real operation completed and its result can be measured or confirmed.
9. Never silently fall back to cloud services.
10. Never overwrite a project, source asset, scene render, render version, continuity frame, or final export.
11. Do not remove working editor or project functionality merely to simplify implementation.
12. Do not perform a broad rewrite before producing a reuse audit.

## Required first action: repository reuse audit

Before implementing H3 generation, inspect the repository and create:

```text
docs/LTX_REUSE_AUDIT.md
```

Classify each major subsystem as:

- `REUSE_AS_IS`
- `REUSE_WITH_CHANGES`
- `REPLACE`
- `REMOVE`
- `UNKNOWN_REQUIRES_TESTING`

Audit at minimum:

- Electron main process;
- preload bridge;
- React application shell;
- project persistence;
- video editor;
- media library;
- FFmpeg integration;
- settings;
- backend process management;
- local model management;
- render queue;
- progress reporting;
- prompt enhancement;
- LTX generation code;
- API mode;
- telemetry;
- installer;
- updater;
- tests;
- performance runner;
- licenses and notices.

Do not start a large implementation until the audit is written.

## Working method

Before each meaningful change:

1. Inspect relevant source files.
2. State the exact intended change.
3. Identify assumptions.
4. Replace assumptions with inspection or runtime evidence where possible.
5. Implement the smallest complete change.
6. Run applicable checks.
7. Report the exact commands and actual results.

Required checks where available:

```text
pnpm typecheck
pnpm backend:test
pnpm build
```

Also run focused tests for modified modules.

Do not report success if a command failed.

## Target architecture

Preserve the existing separation where practical:

- React + TypeScript renderer/frontend;
- Electron main process and preload bridge;
- Python FastAPI local backend;
- FFmpeg for media operations;
- local application data;
- existing project/editor infrastructure.

Introduce a provider boundary:

```text
GenerationProvider
├── ComfyUIMiniMaxH3Provider
└── future providers, not implemented in Phase 1
```

LTX-specific generation must not remain tangled with editor state.

## Critical rendering design

Do not construct one giant 5–15 scene ComfyUI workflow.

Use one verified **single-scene MiniMax H3 API workflow** per render job.

The application, not ComfyUI, owns:

- scene order;
- scene dependency graph;
- continuity decisions;
- reference-image selection;
- last-frame extraction;
- prompt assembly;
- prompt enhancement;
- queue sequencing;
- retries;
- render versions;
- output folders;
- progress mapping;
- cancellation;
- final assembly.

## Scene system

The user can create:

- 5 scenes;
- 10 scenes;
- 15 scenes;
- any custom positive scene count.

Scenes can later be:

- added;
- duplicated;
- deleted;
- reordered;
- rendered individually;
- rendered from the selected scene;
- rendered as a full project.

Each scene is independent and persisted.

Minimum model:

```ts
type SceneMode =
  | "continue_previous"
  | "new_shot"
  | "same_character_new_shot";

type SceneStatus =
  | "idle"
  | "queued"
  | "preparing"
  | "rendering"
  | "encoding"
  | "complete"
  | "failed"
  | "cancelled";

interface Scene {
  id: string;
  projectId: string;
  order: number;
  name: string;

  userPrompt: string;
  enhancedPrompt: string;
  finalPrompt: string;
  promptEnhancementEnabled: boolean;

  mode: SceneMode;
  previousSceneId: string | null;

  durationSeconds: number;
  width: number;
  height: number;
  fps: number;
  seed: number | null;

  referenceImagePaths: string[];
  characterReferenceIds: string[];
  locationReferenceId: string | null;

  continuityStrategy:
    | "last_valid_frame"
    | "offset_from_end"
    | "manual_frame";
  continuityOffsetFrames: number;
  manualStartFramePath: string | null;

  selectedRenderVersionId: string | null;
  status: SceneStatus;
}
```

Validate duration, resolution, FPS, and input modes against the actual MiniMax H3 workflow and installed nodes.

## New project wizard

The user chooses:

- project name;
- scene count: 5, 10, 15, or custom;
- aspect ratio;
- resolution;
- FPS;
- default seconds per scene;
- visual style;
- default scene mode;
- output root;
- prompt-enhancement mode.

The app creates the scene cards automatically.

## Director-style interface

Create a premium dark cinematic UI without copying another service pixel-for-pixel.

Recommended layout:

### Left panel

- projects;
- characters;
- locations;
- reference images;
- imported media;
- generated versions.

### Center

- large video player;
- current-scene preview;
- project playback;
- compare render versions.

### Bottom

- storyboard first;
- lightweight timeline later;
- scene thumbnails;
- duration labels;
- status indicators;
- drag reorder.

### Right Director panel

- user prompt;
- enhanced prompt;
- exact final prompt;
- reference images;
- scene mode;
- character continuity;
- location;
- shot size;
- camera movement;
- subject action;
- mood;
- lighting;
- duration;
- aspect ratio;
- resolution;
- FPS;
- seed;
- continuity source;
- continuity-frame strategy;
- Render Scene;
- Render From Here;
- Render All;
- Retake;
- Duplicate;
- Cancel.

### Resource/status bar

- ComfyUI status;
- queue;
- active scene;
- render progress;
- system RAM;
- process RAM;
- VRAM;
- GPU utilization;
- GPU temperature when available;
- disk free space.

No node graph, links, subgraphs, prompt IDs, or raw ComfyUI internals should be required for normal use.

## Prompt Director

The user writes a short natural scene description.

The application constructs the final MiniMax H3 prompt from verified fields:

- project style;
- character references;
- location;
- scene mode;
- incoming continuity frame;
- shot framing;
- camera movement;
- subject action;
- lighting;
- mood;
- explicit continuity changes;
- preservation rules.

Always show:

1. user prompt;
2. enhanced prompt;
3. exact final prompt sent to ComfyUI.

Phase 1 providers:

```text
Template Only
Local Ollama
Disabled
```

No online prompt provider.

Never silently replace the user’s prompt after an Ollama error.

## Continuity behavior

### Continue Previous

1. Verify the selected previous scene version exists.
2. Probe it with FFmpeg.
3. Determine the final valid frame or configured offset.
4. Extract that frame.
5. Save it as an immutable input artifact.
6. Record:
   - source scene;
   - source render version;
   - video path;
   - frame index;
   - timestamp;
   - extraction settings.
7. Use the extracted image as the next single-scene input.

### New Shot

Use the scene’s own reference image.

Allow completely different:

- environment;
- person;
- shot;
- lighting;
- visual setup.

### Same Character, New Shot

Use the new shot’s reference/environment plus selected character references only when the verified MiniMax H3 workflow supports those inputs.

Do not promise perfect identity preservation.

## ComfyUI settings

Provide:

- ComfyUI root;
- ComfyUI Python/executable;
- local API URL;
- input folder;
- output folder;
- models root;
- custom nodes folder;
- MiniMax H3 workflow file;
- MiniMax H3 model paths where verifiable;
- FFmpeg path;
- project root;
- temporary/cache root;
- optional Ollama endpoint and model.

Each path must provide:

- Auto-detect;
- Browse;
- Test;
- Open Folder.

Support Windows paths with spaces and non-ASCII characters.

Do not hard-code the user’s installation layout.

## ComfyUI adapter requirements

The adapter must:

1. connect only to a local configured ComfyUI instance by default;
2. verify backend health;
3. inspect actual node/object metadata;
4. import a verified API-format single-scene workflow;
5. map only verified workflow inputs;
6. upload or copy reference media safely;
7. submit the job;
8. store the real prompt/job ID;
9. listen to WebSocket/API events;
10. translate backend events into scene progress;
11. handle interruption;
12. find the actual output;
13. verify output with FFmpeg;
14. create a unique render version;
15. persist full render metadata;
16. display actual errors.

## Output and versioning

Never overwrite.

Example:

```text
Projects/
  Project_Name/
    project.json
    project.sqlite
    assets/
      characters/
      locations/
      references/
    scenes/
      scene_001/
        inputs/
        continuity/
        renders/
          v001/
            video.mp4
            metadata.json
          v002/
      scene_002/
    exports/
    previews/
    logs/
    temp/
```

Use collision-safe names.

## RAM, VRAM, and cache controls

Do not create a misleading generic “RAM Dump” button.

Provide accurately named actions only when real implementations exist:

- Unload Models
- Clear ComfyUI Execution Cache
- Empty CUDA Allocator Cache
- Restart ComfyUI Backend
- Clear App Temporary Files
- Clear Preview Cache
- Release Finished Job Resources
- Emergency Stop

Explain that:

- emptying CUDA cache does not guarantee all VRAM is released;
- unloading models is distinct from CUDA cache cleanup;
- deleting output files is distinct from execution cache;
- restarting ComfyUI is the reliable fallback when no supported cache endpoint exists.

Every action must:

- show its scope;
- require confirmation when destructive;
- report actual success or failure;
- avoid deleting outside app-owned temp/cache paths;
- never delete final renders automatically.

## Telemetry and privacy

Disable telemetry in the fork.

Do not transmit:

- prompts;
- reference images;
- videos;
- project metadata;
- hardware information;
- usage analytics.

Document the local-only privacy model.

## Editing roadmap

### Phase 1: reliable generation

- settings;
- projects;
- scene creation;
- 5/10/15/custom scene count;
- single-scene generation;
- Continue Previous;
- New Shot;
- prompt enhancement through template/Ollama;
- render queue;
- real progress;
- previews;
- versions;
- resource monitor;
- cache/model controls;
- concatenate selected scene versions;
- export MP4.

### Phase 2: lightweight editor

- trim in/out;
- scene reorder;
- transitions;
- music track;
- simple titles;
- final export.

### Phase 3: advanced editor

- multitrack timeline;
- detailed audio tools;
- subtitles;
- speed changes;
- filters;
- voice;
- lip sync;
- proxy workflow;
- partial regeneration.

Do not start Phase 2 until real MiniMax H3 rendering works end-to-end.

## Security

- Bind backend services to loopback by default.
- Do not execute arbitrary shell strings.
- Use process argument arrays.
- Validate imported workflow JSON.
- Validate all file operations.
- Prevent cache cleanup outside approved app directories.
- Do not log secrets.
- Do not retain cloud API code in an enabled production path.

## Definition of done

A feature is complete only when:

- implementation exists;
- real error handling exists;
- UI states exist;
- persistence survives restart;
- applicable tests pass;
- production build passes;
- manual verification steps are documented;
- no mock is presented as real;
- no cloud request is made.

## First vertical slice

Build and verify this before broad UI work:

1. Fork/clone LTX Desktop.
2. Rename development branding to H3 Director Desktop while preserving legal notices.
3. Disable API mode and telemetry.
4. Preserve existing app startup.
5. Add local ComfyUI settings and validation.
6. Import one verified MiniMax H3 single-scene API workflow.
7. Render one real image-to-video scene.
8. show real progress;
9. verify and preview the output;
10. create Scene 2;
11. extract a continuity frame from Scene 1;
12. render Scene 2 from that frame;
13. render 5 scenes sequentially;
14. verify every scene output and folder;
15. concatenate the selected versions into an MP4.

Do not claim the product works before this vertical slice passes.
