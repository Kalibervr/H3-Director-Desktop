# Codex Start Prompt — Fork LTX Desktop into H3 Director Desktop, Local Only

Read `AGENTS.md` completely before taking any action. Every rule in it is mandatory.

## Objective

Fork or clone:

```text
https://github.com/Lightricks/LTX-Desktop
```

and transform it into a new Windows-first desktop application called:

```text
H3 Director Desktop
```

The application must reuse the LTX Desktop shell and editor architecture where appropriate, but replace LTX-specific generation with a **fully local ComfyUI + MiniMax H3** generation backend.

Phase 1 must use no cloud generation and no external AI API.

## Local-only constraints

Do not use or require:

- LTX API;
- Gemini;
- fal.ai;
- OpenAI API;
- cloud text encoding;
- cloud prompt enhancement;
- cloud image generation;
- cloud video generation;
- accounts;
- credits;
- analytics;
- telemetry.

Prompt enhancement must be:

- deterministic local template;
- optional local Ollama;
- or disabled.

The application must remain usable without Ollama.

## Do not start coding blindly

Before modifying the repository:

1. inspect the repository structure;
2. read its `README.md`;
3. read its existing `AGENTS.md`;
4. inspect `LICENSE.txt` and `NOTICES.md`;
5. inspect the Electron, frontend, backend, shared, settings, editor, FFmpeg, generation, telemetry, API-mode, and test code;
6. identify all LTX-specific dependencies;
7. identify all external network calls;
8. identify all telemetry;
9. inspect the supplied MiniMax H3 ComfyUI workflow files;
10. create a written reuse audit.

Create:

```text
docs/LTX_REUSE_AUDIT.md
```

For each major subsystem classify it as:

```text
REUSE_AS_IS
REUSE_WITH_CHANGES
REPLACE
REMOVE
UNKNOWN_REQUIRES_TESTING
```

Do not implement the generation backend until this audit exists.

## Required architecture decision

Do not replace the entire repository with a new blank application.

Preserve the existing application shell where practical:

- Electron lifecycle;
- secure preload bridge;
- React frontend;
- project/media/editor infrastructure;
- local FastAPI backend;
- FFmpeg integration;
- settings and file dialogs;
- build and installer system;
- testing and performance tools.

Introduce a clean generation-provider boundary.

Create an interface conceptually equivalent to:

```text
GenerationProvider
└── ComfyUIMiniMaxH3Provider
```

Do not keep MiniMax integration mixed into LTX-specific model code.

## Core render design

Do not use one large multi-scene ComfyUI graph.

Use one verified single-scene MiniMax H3 API workflow for each scene job.

The app controls:

- number and order of scenes;
- reference images;
- continuity mode;
- previous-scene dependency;
- continuity-frame extraction;
- prompt construction;
- prompt enhancement;
- render queue;
- unique versions;
- retries;
- status;
- output folders;
- final assembly.

## Product requirements

### New project

Allow:

- 5 scenes;
- 10 scenes;
- 15 scenes;
- custom scene count.

Allow project defaults for:

- aspect ratio;
- resolution;
- FPS;
- seconds per scene;
- visual style;
- default continuity mode;
- project folder;
- prompt enhancement mode.

Generate the initial scene cards automatically.

### Scene modes

Every scene supports:

#### Continue Previous

Extract a verified final valid frame, or configured offset frame, from the selected previous scene render and use it as the next scene’s start image.

#### New Shot

Use the scene’s own reference image. Allow a completely different room, location, character, camera, lighting, or style.

#### Same Character, New Shot

Use the new shot setup plus selected character references when the verified workflow supports that input.

Do not promise perfect identity consistency.

### Director interface

Create an original premium dark cinematic interface.

Use:

- left asset and project library;
- large central video preview;
- storyboard/timeline scene cards;
- right Director panel;
- bottom render/resource status.

The user must not see ComfyUI nodes.

The selected scene panel must contain:

