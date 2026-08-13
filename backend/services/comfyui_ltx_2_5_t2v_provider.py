"""Strict local binding for the official LTX 2.5 Text-to-Video API workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlsplit

import requests

from server_utils.loopback_url import require_loopback_http_url
from services.comfyui_minimax_h3_provider import ProviderError, RenderResult, VideoProbe, probe_video
from services.ltx_2_5_geometry import is_ltx_product_validation_preset

JsonObject = dict[str, Any]
LTX_T2V_WORKFLOW_SHA256 = "237abb5a9e1c15fb1e29e5e22eecf2e17a84d23d7b06e3fd0ab18c2efadbd367"
LTX_T2V_OUTPUT_NODE_ID = "75"
LTX_T2V_MAPPING = {
    "prompt": "405:376", "prompt_enhance": "405:383", "duration": "405:362",
    "width": "405:372", "height": "405:360", "fps": "405:361", "seed": "405:339",
    "resolution": "409", "transformer": "405:384", "video_vae": "405:385",
    "audio_vae": "405:386", "text_encoder": "405:387", "enhancer": "405:393",
    "latent_upscale": "405:371", "create_video": "405:370", "output": "75",
}
LTX_T2V_MODELS = frozenset((
    "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "gemma4_e2b_it_bf16.safetensors", "ltx-2.5-video-vae-bf16.safetensors",
    "ltx-2.5-audio-vae-bf16.safetensors", "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
))
LTX_T2V_REQUIRED_NODES = frozenset((
    "CLIPLoader", "CLIPTextEncode", "ComfyMathExpression", "ComfySwitchNode", "CreateVideo",
    "EmptyLTXVLatentVideo", "KSamplerSelect", "LatentUpscaleModelLoader", "LTXVAudioVAEDecode",
    "LTXVConcatAVLatent", "LTXVConditioning", "LTXVDualCFGGuider", "LTXVEmptyLatentAudio",
    "LTXVLatentUpsampler", "LTXVSeparateAVLatent", "ManualSigmas", "PrimitiveBoolean", "PrimitiveInt",
    "PrimitiveStringMultiline", "RandomNoise", "ResolutionSelector", "SamplerCustomAdvanced", "SaveVideo",
    "TextGenerateLTX2Prompt", "UNETLoader", "VAEDecodeTiled", "VAELoader",
))


@dataclass(frozen=True)
class LtxT2VRequest:
    prompt: str
    prompt_enhance: bool
    seed: int
    aspect_ratio: str
    resolution_megapixels: float
    width: int
    height: int
    duration_seconds: float
    fps: int
    frame_count: int
    output_filename_prefix: str
    audio_guidance: str = ""


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ProviderError("The captured LTX 2.5 T2V workflow is invalid.")
    return cast(JsonObject, value)


def load_ltx_t2v_workflow(path: Path) -> JsonObject:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LTX_T2V_WORKFLOW_SHA256:
        raise ProviderError("The official LTX 2.5 T2V workflow has changed.")
    workflow = _object(json.loads(raw))
    if any(not isinstance(node, dict) or not isinstance(node.get("class_type"), str) for node in workflow.values()):
        raise ProviderError("The official LTX 2.5 T2V workflow is not API format.")
    return workflow


def validate_ltx_t2v_workflow(workflow: JsonObject, object_info: JsonObject) -> None:
    classes = {str(_object(node).get("class_type")) for node in workflow.values()}
    if not LTX_T2V_REQUIRED_NODES.issubset(classes) or any(name not in object_info for name in LTX_T2V_REQUIRED_NODES):
        raise ProviderError("Local ComfyUI is missing required LTX 2.5 T2V nodes.")
    serialized = json.dumps(workflow, sort_keys=True).lower()
    if "loadimage" in classes or any(value in serialized for value in ('"first_frame"', '"last_frame"', '"image"')):
        raise ProviderError("The LTX 2.5 T2V workflow must not contain an image dependency.")
    for node_id in LTX_T2V_MAPPING.values():
        if node_id not in workflow:
            raise ProviderError("The LTX 2.5 T2V workflow is missing a required contract node.")
    if _object(workflow[LTX_T2V_OUTPUT_NODE_ID]).get("class_type") != "SaveVideo":
        raise ProviderError("The LTX 2.5 T2V workflow output contract is invalid.")
    expected_models = {
        ("405:384", "unet_name"): "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
        ("405:385", "vae_name"): "ltx-2.5-video-vae-bf16.safetensors",
        ("405:386", "vae_name"): "ltx-2.5-audio-vae-bf16.safetensors",
        ("405:387", "clip_name"): "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
        ("405:393", "clip_name"): "gemma4_e2b_it_bf16.safetensors",
        ("405:371", "model_name"): "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
    }
    for (node_id, field), model in expected_models.items():
        if _object(workflow[node_id]).get("inputs", {}).get(field) != model:
            raise ProviderError("The LTX 2.5 T2V workflow model contract is invalid.")


def build_ltx_t2v_prompt_payload(template: JsonObject, request: LtxT2VRequest, client_id: str) -> JsonObject:
    if not request.prompt.strip():
        raise ProviderError("A prompt is required.")
    if not is_ltx_product_validation_preset(request.aspect_ratio, request.resolution_megapixels, request.width, request.height) or (request.fps, request.duration_seconds, request.frame_count) != (24, 5.0, 121) or not 0 <= request.seed <= 0xFFFFFFFFFFFFFFFF:
        raise ProviderError("Only the runtime-verified LTX configuration or an approved supervised validation preset is supported.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", request.output_filename_prefix):
        raise ProviderError("Output filename prefix contains unsupported characters.")
    workflow = copy.deepcopy(template)
    workflow["405:376"]["inputs"]["value"] = request.prompt.strip()
    workflow["405:383"]["inputs"]["value"] = request.prompt_enhance
    workflow["405:362"]["inputs"]["value"] = request.duration_seconds
    workflow["405:361"]["inputs"]["value"] = request.fps
    workflow["405:339"]["inputs"]["noise_seed"] = request.seed
    workflow["409"]["inputs"].update({"aspect_ratio": request.aspect_ratio, "megapixels": request.resolution_megapixels, "multiple": 32})
    workflow["75"]["inputs"]["filename_prefix"] = f"h3-director/{request.output_filename_prefix}_{client_id[:8]}"
    return {"prompt": workflow, "client_id": client_id}


def _discover_output(history: object, prompt_id: str, output_root: Path) -> Path | None:
    payload = _object(history)
    pending = payload.get(prompt_id)
    # ComfyUI returns an empty history object until it has finalized a prompt.
    # That is a normal polling state, not a malformed workflow response.
    if pending is None:
        return None
    record = _object(pending)
    status = _object(record.get("status"))
    if status.get("status_str") == "error":
        raise ProviderError("Local ComfyUI failed to render the LTX 2.5 T2V scene.")
    if status.get("completed") is not True:
        return None
    output = _object(_object(record.get("outputs")).get(LTX_T2V_OUTPUT_NODE_ID))
    entries = output.get("images")
    if not isinstance(entries, list):
        raise ProviderError("Local ComfyUI did not report the expected LTX T2V video output.")
    root = output_root.resolve()
    for entry in entries:
        descriptor = _object(entry)
        filename, subfolder = descriptor.get("filename"), descriptor.get("subfolder", "")
        if descriptor.get("type") != "output" or not isinstance(filename, str) or not filename.lower().endswith(".mp4") or not isinstance(subfolder, str):
            continue
        candidate = (root / subfolder / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProviderError("Local ComfyUI returned an unsafe LTX T2V output path.") from exc
        if candidate.is_file():
            return candidate
    raise ProviderError("Local ComfyUI completed without a readable LTX T2V MP4 output.")


class ComfyUILtx25T2VProvider:
    """Image-free, loopback-only execution binding for the official LTX 2.5 T2V export."""

    def __init__(self, *, workflow_path: Path, output_root: Path, render_root: Path, ffprobe_path: Path) -> None:
        self._workflow_path, self._output_root = workflow_path, output_root
        self._render_root, self._ffprobe_path = render_root, ffprobe_path
        self._session = requests.Session()

    def render(self, *, base_url: str, request: LtxT2VRequest, timeout_seconds: float = 1800.0) -> RenderResult:
        try:
            normalized = require_loopback_http_url(base_url)
            if urlsplit(normalized).scheme != "http": raise ValueError
        except ValueError as exc:
            raise ProviderError("ComfyUI URL must be a loopback HTTP address.") from exc
        workflow = load_ltx_t2v_workflow(self._workflow_path)
        self._validate_runtime(normalized, workflow)
        client_id = uuid.uuid4().hex
        payload = build_ltx_t2v_prompt_payload(workflow, request, client_id)
        started = time.monotonic()
        try:
            response = self._session.post(f"{normalized}/prompt", json=payload, timeout=30.0, allow_redirects=False)
            response.raise_for_status(); prompt_id = _object(response.json()).get("prompt_id")
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("The local LTX T2V prompt could not be submitted.") from exc
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ProviderError("Local ComfyUI did not return an LTX T2V prompt ID.")
        source: Path | None = None; deadline = started + timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = self._session.get(f"{normalized}/history/{quote(prompt_id, safe='')}", timeout=30.0, allow_redirects=False)
                response.raise_for_status(); source = _discover_output(response.json(), prompt_id, self._output_root)
            except ProviderError: raise
            except (requests.RequestException, ValueError) as exc: raise ProviderError("Local ComfyUI LTX T2V history is unavailable.") from exc
            if source is not None: break
            time.sleep(2.0)
        if source is None: raise ProviderError("The local LTX T2V render timed out.")
        video = probe_video(self._ffprobe_path, source)
        if (video.width, video.height, video.frame_count, video.audio_present) != (request.width, request.height, request.frame_count, True) or video.fps not in {"24", "24/1"} or abs(video.duration_seconds - request.duration_seconds) > .25:
            raise ProviderError("The LTX T2V output does not match the verified video and audio contract.")
        directory, output, metadata = self._adopt(source, prompt_id, request, video, time.monotonic() - started)
        return RenderResult(prompt_id, source, directory, output, metadata, video)

    def _validate_runtime(self, base_url: str, workflow: JsonObject) -> None:
        try:
            response = self._session.get(f"{base_url}/object_info", timeout=30.0, allow_redirects=False); response.raise_for_status(); info = _object(response.json())
        except (requests.RequestException, ValueError) as exc: raise ProviderError("Local ComfyUI LTX T2V compatibility metadata is unavailable.") from exc
        validate_ltx_t2v_workflow(workflow, info)
        option_checks = (("UNETLoader", "unet_name"), ("VAELoader", "vae_name"), ("CLIPLoader", "clip_name"), ("LatentUpscaleModelLoader", "model_name"))
        available = set()
        for class_type, field in option_checks:
            options = _object(info[class_type])["input"]["required"][field][0]
            if isinstance(options, list): available.update(options)
            elif class_type == "LatentUpscaleModelLoader": available.update(_object(info[class_type])["input"]["required"][field][1]["options"])
        if not LTX_T2V_MODELS.issubset(available): raise ProviderError("Local ComfyUI is missing a required LTX T2V model.")

    def _adopt(self, source: Path, prompt_id: str, request: LtxT2VRequest, video: VideoProbe, elapsed_seconds: float) -> tuple[Path, Path, Path]:
        self._render_root.mkdir(parents=True, exist_ok=True)
        for number in range(1, 10000):
            directory = self._render_root / f"v{number:03d}"
            try: directory.mkdir(); break
            except FileExistsError: continue
        else: raise ProviderError("No immutable LTX T2V render version slot is available.")
        output, metadata = directory / f"SceneLTXT2V_v{number:03d}.mp4", directory / "render-metadata.json"
        try:
            shutil.copy2(source, output)
            payload = {"schema_version": 1, "provider": "ComfyUILtx25T2VProvider", "created_at": datetime.now(UTC).isoformat(), "workflow_profile_id": "ltx_2_5_text_to_video", "mode": "text_to_video", "workflow_sha256": LTX_T2V_WORKFLOW_SHA256, "reference_image_used": False, "prompt_id": prompt_id, "prompt": request.prompt, "audio_guidance": request.audio_guidance, "prompt_enhance": request.prompt_enhance, "models": sorted(LTX_T2V_MODELS), "aspect_ratio": request.aspect_ratio, "resolution_megapixels": request.resolution_megapixels, "width": request.width, "height": request.height, "fps": request.fps, "duration_seconds": request.duration_seconds, "frame_count": request.frame_count, "seed": request.seed, "latent_upscale": {"enabled": True, "model": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"}, "audio_capability": "synchronized_audio_decode", "elapsed_seconds": elapsed_seconds, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "ffprobe": asdict(video)}
            temporary = directory / f".metadata.{uuid.uuid4().hex}.tmp"; temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8"); os.replace(temporary, metadata)
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True); raise ProviderError("The immutable LTX T2V render version could not be created.") from exc
        return directory, output, metadata
