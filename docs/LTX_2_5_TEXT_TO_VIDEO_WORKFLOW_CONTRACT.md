# LTX 2.5 Text-to-Video workflow contract

The executable contract is `workflows/ltx_2_5_text_to_video_api_official.json` (SHA-256 `237abb5a9e1c15fb1e29e5e22eecf2e17a84d23d7b06e3fd0ab18c2efadbd367`). It is a genuine ComfyUI **Export (API)** of the user-saved `Text to Video (LTX-2.5)` subgraph.

`workflows/ltx_2_5_text_to_video_ui.json` is the UI evidence. `workflows/ltx_2_5_text_to_video_api.json` is retained unchanged as historical manually flattened evidence and is not executable.

## Verified initial configuration

- `16:9 (Widescreen)`, `0.9` MP, `multiple=32`
- generated resolution: 1280 × 704
- 24 FPS, 5 seconds, 121 frames (`duration × FPS + 1`)
- native Prompt Enhance: enabled
- two `euler_ancestral` stages; latent x2 upscale; synchronized audio decode and `CreateVideo`.

## Executable mappings

| Control | API mapping |
| --- | --- |
| Prompt | `405:376.inputs.value` |
| Prompt Enhance | `405:383.inputs.value` |
| Duration | `405:362.inputs.value` |
| Resolution | `409.inputs.aspect_ratio`, `megapixels`, `multiple`; feeds `405:372`/`405:360` |
| FPS | `405:361.inputs.value` |
| Seed | `405:339.inputs.noise_seed` |
| Video/audio output | `405:358 → 405:370 → 75` |

The graph contains no `LoadImage`, image input, first frame, or last frame. The T2V provider must never upload or stage an image.

## Profile integration status

`ltx_2_5_text_to_video` now has an image-free payload, strict contract preflight,
and normal project-version adoption seam. Its persisted initial scene configuration
is independently locked to the API-exported contract: 16:9 / 0.9 MP / 1280×704 /
24 FPS / 5 seconds / 121 frames, with native Prompt Enhance enabled. It remains
**runtime verified and enabled** only for the captured 16:9 / 0.9 MP / 1280×704 /
24 FPS / 5-second / 121-frame configuration. Other resolutions, durations, FPS
values, multishot, first/last-frame, V2V, and continue/extend remain unavailable.

The project metadata seam records the profile ID, `text_to_video` mode,
`reference_image_used=false`, official workflow hash, prompt, composed local audio
guidance, native Prompt Enhance setting, model list, sampled settings, latent
upscale state, prompt ID, elapsed time, output hash, and ffprobe result.
