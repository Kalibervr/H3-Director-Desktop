# LTX Desktop Reuse Audit for H3 Director Desktop

Status: pre-implementation audit, 2026-08-09. This document records source inspection only. No MiniMax H3 renderer has been implemented or verified.

## Scope and baseline

The inspected source is the downloaded repository at `I:\H3-director desktop\H3-Director-Desktop-main`. It is a GitHub ZIP rather than a Git checkout (`.git` is absent). The repository is not a blank application and retains the LTX Desktop Electron, React, FastAPI, FFmpeg, project, editor, test, build, and installer foundations.

No MiniMax H3 or ComfyUI workflow JSON was found. `node_modules`, `backend/.venv`, `uv`, and a system `ffmpeg`/`ffprobe` are absent. The three required baseline commands were attempted before broad changes; all failed before reaching project checks because pnpm could not create `C:\Users\carlj\AppData\Local\pnpm` in the sandbox. Dependency installation and a true clean baseline remain required.

## Subsystem classifications

| Subsystem | Classification | Evidence and required action |
| --- | --- | --- |
| Electron main process | `REUSE_WITH_CHANGES` | `electron/main.ts` has sound lifecycle/handler/backend ownership structure. Remove analytics startup, change branding, and review updater behavior. |
| Preload bridge | `REUSE_WITH_CHANGES` | `electron/preload.ts` exposes a schema-driven IPC surface under context isolation. Extend with typed local ComfyUI/settings operations; retain renderer isolation. |
| React application shell | `REUSE_WITH_CHANGES` | `frontend/App.tsx`, views, contexts, hooks, and reusable UI components provide the shell. Replace LTX/account/credit/API-facing surfaces while preserving navigation and working features. |
| Project persistence | `REUSE_WITH_CHANGES` | Projects are Zod-validated and migrated but currently stored in renderer `localStorage` (`frontend/lib/project-storage.ts`). H3 scenes/version metadata and immutable artifacts need filesystem-backed persistence and collision-safe paths. |
| Video editor | `REUSE_AS_IS` initially | The editor contains timelines, playback, subtitles, effects, trims, retakes, and export integration. Preserve it; defer nonessential editor expansion until local generation works. LTX regeneration hooks later need provider integration. |
| Media library | `REUSE_WITH_CHANGES` | Project assets, takes, thumbnails, media import, and safe Electron file-copy handlers are reusable. Add H3 reference/character/location and generated-version semantics without deleting existing media behavior. |
| FFmpeg integration | `REUSE_WITH_CHANGES` | Electron uses argument arrays and provides export, audio detection, frame extraction, dimensions, and cancellation. Add explicit configurable FFmpeg/ffprobe validation and robust output probing; do not rely only on parsing `ffmpeg -i`. |
| Settings | `REUSE_WITH_CHANGES` | Electron/backend settings persistence and UI exist, but schemas contain LTX/Gemini/fal keys. Add local ComfyUI, workflow, model-path, project/cache, FFmpeg, and optional Ollama settings. Remove cloud credentials from enabled production paths. |
| Backend process management | `REUSE_WITH_CHANGES` | `electron/python-backend.ts` manages a loopback FastAPI process, auth/admin tokens, health checks, restart, and ownership. Preserve this and add a local ComfyUI client service rather than embedding ComfyUI internals into Electron. |
| Local model management | `REPLACE` for generation models | Existing Hugging Face download/scanning/license flows are LTX-specific and network-oriented. Phase 1 should validate user-configured local ComfyUI/MiniMax paths; no automatic cloud model downloads in production. Reuse generic path validation where suitable. |
| Render queue | `REUSE_WITH_CHANGES` | Existing generation state, background task runner, progress polling, cancellation, and recovery are useful patterns but coupled to one active LTX pipeline. Introduce scene jobs, dependencies, per-scene versions, and sequential scheduling at the app layer. |
| Progress reporting | `REUSE_WITH_CHANGES` | Existing REST polling/generation state can inform UI patterns. ComfyUI progress must be based on verified WebSocket/API events and translated without exposing raw graph internals. |
| Prompt enhancement | `REPLACE` | Current local Gemma and Gemini paths are LTX/catalog-specific, with Gemini able to transmit prompts/media. Phase 1 providers are deterministic template, optional loopback Ollama, or disabled. No silent fallback. |
| LTX generation code | `REPLACE` | LTX pipelines, encoders, model specs, LoRAs, retake, extend, and LTX API clients are not the H3 provider. Keep temporarily only until the provider boundary and removal tests make replacement safe; do not leave enabled production paths. |
| API mode | `REMOVE` | Runtime policy selects API-only modes and UI contains LTX/fal API-key, account, billing, upgrade, and API gateway surfaces. Phase 1 must have no API-only fallback or cloud generation. |
| Telemetry | `REMOVE` | `electron/analytics.ts` posts to `https://ltx-desktop.lightricks.com/v2/ingest`; it is enabled unless explicitly false and is invoked on app launch plus multiple UI events. Remove sender, call sites, preference/UI, stored installation ID, and endpoint allowance; add tests/static checks. |
| Installer | `REUSE_WITH_CHANGES` | Electron Builder/NSIS foundation is useful. Rename product/app IDs/shortcuts/assets and remove Lightricks signing/publishing configuration. Preserve license/notices in packaged files. |
| Updater | `UNKNOWN_REQUIRES_TESTING` | `electron/updater.ts` and GitHub publishing are tied to upstream Lightricks releases. Disable for the first local-only milestone or repoint only after a controlled H3 release channel exists. Verify that startup performs no update network call. |
| Tests | `REUSE_WITH_CHANGES` | Backend integration-first tests and service fakes are valuable. Remove/replace LTX API tests and add local-only egress, provider-contract, queue, versioning, cancellation, and output-verification tests. |
| Performance runner | `REUSE_WITH_CHANGES` | The headless runner already covers health, output integrity, GPU/RAM sampling, soak, and cold-start concepts. Adapt scenarios to ComfyUI jobs only after the workflow contract is verified. |
| Licenses and notices | `REUSE_WITH_CHANGES` | Preserve `LICENSE.txt`, relevant `NOTICES.md` entries, copyright/patent/trademark notices, and third-party attributions. Add prominent modification notices and MiniMax/ComfyUI/custom-node/model licenses after actual artifacts are identified. |

