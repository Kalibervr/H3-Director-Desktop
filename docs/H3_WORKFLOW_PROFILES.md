# H3 workflow profiles and local model manifests

`minimax_h3_image_to_video` is the only active profile. Its manifest contains only the four model selections verified in `workflows/minimax_h3_single_scene_api.json`; source URLs and checksums are intentionally null until separately verified.

`minimax_h3_text_to_video` is intentionally unavailable. Before activation, H3 Director needs a real local ComfyUI API workflow, matching UI workflow if available, `/object_info` evidence, exact model filenames/categories, verified sources and checksums, plus a successful local render.

The model UI never downloads anything. A later model manager may only use verified profile manifests, configured shared local model paths, user-initiated downloads, fixed approved destination categories, and checksum verification.

RTX Video Super Resolution is also unavailable in this build. The installed KJNodes source exposes an `nvidia_rtx_vsr` image operation, but the configured runtime lacks `nvvfx`/`nvidia-vfx` and no verified video upscale workflow or output contract exists. The original H3 render is never modified; a future derived variant must record source render-version ID, backend, source/output resolution and settings.

Prompt Assistant is local-only. The current deterministic provider builds an editable suggestion from scene/continuity/audio context and never overwrites the user prompt. Optional Ollama support must remain loopback-only and needs separately verified configuration before it can be enabled.
