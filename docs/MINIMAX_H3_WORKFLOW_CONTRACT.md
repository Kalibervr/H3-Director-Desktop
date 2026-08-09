# MiniMax H3 Workflow Contract

Status: `READ_ONLY_PROBE_IMPLEMENTED_PROVIDER_NOT_IMPLEMENTED` as of 2026-08-09.

This contract records only facts present in the supplied repository evidence. It does not claim that the workflow has been submitted by H3 Director, that cancellation/progress/output retrieval has been verified, or that a provider is ready.

## Evidence reviewed

- `workflows/minimax_h3_single_scene_ui.json`: valid JSON; ComfyUI UI workflow version `0.4`, 9 top-level nodes, 5 links.
- `workflows/minimax_h3_single_scene_api.json`: valid JSON; API-format top-level node map with 20 node entries. Every entry has a string `class_type` and an `inputs` object; it has no UI `nodes` or `links` fields.
- `docs/comfyui_object_info.json`: valid JSON; contains metadata for all 19 unique `class_type` values used by the API workflow.
- `docs/custom_nodes_installed.txt`: inventory reports a ComfyUI tree under `D:\comfy desktop\ComfyUI (1)\ComfyUI` and seven third-party custom-node directories.
- `docs/minimax_model_files.txt`: inventory contains only placeholder/config files and does not list the four MiniMax model files by filesystem path.
- `test-assets/minimax-h3/single_scene_input.jpg`: readable MJPEG image, 1026x1031.
- `test-assets/minimax-h3/single_scene_verified_output.mp4`: readable output with video and audio streams; probe results are below.

## Live local runtime verification

The existing development instance was inspected read-only through `http://127.0.0.1:8188`; no prompt was submitted and the ComfyUI UI was not opened.

- `GET /system_stats`: HTTP 200.
- Listener: `127.0.0.1:8188` only in the observed `netstat` output.
- ComfyUI version: `0.30.2`.
- Frontend package: `1.47.12`; workflow templates: `0.11.31`; embedded docs: `0.5.9`.
- Python: `3.13.12`; PyTorch: `2.12.1+cu130`; device: NVIDIA GeForce RTX 5060 Ti.
- Runtime process: `D:\comfy desktop\ComfyUI (1)\standalone-env\python.exe`.
- ComfyUI tree reported by the process arguments: `D:\comfy desktop\ComfyUI (1)\ComfyUI`.
- `GET /queue`: HTTP 200 with empty running and pending queues at inspection time.
- `GET /history?max_items=1`: HTTP 200 and returned a completed MiniMax H3 execution described below.
- Live `/object_info` contained all 19 used classes and was semantically identical for those classes to `docs/comfyui_object_info.json`.

The existing external development instance was launched with the argument `--feature-flag enable_telemetry=true`. H3 Director did not launch or modify that process. This configuration is not acceptable for the standalone local-only production runtime: production launch arguments must explicitly disable telemetry and must not enable sign-in or other remote product features.

## API graph and provider-editable fields

The output ancestor graph terminates at output node `92`. API nodes `119` (`ImageScaleToTotalPixels`) and `120` (`GetImageSize`) are disconnected from that output graph and are not provider inputs.

| Field | Exact API node and input | Verified workflow value or connection |
|---|---|---|
| Prompt | `105:104.inputs.prompt` (`MiniMaxH3ImageToVideo`) | Multiline text including visual direction and an `Audio:` instruction. |
| Input image | `114.inputs.image` (`LoadImage`), connected from output 0 to `105:104.inputs.first_frame` | `Gemini_Generated_Image_12xfie12xfie12xf.png` |
| Last frame | `105:104.inputs.last_frame` | Optional in `/object_info`; absent from this API workflow. |
| Seed | `105:15.inputs.noise_seed` (`RandomNoise`) | `193554738272393` |
| Width | `105:104.inputs.width`, linked to output 0 of node `115` | Node `115`: `aspect_ratio="1:1 (Square)"`, `megapixels=0.4`, `multiple=32` |
| Height | `105:104.inputs.height`, linked to output 1 of node `115` | Same `ResolutionSelector` settings as width. |
| Duration input | `105:111.inputs.value` (`PrimitiveFloat`) | `5` seconds |
| Frame-count expression | `105:107.inputs.expression` (`ComfyMathExpression`) | `max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17`; `values.a` links to node `105:111`. For the supplied value, the expression yields 124 frames. |
| Model frame count | `105:104.inputs.length` | Linked to output 1 of node `105:107`. `/object_info` describes this as frame count at 24 FPS on a `17k+5` grid. |
| FPS | `105:91.inputs.fps` (`CreateVideo`) | `24` |
| Audio | `105:23` decodes samples from `105:14` with audio VAE `105:24`; its output connects to `105:91.inputs.audio` | Audio is always connected in this workflow. There is no separate enable/disable field. Audio content is described inside the prompt. |
| Output filename prefix | `92.inputs.filename_prefix` (`SaveVideo`) | `video/MiniMax_H3` |
| Output format/codec controls | `92.inputs.format`, `92.inputs.codec` | Both `auto` |

