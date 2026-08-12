# LTX 2.5 Image-to-Video workflow contract

This document records only a successful local execution observed in the installed ComfyUI environment. It is not a claim that H3 Director can submit this workflow yet.

## Captured execution

- ComfyUI history prompt: `44a4d70d-9de0-4dc0-882d-d7129c53bf61`
- Mode: Image-to-Video. `LoadImage` node `395` supplies the starting image and the graph uses `LTXVImgToVideoInplace` nodes `398:357` and `398:349`.
- API workflow: `workflows/ltx_2_5_image_to_video_api.json` (SHA-256 `37865EF49D4F51F01365BBF362D7A57A294712DD8029620D86904AEAB2A0B0EA`). It is exported exactly from the completed prompt history and parses as a ComfyUI API node map.
- Observed configuration: `16:9 (Widescreen)`, `0.9` megapixels, `multiple=32`, `24` FPS, `5` seconds, native prompt enhancement on. A subsequent H3-originated output validation proved the actual encoded size is `1280×704`; H3 uses that output-verified size for this profile.
- The installed runtime successfully executed this exact distilled INT8 configuration on the local RTX 5060 Ti 16 GB. This does not prove support for other LTX checkpoints, dimensions, lengths, or modes.

## Verified input mapping

| Control | API node and field |
| --- | --- |
| Start image | `395.inputs.image` (`LoadImage`) |
| User prompt | `398:376.inputs.value` (`PrimitiveStringMultiline`) |
| Native prompt enhancement | `398:383.inputs.value` (`PrimitiveBoolean`), switching `398:382` between raw prompt and `398:380` |
| Prompt-enhancer model | `398:393.inputs.clip_name = gemma4_e2b_it_bf16.safetensors` |
| Aspect ratio / megapixels / multiple | `403.inputs.aspect_ratio`, `megapixels`, `multiple` (`ResolutionSelector`) |
| Width / height | `398:372` / `398:360` take the two outputs from `403`; latent dimensions are derived by `398:353` / `398:355` |
| Duration | `398:362.inputs.value` (seconds) |
| FPS | `398:361.inputs.value` |
| Video-frame count | `398:378.inputs.expression = a * b + 1`, using duration and FPS |
| Final sampling seed | `398:338.inputs.noise_seed` |
| Output prefix | `75.inputs.filename_prefix` (`SaveVideo`) |

The captured duration/FPS expression produces `121` frames for 5 seconds at 24 FPS. No app-side LTX submission has been verified.

## Models and active graph paths

The installed shared model paths resolve these locally present files:

- `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` via `398:384` (`UNETLoader`)
- `text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` via `398:387` (`CLIPLoader`)
- `text_encoders/gemma4_e2b_it_bf16.safetensors` via `398:393` (`CLIPLoader`)
- `vae/ltx-2.5-video-vae-bf16.safetensors` via `398:385` (`VAELoader`)
- `vae/ltx-2.5-audio-vae-bf16.safetensors` via `398:386` (`VAELoader`)
- `latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` via `398:371` (`LatentUpscaleModelLoader`)

The native latent upscaler is active: `398:371 → 398:348 (LTXVLatentUpsampler) → 398:349`. It is distinct from H3 Director's optional NVIDIA RTX VSR post-process.

## Output contract

`398:374` decodes video and `398:358` decodes audio. `398:370` creates the video with audio and `75` saves it. The captured history output is `{ filename: "LTX-2.5_i2v_00001_.mp4", subfolder: "video", type: "output" }`.

All 32 captured `class_type` values were present in live `/object_info`: `CLIPLoader`, `CLIPTextEncode`, `ComfyMathExpression`, `ComfySwitchNode`, `CreateVideo`, `EmptyLTXVLatentVideo`, `KSamplerSelect`, `LatentUpscaleModelLoader`, `LoadImage`, `LTXVAudioVAEDecode`, `LTXVConcatAVLatent`, `LTXVConditioning`, `LTXVDualCFGGuider`, `LTXVEmptyLatentAudio`, `LTXVImgToVideoInplace`, `LTXVLatentUpsampler`, `LTXVPreprocess`, `LTXVSeparateAVLatent`, `ManualSigmas`, `PrimitiveBoolean`, `PrimitiveInt`, `PrimitiveStringMultiline`, `RandomNoise`, `ResizeImageMaskNode`, `ResolutionSelector`, `SamplerCustomAdvanced`, `SaveVideo`, `TextGenerateLTX2Prompt`, `UNETLoader`, `VAEDecodeTiled`, and `VAELoader`.

## Boundaries and remaining work

The captured profile is an I2V workflow with native prompt enhancement and synchronized-audio decoding. One H3-originated local render was submitted, adopted as an immutable project render version, and ffprobe-verified. The metadata records workflow profile/version, captured model set, prompt-enhance state, dimensions, timing, seed, audio capability, input/output hashes, and ffprobe result.

The Text-to-Video template has not been captured from this installation and has not executed locally. It remains contract-only unavailable.

No additional LTX mode is enabled. The next step is a separately approved verification of another LTX configuration or mode; it must not broaden this profile automatically.
