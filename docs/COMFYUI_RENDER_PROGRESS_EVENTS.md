# Verified ComfyUI render progress events

Captured on 2026-08-10 from the configured loopback-only ComfyUI 0.30.2 runtime during one successful verified MiniMax H3 render and one controlled invalid-image failure. The capture used the same `client_id` for `/ws?clientId=...` and `/prompt`. Prompts, workflow JSON, paths, output payloads, exception messages, and tracebacks were not retained.

## Observed successful event schemas

| Event | Observed `data` fields |
| --- | --- |
| `status` | `status.exec_info.queue_remaining`, `sid` |
| `execution_start` | `prompt_id`, `timestamp` |
| `execution_cached` | `nodes`, `prompt_id`, `timestamp` |
| `progress_state` | `prompt_id`, `nodes` |
| `executing` | `node`, `display_node`, `prompt_id` |
| `progress` | `value`, `max`, `prompt_id`, `node` |
| `executed` | `node`, `display_node`, `output`, `prompt_id` |
| `execution_success` | `prompt_id`, `timestamp` |

Each observed `progress_state.data.nodes` entry contained `value`, `max`, `state`, `node_id`, `prompt_id`, `display_node_id`, `parent_node_id`, and `real_node_id`.

Only node `105:14` (`SamplerCustomAdvanced`) emitted `progress` during the successful run. It emitted 20 events with integer `value`/`max`, from `1/20` through `20/20`. This is the only verified source for a user-visible percentage. It represents sampler progress, not whole-render progress.

The observed execution-node sequence was:

1. `105:104` — `MiniMaxH3ImageToVideo`
2. `105:16` — `BasicGuider`
3. `105:15` — `RandomNoise`
4. `105:14` — `SamplerCustomAdvanced`
5. `105:23` — `VAEDecodeAudio`
6. `105:10` — `VAEDecode`
7. `105:91` — `CreateVideo`
8. `92` — `SaveVideo`

## Observed failure schema

The controlled invalid-image execution emitted `execution_error` at node `114` (`LoadImage`) with fields `prompt_id`, `node_id`, `node_type`, `executed`, `exception_message`, `exception_type`, `traceback`, `current_inputs`, `current_outputs`, and `timestamp`. The exception type was `PIL.UnidentifiedImageError`.

The product may retain the safe node type and exception type for diagnostics. It must not persist or expose raw exception messages, tracebacks, workflow payloads, prompts, inputs, outputs, or paths from this event.

No interruption or cancellation event was observed. Stop-after-current therefore remains app-owned queue behavior and must not be presented as in-flight ComfyUI cancellation.

## User-visible mapping

| Evidence | UI phase | Percentage |
| --- | --- | --- |
| submission / `execution_start` / `execution_cached` | Preparing | none |
| executing `105:104`, `105:16`, or `105:15` | Preparing generation | none |
| executing/progress `105:14` | Sampling | `value / max` only |
| executing `105:23` or `105:10` | Decoding | none |
| executing `105:91` or `92`, or executed `92` | Encoding | none |
| `execution_success`, followed by local output discovery | Verifying | none |
| bundled ffprobe and immutable copy complete | Complete | none |
| `execution_error` | Failed | none |

Percentages must be cleared when leaving the sampler phase and must never be extrapolated, smoothed, or treated as whole-run completion.