The UI workflow confirms links `114 -> 105.first_frame`, `115.width -> 105.width`, `115.height -> 105.height`, and `105.VIDEO -> 92.video`. The group node's displayed width/height widget values (`1344`, `768`) are overridden by the linked `ResolutionSelector` in this workflow and must not be treated as the API values.

## `/object_info` class cross-reference

All used classes were present. No missing `class_type` was found.

| `class_type` | Python module | Role |
|---|---|---|
| `BasicGuider` | `comfy_extras.nodes_custom_sampler` | guider |
| `BasicScheduler` | `comfy_extras.nodes_custom_sampler` | sigma schedule |
| `CLIPLoader` | `nodes` | text encoder loader |
| `ComfyMathExpression` | `comfy_extras.nodes_math` | seconds-to-frame expression |
| `CreateVideo` | `comfy_extras.nodes_video` | combines decoded frames and audio at 24 FPS |
| `GetImageSize` | `comfy_extras.nodes_images` | disconnected/inactive helper |
| `ImageScaleToTotalPixels` | `comfy_extras.nodes_post_processing` | disconnected/inactive helper |
| `KSamplerSelect` | `comfy_extras.nodes_custom_sampler` | sampler selection |
| `LoadImage` | `nodes` | first-frame loader |
| `MiniMaxH3ImageToVideo` | `comfy_extras.nodes_minimax_h3` | H3 conditioning and latent creation |
| `PrimitiveFloat` | `comfy_extras.nodes_primitive` | duration in seconds |
| `RandomNoise` | `comfy_extras.nodes_custom_sampler` | seed/noise |
| `ResolutionSelector` | `comfy_extras.nodes_resolution` | linked width/height source |
| `SamplerCustomAdvanced` | `comfy_extras.nodes_custom_sampler` | sampling |
| `SaveVideo` | `comfy_extras.nodes_video` | output node |
| `UNETLoader` | `nodes` | diffusion model loader |
| `VAEDecode` | `nodes` | video latent decoder |
| `VAEDecodeAudio` | `comfy_extras.nodes_audio` | audio latent decoder |
| `VAELoader` | `nodes` | video/audio VAE loader |

Because every active class resolves to ComfyUI core (`nodes`) or bundled `comfy_extras`, none of the installed third-party packages listed in `custom_nodes_installed.txt` is required by this workflow according to the supplied metadata. Exact ComfyUI commit/package version remains unknown.

## Required model files

The API workflow selects these exact filenames, and each appears in the corresponding `/object_info` loader choices:

| Loader node | Model filename | Verified local path and size |
|---|---|---|
| `105:6` `UNETLoader.inputs.unet_name` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `C:\Users\carlj\AppData\Roaming\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors` — 20,970,379,616 bytes |
| `105:13` `CLIPLoader.inputs.clip_name` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `C:\Users\carlj\AppData\Roaming\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` — 15,687,142,551 bytes |
| `105:11` `VAELoader.inputs.vae_name` | `minimax_h3_video_vae_fp16.safetensors` | `C:\Users\carlj\AppData\Roaming\ComfyUI\models\vae\minimax_h3_video_vae_fp16.safetensors` — 5,207,808,496 bytes |
| `105:24` `VAELoader.inputs.vae_name` | `minimax_h3_audio_vae_fp32.safetensors` | `C:\Users\carlj\AppData\Roaming\ComfyUI\models\vae\minimax_h3_audio_vae_fp32.safetensors` — 605,254,808 bytes |

