# MiniMax H3 Workflow Contract

Status: `REAL_SINGLE_SCENE_PROVIDER_VERIFIED` as of 2026-08-09.

This contract records facts from the supplied repository evidence and verified H3 Director executions. H3 Director can run the immutable single-scene workflow in persisted project order through Render From Here or Render All, and manual continuity can derive its single input image from a completed previous-scene render. Neither behavior changes or extends the verified workflow controls. Verified ComfyUI WebSocket events provide truthful execution phases and sampler `value`/`max` progress; they do not provide a trustworthy global render percentage. In-flight ComfyUI cancellation, lifecycle management, restart recovery, cache control, and timeline orchestration are not implemented.

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

## Real H3 Director single-scene provider execution

The development-only `ComfyUIMiniMaxH3Provider` submitted one real render to the already running loopback runtime. The provider hash-verified the immutable API workflow, validated the runtime with the existing probe, uploaded one image, mapped only the verified controls, submitted `/prompt`, polled `/history/{prompt_id}`, resolved output node `92`, verified the MP4 with the bundled ffprobe, and created a collision-safe immutable version directory.

| Property | Verified value |
|---|---|
| Runtime URL | `http://127.0.0.1:8188` |
| Prompt ID | `96bad275-1b6f-48b2-bda3-a4df6286675b` |
| Input SHA-256 | `6E8A95C0FC94C1F25C844B3EFF02C0DF8824257351E556D3375302DDAF06EAAA` |
| Upload mapping | `/upload/image` returned a usable basename; history node `114.inputs.image` was `single_scene_input.jpg` |
| Seed | `193554738272393` |
| Resolution mapping | Request `640x640`; node `115` retained `aspect_ratio="1:1 (Square)"`, `megapixels=0.4`, `multiple=32`; width/height links remained `115` outputs 0/1 |
| Duration/frame mapping | `105:111.inputs.value=5.0`; verified expression produced 124 frames |
| FPS mapping | `105:91.inputs.fps=24` |
| Requested prefix | Provider-safe prefix under `h3-director/` |
| Actual descriptor | `filename="MiniMax_H3_c37be849_00001_.mp4"`, `subfolder="h3-director"`, `type="output"` |
| Source output SHA-256 | `A111284FDF9ECDACEF40D13EEBFA461EB31C8DE9C3FDBC8BB8BE69500D8EC164` |
| Immutable render | local app-data `development-renders/single-scene/renders/v001/video.mp4` |
| Metadata | local app-data `development-renders/single-scene/renders/v001/metadata.json` |

The supplied JPG is now proven as the input to this new provider execution by its metadata hash and the history mapping. It remains excluded from the earlier verified-output evidence commit because it did not produce the earlier `91AD...B57D` MP4.

### Sanitized API shapes

- `/upload/image` success: the provider verified string `name` and `subfolder` fields. The initial harness did not retain any additional response keys.
- `/prompt` request: top-level keys `prompt` and `client_id`; `prompt` contained the 20-node hash-verified API map. Raw graph and prompt content are not logged.
- `/prompt` success: the provider verified a non-empty string `prompt_id`. The initial harness did not retain any additional response keys.
- `/history/{prompt_id}` success: top-level key is the prompt ID; record keys are `prompt`, `outputs`, `status`, `meta`; status keys are `status_str`, `completed`, `messages`; output node `92` keys are `images`, `animated`; descriptor keys are `filename`, `subfolder`, `type`.
- Actual invalid empty `/prompt` request: HTTP 400; top-level keys `error`, `node_errors`; `error` keys `details`, `extra_info`, `message`, `type`; `node_errors` is an object. Raw server error text was not retained or logged.
- Provider success harness: `status`, `prompt_id`, `output_file`, `metadata_file`, `ffprobe`.
- Provider failures return fixed human-readable messages and do not include raw workflow JSON, prompts, image/model paths, response bodies, or environment data.

### Actual bundled-ffprobe verification

The new immutable `v001/video.mp4` and the ComfyUI source output are byte-identical with SHA-256 `A111284FDF9ECDACEF40D13EEBFA461EB31C8DE9C3FDBC8BB8BE69500D8EC164`.

| Property | Verified value |
|---|---|
| Codec | H.264 (`h264`) |
| Width / height | 640 / 640 |
| FPS | `24/1` |
| Duration | 5.167 seconds |
| Frame count | 124 |
| Audio stream | present |

## Explicitly unresolved

- The exact ComfyUI source commit; the runtime reports version `0.30.2` only.
- Additional `/upload/image` and successful `/prompt` response keys were not retained by the initial harness; only the fields consumed by the provider are verified.
- In-flight cancellation/interruption request and response semantics and cache-control behavior. The observed read-only WebSocket event schema is documented in `docs/COMFYUI_RENDER_PROGRESS_EVENTS.md`.
- Output collision and numbering rules beyond the two observed successful descriptors. The provider does not depend on ComfyUI numbering for its own immutable `vNNN` folders.
- A user-facing audio enable/disable mapping; none exists in the workflow.
- Supported production bounds and validation policy for width, height, seconds and frame count beyond the raw `/object_info` constraints and workflow notes.
- Cryptographic hashes for all four model files.
- Verified upstream source, exact model version and license for each model file.
- Licensing/provenance details for the supplied input and output media.
- Exact versions/licenses of the installed third-party custom-node packages, although none is used by this graph according to `/object_info`.
- Production-safe ComfyUI launch arguments with telemetry, sign-in and remote features disabled. The inspected development process has telemetry explicitly enabled.
- Automatic discovery, launch, readiness timeout, ownership, restart, log redaction and clean shutdown behavior required by the standalone product constraint; production runtime bundling is intentionally out of scope for this phase.

## Implemented provider boundary

A tested, read-only `ComfyUIRuntimeProbe` and workflow-contract validator enforce runtime compatibility. The development-only `ComfyUIMiniMaxH3Provider` adds one-image staging, one `/prompt` submission, history polling, safe output discovery, bundled-ffprobe verification, and immutable local render versioning. All ComfyUI connections are loopback HTTP. Neither component exposes the graph in the frontend or manages/bundles the runtime.

Do not infer additional workflow controls from this success. H3 Director owns the verified ordered queue, immutable per-scene versions, dependency resolution, and stop-after-current behavior outside the graph. Stop does not interrupt an already submitted ComfyUI prompt. Only the verified sampler `value`/`max` event is displayed as a percentage; other verified events map to phase labels without fabricated progress. In-flight prompt cancellation, lifecycle ownership, restart recovery, cache controls, and timeline orchestration remain outside this milestone. Continuity only selects an immutable ffmpeg-extracted previous-scene frame for the already documented input-image field.