- simple prompt;
- enhanced prompt;
- exact final prompt;
- reference images;
- scene mode;
- character;
- location;
- shot framing;
- camera motion;
- subject action;
- mood;
- lighting;
- duration;
- resolution;
- FPS;
- seed;
- continuity source;
- continuity frame strategy;
- Render Scene;
- Render From Here;
- Render All;
- Retake;
- Duplicate;
- Cancel.

### Prompt Director

Build prompts from verified controls and project context.

Always display:

- original prompt;
- enhanced prompt;
- exact prompt sent to ComfyUI.

Local enhancement options:

```text
Template Only
Local Ollama
Disabled
```

Never hide prompt changes.

Never silently fall back to an online service.

### Settings

Add configuration for:

- ComfyUI root;
- ComfyUI executable or Python;
- local ComfyUI URL;
- ComfyUI input folder;
- ComfyUI output folder;
- models root;
- custom nodes folder;
- MiniMax H3 workflow JSON;
- MiniMax H3 model files when verified;
- FFmpeg;
- projects root;
- app temp/cache root;
- optional local Ollama endpoint/model.

Every path gets:

- Auto-detect;
- Browse;
- Test;
- Open Folder.

### Resource and maintenance panel

Show real values where supported:

- system RAM;
- app/backend process RAM;
- GPU;
- VRAM used/free/total;
- GPU load;
- GPU temperature when available;
- disk space;
- queue;
- active scene;
- ComfyUI status.

Add accurately named controls:

- Unload Models
- Clear ComfyUI Execution Cache
- Empty CUDA Allocator Cache
- Restart ComfyUI Backend
- Clear App Temporary Files
- Clear Preview Cache
- Release Finished Job Resources
- Emergency Stop

Do not create a generic fake “RAM Dump” or “VRAM Dump” button.

Verify every backend operation before enabling it.

## Data and versioning

Never overwrite.

Every render creates:

```text
scene_NNN/renders/vNNN/
```

Store:

- source prompt;
- enhanced prompt;
- final prompt;
- seed;
- dimensions;
- duration;
- FPS;
- model/workflow metadata;
- reference inputs;
- continuity source;
- start-frame metadata;
- ComfyUI job ID;
- timestamps;
- verified output details.

## Editing scope

Do not build a complete Clipchamp replacement in Phase 1.

Phase 1 may include:

- scene reorder;
- version selection;
- playback;
- simple trim;
- concatenation;
- MP4 export.

Architect for a later timeline with:

- transitions;
- music;
- text;
- subtitles;
- multitrack editing;
- speed;
- effects;
- voice;
- lip sync.

## Strict verification

Do not assume MiniMax H3 values or node mappings.

Before real rendering:

1. inspect the actual workflow JSON;
2. convert or confirm API format;
3. inspect ComfyUI node metadata;
4. document exact mapped fields;
5. verify prompt input;
6. verify image input;
7. verify duration;
8. verify resolution;
9. verify FPS;
10. verify seed behavior;
11. verify video output;
12. verify audio behavior;
13. verify interruption;
14. verify progress events.

Create:

```text
docs/MINIMAX_H3_WORKFLOW_CONTRACT.md
```

Include only verified information.

## First milestone

The first milestone is complete only when:

1. the fork starts under development;
2. API mode and telemetry are disabled;
3. the app connects to local ComfyUI;
4. one real MiniMax H3 scene renders;
5. actual progress is shown;
6. output exists and passes FFmpeg probing;
7. the result appears in the video preview;
8. a second scene uses an extracted frame from Scene 1;
9. a 5-scene project renders sequentially;
10. every scene creates a unique version;
11. selected versions concatenate into a final MP4;
12. type checking, backend tests, and production build pass.

## Required response before implementation

Before writing significant implementation code, provide:

1. repository structure summary;
2. reuse audit summary;
3. external network/API removal plan;
4. telemetry removal plan;
5. licensing obligations;
6. proposed provider boundary;
7. exact first vertical slice;
8. MiniMax information still required;
9. test strategy;
10. risk list;
11. commands that will be run.

Then create the documentation and make only the smallest safe scaffold changes.

Report actual command results. Do not claim work that was not executed.
