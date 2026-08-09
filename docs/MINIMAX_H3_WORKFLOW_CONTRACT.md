# MiniMax H3 Workflow Contract

Status: `BLOCKED_PENDING_VERIFICATION` as of 2026-08-09.

## Verified facts

- No MiniMax H3 or ComfyUI workflow JSON exists in the inspected repository.
- No ComfyUI installation path, running local API, node metadata, custom-node inventory, or MiniMax H3 model inventory was supplied in the repository.
- Therefore no endpoint behavior, node type, node ID, workflow input, model filename, supported resolution, duration, FPS, seed behavior, audio behavior, progress event, cancellation operation, cache operation, or output rule is verified.

## Contract gate

Renderer/provider binding must not begin until all of the following are captured from the user's actual local installation:

1. A single-scene API-format workflow JSON.
2. ComfyUI version/commit and loopback URL.
3. `/object_info` metadata for every workflow node.
4. Custom-node repositories and exact versions/licenses.
5. Model filenames, paths, versions/checksums, sources, and licenses.
6. Verified mappings for prompt, image, duration/frame count, dimensions, FPS, seed, output, and any audio controls.
7. Real submission, progress, history, output retrieval, interruption, and error samples.
8. A real output file that exists, is readable, and passes local FFmpeg/ffprobe inspection.

Until those gates pass, `ComfyUIMiniMaxH3Provider` may contain only transport-independent interfaces, configuration validation, and metadata/workflow validation scaffolding. It must not claim rendering support.