The UI workflow contains declared Hugging Face download URLs for these files. Local presence and byte sizes are verified; cryptographic hashes, upstream provenance and licenses are not yet verified.

## Verified output probe

Probe executable:

`C:\Projects\H3-Director-Desktop\backend\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffprobe.exe`

`ffprobe` exited with code 0 for `test-assets/minimax-h3/single_scene_verified_output.mp4`.

| Property | Verified value |
|---|---|
| Video codec | H.264 (`h264`) |
| Width | 640 |
| Height | 640 |
| FPS | 24/1 (both average and reported frame rate) |
| Container duration | 5.167000 seconds |
| Video duration | 5.166667 seconds |
| Video frame count | 124 (`nb_frames` and counted `nb_read_frames`) |
| Audio stream | Present: AAC, stereo, 32000 Hz |
| Audio duration | 5.167000 seconds |

Live history prompt ID `06f1ce34-9740-4598-b136-2ce230ebc22c` completed successfully. Output node `92` reported `{filename: "MiniMax_H3_00015_.mp4", subfolder: "video", type: "output"}`. The live file at `C:\Users\carlj\AppData\Roaming\ComfyUI\output\video\MiniMax_H3_00015_.mp4` and the repository evidence MP4 are both 590,077 bytes and have the same SHA-256:

`91ADAC494F267195DEAA7E11F9EDA55A5C93267DB0B61AB8A1692A5E8A63B57D`

The executed history graph matches the supplied API graph except for two recorded differences: history used seed `168866841893410` instead of the API file's current `193554738272393`, and history omitted the empty `92.inputs.video-preview` field. The verified output is therefore provenance-linked to the recorded execution, but not to the API file's current seed value.

The history-referenced input exists at `C:\Users\carlj\AppData\Roaming\ComfyUI\input\Gemini_Generated_Image_12xfie12xfie12xf.png`; it is a 2816x1536 PNG, 7,631,107 bytes, SHA-256 `F83ACAA1C04759575B5A6FD1F116F2792919931C038D46AC0C0649B45367F7B8`. It is not the same file as `test-assets/minimax-h3/single_scene_input.jpg`, whose SHA-256 is `6E8A95C0FC94C1F25C844B3EFF02C0DF8824257351E556D3375302DDAF06EAAA`.

## Explicitly unresolved

- The exact ComfyUI source commit; the runtime reports version `0.30.2` only.
- A captured real `/prompt` request and its submission response from H3 Director. Existing history proves a prior external execution but does not document the submission response.
- Websocket connection/events, progress semantics, cancellation/interruption request and response, cache behavior and representative error payloads.
- The upload operation and server-side filename mapping from an H3 Director project image to `114.inputs.image`.
- The relationship between `test-assets/minimax-h3/single_scene_input.jpg` and the successful execution is unresolved; it differs from the history-referenced PNG.
- Output collision and numbering rules beyond the verified history descriptor `video/MiniMax_H3_00015_.mp4`.
- A user-facing audio enable/disable mapping; none exists in the workflow.
- Supported production bounds and validation policy for width, height, seconds and frame count beyond the raw `/object_info` constraints and workflow notes.
- Cryptographic hashes for all four model files.
- Verified upstream source, exact model version and license for each model file.
- Licensing/provenance details for the supplied input and output media.
- Exact versions/licenses of the installed third-party custom-node packages, although none is used by this graph according to `/object_info`.
- Production-safe ComfyUI launch arguments with telemetry, sign-in and remote features disabled. The inspected development process has telemetry explicitly enabled.
- Automatic discovery, launch, readiness timeout, ownership, restart, log redaction and clean shutdown behavior required by the standalone product constraint; production runtime bundling is intentionally out of scope for this phase.

## Implemented validation boundary

A tested, read-only `ComfyUIRuntimeProbe` and workflow-contract validator now enforce the verified boundary. They accept only loopback HTTP URLs; call only `/system_stats` and `/object_info`; validate all 19 node contracts, exact mapped inputs, audio/video links, output node and four model selections; return sanitized status; and mark telemetry-enabled production configuration incompatible. They do not upload an image, submit `/prompt`, expose the graph in the frontend, or manage/bundle the runtime.

Do not implement rendering yet. The next gate is evidence collection for upload naming, a real `/prompt` submission response, websocket/progress events, cancellation/interruption and representative error payloads. Provider submission remains blocked until those contracts are captured and reviewed.