## Existing architecture

The renderer is React/TypeScript and calls a local FastAPI backend over loopback HTTP while privileged OS operations pass through the typed Electron preload bridge. Electron owns app lifecycle, native dialogs/file access, Python backend lifecycle, FFmpeg export, logging, updater, and telemetry. The Python backend uses thin FastAPI routes, a shared `AppHandler`, locked typed state, handlers for business logic, and injected services for GPU, IO, and network side effects. This separation is suitable for a new service/provider boundary.

Project/editor state is currently Zod-modeled and stored in `localStorage`; media files are copied beneath an app-owned project-assets directory through validated Electron IPC. H3 render metadata and immutable version folders require a stronger filesystem persistence layer, without discarding the existing editor model.

## Cloud, external API, account, and telemetry inventory

Production-relevant external paths found during inspection include:

- LTX API: `https://api.ltx.video`, used for generation/text encoding through runtime policy, LTX API client, settings, and API-mode UI.
- fal.ai: `https://fal.run`, API-key UI and Z Image generation/editing client.
- Google Gemini: `https://generativelanguage.googleapis.com/...`, prompt enhancement and gap suggestion paths that may include prompt context/media.
- Telemetry: `https://ltx-desktop.lightricks.com/v2/ingest`, enabled by default outside development and called on launch/events.
- Hugging Face: OAuth, license retrieval, model/LoRA discovery and downloads, catalog links/media, and remote license text.
- Lightricks/GCS/GitHub artifact downloads: Python bundles, models/catalog media, updater/releases, and remotely hosted preview assets.
- Remote UI resources: Google Fonts CSS/fonts, `videos.ltx.io`, and `storage.googleapis.com` are permitted by CSP; first-run CSS imports Google Fonts.
- Account/commerce surfaces: LTX Console API keys, billing/credit purchase links, Hugging Face OAuth, free-key/upgrade/API gateway components, and fal key links.
- Updater/publisher: upstream GitHub release configuration and `electron-updater` can create an external startup path.
- Development/install-only network paths: pnpm/PyPI/PyTorch/GitHub dependency sources. These may remain user-initiated development tasks but cannot become runtime requirements.

Removal must be structural, not merely hidden UI: cloud services must not be constructed by the production composition root, runtime policy must not select API mode, all call sites and credentials must be removed/disabled, CSP must allow only loopback/data/blob/file as required, remote fonts/assets must become local, telemetry sender and installation ID must be removed, and tests must fail on non-loopback runtime URLs.

## Licensing obligations

- Apache-2.0 permits modification and redistribution subject to including the license, marking modified files prominently, retaining relevant copyright/patent/trademark/attribution notices, and carrying forward applicable NOTICE content.
- Preserve relevant third-party notices and license texts for shipped dependencies. `NOTICES.md` includes Apache-2.0, MIT, BSD variants, MPL-2.0, ISC, HPND, and model-related notices; applicability must be re-evaluated as LTX dependencies are removed.
- Do not imply endorsement or official status by Lightricks or MiniMax; replace branding and upstream publisher/signing metadata without erasing required attribution.
- ComfyUI, MiniMax H3 model weights, workflow authorship, and every custom node have separate, currently unverified license obligations. Distribution decisions are blocked until exact repositories, versions, model files, and licenses are supplied and inspected.
- Maintain a written modification record and ensure source and packaged distributions include the required license/notices.

## Proposed local provider boundary

