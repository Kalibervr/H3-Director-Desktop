# H3 Director workflow profiles

H3 Director profiles are declarative local packages. They describe a verified model/workflow combination; they never execute profile-supplied Python, JavaScript, shell commands, or downloads.

## Active profile

`minimax_h3_image_to_video` is the first verified profile. It retains the established MiniMax H3 Image-to-Video workflow, 1:1/16:9/9:16 resolution tiers, fixed 24 FPS, frame constraints, reference fit, audio guidance, continuity, editor provenance, and RTX VSR derived-output compatibility.

Projects persist `workflow_profile_id` and `workflow_mode`. Schema 10 and older projects migrate atomically to schema 11 with `minimax_h3_image_to_video` / `image_to_video`; renders, continuity artifacts, editor links, and derived variants are unchanged.

## Package format

An installable local folder may contain only:

- `profile.json` — identity, version, capabilities, modes, and workflow references;
- `workflow_api.json` — API-format ComfyUI workflow;
- optional `workflow_ui.json`, `model-manifest.json`, and `README.md`.

`profile.json` schema version is currently `1`. Workflow paths must be fixed package-local filenames. Unknown schema versions, malformed modes, missing workflow JSON, path traversal, executable files, duplicate ID/version installs, and invalid model manifests are rejected. Installation copies validated declarative files into the app-managed profile directory and never overwrites an installed version.

## Model manifests

Entries declare stable ID, display name, role, expected filename, destination category, required state, and (only when verified) source, download URL, size, and SHA-256. The current MiniMax H3 manifest exposes the four verified required assets. The Models panel reports readiness/missing-model and node/compatibility states; it does not download models.

## Adding a future profile

Before enabling a new model, verify its local license/distribution terms, local checkpoint files, API workflow and UI workflow, `/object_info` nodes, required custom-node versions, model manifests/checksums, GPU/VRAM needs, supported formats/resolution/FPS/duration, audio contract, output contract, and one real local render. Only then add its declarative profile and enable its declared modes.

### LTX 2.5 checklist

Future IDs may be `ltx_2_5_image_to_video` and `ltx_2_5_text_to_video`. Neither is installed or selectable today. H3 must not invent LTX 2.5 checkpoints, nodes, URLs, hardware needs, or license terms. It needs the full verification checklist above before its profile is marked ready.

### Turbo and LoRA variants

Profiles may later declare verified variants and optional LoRAs, including compatible profile version, required model entry, strength/range, and explicitly mapped workflow parameters. A Turbo or LoRA option remains unavailable until its workflow, required sampler/steps changes, files, and output are verified locally.
