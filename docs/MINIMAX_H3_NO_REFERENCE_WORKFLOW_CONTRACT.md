# MiniMax H3 no-reference workflow contract

Status: **runtime verified through H3 Director for the exact configuration documented below.**

## Classification

This is **not a separately identified MiniMax H3 Text-to-Video model or node**. It is the installed `MiniMaxH3ImageToVideo` node used with neither optional keyframe connected. The template describes this path as `t2va`; H3 Director records it conservatively as the `minimax_h3_no_reference` profile rather than claiming a distinct product capability.

## Captured workflow

The exact captured visible source template is [minimax_h3_single_scene_ui.json](../workflows/minimax_h3_single_scene_ui.json), SHA-256 `7a9ff483fc2ab0b2c7a50278f276fc6d67d430c1dee78ace0c273df200ca698e`. Its MiniMax H3 group exposes `first_frame` and `last_frame`. The saved I2V instance links `LoadImage` node `114` to `105:104.first_frame`; it has no `last_frame` link.

The exact executed prompt-only API graph is [minimax_h3_no_reference_api.json](../workflows/minimax_h3_no_reference_api.json), SHA-256 `975e61acfa981b0268bd97e5d5fa72696d0f19a2ceedd18ccefdbea6cdaa5be1`. It intentionally omits node `114`, `105:104.inputs.first_frame`, and `105:104.inputs.last_frame`. Former disconnected utility nodes `119` and `120` are also absent.

Live ComfyUI `/object_info` verification found `MiniMaxH3ImageToVideo` in `comfy_extras.nodes_minimax_h3`, with these inputs:

| Input classification | Fields |
| --- | --- |
| Required | `clip`, `vae`, `prompt`, `width`, `height`, `length` |
| Optional | `first_frame`, `last_frame` |

All API-graph class types were confirmed present in the live local `/object_info`: `BasicGuider`, `BasicScheduler`, `CLIPLoader`, `ComfyMathExpression`, `CreateVideo`, `KSamplerSelect`, `MiniMaxH3ImageToVideo`, `RandomNoise`, `ResolutionSelector`, `SamplerCustomAdvanced`, `SaveVideo`, `UNETLoader`, `VAEDecode`, `VAEDecodeAudio`, and `VAELoader`.

## Exact mappings

| Concern | API node/input |
| --- | --- |
| Prompt | `105:104.inputs.prompt` |
| Optional images | omitted: `105:104.inputs.first_frame`, `105:104.inputs.last_frame` |
| Seed | `105:15.inputs.noise_seed` |
| Aspect ratio / megapixels / multiple | `115.inputs.aspect_ratio`, `.megapixels`, `.multiple` |
| Width / height | `105:104.inputs.width` = `115:0`; `.height` = `115:1` |
| Duration seconds | `105:111.inputs.value` |
| Frame count | `105:107` expression `max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17` -> `105:104.inputs.length` |
| FPS | `105:91.inputs.fps` |
| Video VAE | `105:11.inputs.vae_name` |
| Audio VAE | `105:24.inputs.vae_name` |
| Audio/video mux | `105:91` `CreateVideo`, with image output `105:10:0` and audio output `105:23:0` |
| Output | `92` `SaveVideo`; `outputs.92.images[]`, `type=output`, `animated=[true]` |

The captured graph uses `1:1 (Square)`, `0.4` megapixels, `multiple=32`, producing 640x640. It uses 5 seconds and the expression resolves this to 124 frames at 24 FPS. No other no-reference resolutions, durations, FPS values, modes, or models are verified by this contract.

## Required installed model selections

- `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (`UNETLoader`)
- `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (`CLIPLoader`, type `minimax`)
- `minimax_h3_video_vae_fp16.safetensors` (`VAELoader`)
- `minimax_h3_audio_vae_fp32.safetensors` (`VAELoader`)

## Single local execution evidence

The local loopback ComfyUI instance accepted prompt ID `67b4870d-4410-4a4c-bec8-3a72dbf8e2b7` with no image upload and no image node in the submitted graph. History reported success and output descriptor:

```text
filename: minimax_h3_no_reference_contract_00001_.mp4
subfolder: h3-director
type: output
animated: true
```

Resolved output: `C:\Users\carlj\AppData\Roaming\ComfyUI\output\h3-director\minimax_h3_no_reference_contract_00001_.mp4`.

Bundled `ffprobe` verified H.264 video at 640x640, `24/1` FPS, 124 video frames, 5.167 seconds, plus stereo AAC audio. The ComfyUI execution timestamps span 311.177 seconds. This validates that audio continues to be generated/muxed in the same `CreateVideo` path with no reference input.

## H3 Director product execution

H3 Director submitted the immutable Prompt Only graph through the normal project-render route on the managed loopback runtime. The request used no reference image and no `/upload/image` operation. ComfyUI returned prompt ID `cdf16557-4062-4761-965d-6f238559808b` and H3 Director adopted the result as the immutable project render version `v001`.

Bundled `ffprobe` verified H.264 video at 640x640, `24/1` FPS, 124 frames, 5.167 seconds, with audio present. The project-owned output is stored as `Scene01_v001.mp4` with `render-metadata.json`; metadata records `workflow_profile_id=minimax_h3_no_reference`, `model_family=MiniMax H3`, `mode=prompt_only`, and `reference_image_used=false`.

## Product scope and remaining work

`minimax_h3_no_reference` is now `runtime_verified` only for 1:1 / 640x640 / 24 FPS / 5 seconds / 124 frames and the four model selections above. The provider uses the strict Prompt Only payload seam, omits `/upload/image`, and uses the normal project versioning, preview, file actions, editor bridge, and RTX VSR-compatible render-version path. Existing `minimax_h3_image_to_video` behavior and reference-image/continuity semantics are unchanged. Image-based continuity, reference controls, and all other Prompt Only formats, resolutions, durations, FPS values, and model variants remain unavailable pending separate evidence.