Keep orchestration outside ComfyUI and isolate protocol details behind narrow typed interfaces:

```text
Scene/Application orchestration
  -> GenerationProvider (submit, observe, cancel, resolve output)
       -> ComfyUIMiniMaxH3Provider
            -> ComfyUIClient (loopback HTTP/WebSocket only)
            -> VerifiedWorkflowContract (node IDs/types/input bindings)
            -> MediaStager (validated copies/uploads)
  -> OutputVerifier (local FFmpeg/ffprobe)
  -> RenderVersionRepository (immutable collision-safe folders + metadata)
```

The provider accepts app-domain values only after validation against the imported workflow contract. It must not know editor UI state or multi-scene sequencing. The app owns prompt assembly, scene dependencies, continuity extraction, queue/retry/cancel policy, version selection, folder layout, progress mapping, and concatenation. The client rejects non-loopback ComfyUI and Ollama URLs by default.

No endpoint, workflow field, node mapping, model path, supported duration/resolution/FPS, seed behavior, progress event, interruption operation, or output discovery rule is defined yet because none has been verified.

## MiniMax H3 information still required

The following exact evidence is missing and blocks renderer implementation:

1. The actual single-scene MiniMax H3 workflow JSON in ComfyUI API format (or UI workflow plus a verified API export).
2. The exact ComfyUI version/commit and local launch configuration/API base URL.
3. Full `/object_info` metadata for every node used by that workflow.
4. Exact custom-node repositories, commits/versions, installation state, and licenses.
5. Exact MiniMax H3 model filenames, paths relative to ComfyUI, versions/checksums, sources, and licenses.
6. Verified node IDs and fields for positive/negative prompt, reference/start image, seed, width, height, frame count or duration, FPS, sampler/settings, video/audio output, and output prefix.
7. Valid enumerations/ranges for image modes, duration/frame count, resolution/aspect ratio, FPS, batch, and seed semantics.
8. Whether same-character/new-shot accepts multiple character references and how they are bound.
9. Whether H3 produces audio, its codec/sample characteristics, and whether audio controls exist.
10. Real `/prompt`, `/history`, `/view`, upload, WebSocket progress/execution/error, queue, and interrupt behavior for the installed ComfyUI version.
11. Actual output node/type, filenames/subfolders, metadata, completion signal, and a sample output that passes local FFmpeg/ffprobe.
12. Measured GPU/VRAM behavior plus verified supported model unload/cache operations; no cleanup control can be enabled from assumptions.

## First vertical slice

The smallest coding slice after environment/workflow verification is: preserve startup; remove telemetry launch/call sites and disable updater/API-mode composition; add typed local ComfyUI settings with loopback validation; add a health/object-metadata probe service and tests; import and validate the supplied single-scene API workflow without yet submitting it. Then, using the verified contract, submit one image-to-video scene, map real progress, cancel through the verified API, locate the actual output, probe it with FFmpeg/ffprobe, create an immutable `v001` folder plus metadata, and show it in the existing preview. Only after that passes should continuity Scene 2, five-scene sequencing, and concatenation be added.

The exact next coding change is intentionally smaller: add a production local-only guard plus tests that rejects non-loopback provider URLs, and remove/disable the telemetry startup path. This must follow a clean passing baseline and creation of the verified workflow contract.

## Test strategy and risks

Tests should cover schema/URL/path validation, production composition containing no cloud clients, static/runtime egress allow-listing, workflow-contract validation, fake ComfyUI protocol behavior, queue/dependency transitions, cancellation races, unique version allocation, restart persistence, continuity provenance, output probing, missing/corrupt files, and path traversal. Existing backend integration tests and TypeScript typecheck/build remain mandatory. Real ComfyUI/H3/FFmpeg verification is a separate local integration gate and cannot be mocked as product success.

Principal risks are undocumented workflow/custom-node contracts, model and custom-node licensing, unsafe non-loopback configuration, confusing ComfyUI progress with model progress, cancellation leaving outputs/state behind, localStorage durability limits, Windows paths with spaces/non-ASCII characters, output races/collisions, missing ffprobe, updater/remote assets causing hidden egress, and accidentally breaking mature editor/export behavior during LTX removal.

## Commands and actual baseline results

- `pnpm typecheck` — failed before type checking: pnpm attempted to create `C:\Users\carlj\AppData\Local\pnpm` and received `EPERM`; dependencies are absent.
- `pnpm backend:test` — failed before tests for the same pnpm store `EPERM`; `uv` is also absent from `PATH`.
- `pnpm build` — failed before build for the same pnpm store `EPERM`; dependencies are absent.
- `ffmpeg -version` — command not found in `PATH`. The project can later use `imageio-ffmpeg` from its Python environment, but that environment is absent.

Required next environment commands, after permission and tool installation, are `pnpm setup:dev`, followed by `pnpm typecheck`, `pnpm backend:test`, and `pnpm build`. Results must be recorded exactly before broad implementation.
