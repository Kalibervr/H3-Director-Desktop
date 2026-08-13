"""Strict local binding for the captured LTX 2.5 Image-to-Video API workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import quote, urlsplit

import requests
from PIL import Image

from server_utils.loopback_url import require_loopback_http_url
from services.comfyui_minimax_h3_provider import ProviderError, RenderResult, VideoProbe, preprocess_reference_image, probe_video
from services.ltx_2_5_geometry import is_ltx_product_validation_preset

JsonObject = dict[str, Any]
LTX_I2V_WORKFLOW_SHA256 = "37865EF49D4F51F01365BBF362D7A57A294712DD8029620D86904AEAB2A0B0EA".lower()
LTX_I2V_OUTPUT_NODE_ID = "75"
LTX_I2V_REQUIRED_NODES = frozenset({
    "CLIPLoader", "CLIPTextEncode", "ComfyMathExpression", "ComfySwitchNode", "CreateVideo",
    "EmptyLTXVLatentVideo", "KSamplerSelect", "LatentUpscaleModelLoader", "LoadImage",
    "LTXVAudioVAEDecode", "LTXVConcatAVLatent", "LTXVConditioning", "LTXVDualCFGGuider",
    "LTXVEmptyLatentAudio", "LTXVImgToVideoInplace", "LTXVLatentUpsampler", "LTXVPreprocess",
    "LTXVSeparateAVLatent", "ManualSigmas", "PrimitiveBoolean", "PrimitiveInt",
    "PrimitiveStringMultiline", "RandomNoise", "ResizeImageMaskNode", "ResolutionSelector",
    "SamplerCustomAdvanced", "SaveVideo", "TextGenerateLTX2Prompt", "UNETLoader", "VAEDecodeTiled", "VAELoader",
})
LTX_I2V_MODELS = frozenset({
    "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "gemma4_e2b_it_bf16.safetensors",
    "ltx-2.5-video-vae-bf16.safetensors",
    "ltx-2.5-audio-vae-bf16.safetensors",
    "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
})


@dataclass(frozen=True)
class LtxI2VRequest:
    prompt: str
    input_image: Path
    seed: int
    prompt_enhance: bool
    aspect_ratio: str
    resolution_megapixels: float
    width: int
    height: int
    duration_seconds: float
    fps: int
    frame_count: int
    output_filename_prefix: str
    reference_fit: str = "fill_crop"


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ProviderError("Local ComfyUI returned an incompatible response.")
    return cast(JsonObject, value)


def load_ltx_i2v_workflow(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderError("The captured LTX 2.5 I2V workflow is unavailable.") from exc
    if hashlib.sha256(raw).hexdigest() != LTX_I2V_WORKFLOW_SHA256:
        raise ProviderError("The captured LTX 2.5 I2V workflow has changed.")
    try:
        workflow = _object(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("The captured LTX 2.5 I2V workflow is invalid.") from exc
    if not all(isinstance(node, dict) and isinstance(node.get("class_type"), str) for node in workflow.values()):
        raise ProviderError("The captured LTX 2.5 I2V workflow is not API format.")
    return workflow


def build_ltx_i2v_prompt_payload(template: JsonObject, request: LtxI2VRequest, staged_image_name: str, client_id: str) -> JsonObject:
    """Map only the node fields verified in the completed I2V history entry."""
    if not request.prompt.strip():
        raise ProviderError("A prompt is required.")
    if not is_ltx_product_validation_preset(request.aspect_ratio, request.resolution_megapixels, request.width, request.height) or (request.fps, request.duration_seconds, request.frame_count) != (24, 5.0, 121):
        raise ProviderError("Only the runtime-verified LTX configuration or an approved supervised validation preset is supported.")
    if request.seed < 0 or request.seed > 0xFFFFFFFFFFFFFFFF:
        raise ProviderError("Seed is outside the verified node range.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", request.output_filename_prefix):
        raise ProviderError("Output filename prefix contains unsupported characters.")
    staged = Path(staged_image_name)
    if not staged_image_name or staged.is_absolute() or ".." in staged.parts:
        raise ProviderError("Local ComfyUI returned an unsafe staged image name.")

    workflow = copy.deepcopy(template)
    workflow["395"]["inputs"]["image"] = staged_image_name.replace("\\", "/")
    workflow["398:376"]["inputs"]["value"] = request.prompt.strip()
    workflow["398:383"]["inputs"]["value"] = request.prompt_enhance
    workflow["403"]["inputs"].update({"aspect_ratio": request.aspect_ratio, "megapixels": request.resolution_megapixels, "multiple": 32})
    workflow["398:362"]["inputs"]["value"] = request.duration_seconds
    workflow["398:361"]["inputs"]["value"] = request.fps
    workflow["398:338"]["inputs"]["noise_seed"] = request.seed
    workflow["75"]["inputs"]["filename_prefix"] = f"h3-director/{request.output_filename_prefix}_{client_id[:8]}"
    return {"prompt": workflow, "client_id": client_id}


def _discover_ltx_output(history: object, prompt_id: str, output_root: Path) -> Path | None:
    record_value = _object(history).get(prompt_id)
    if record_value is None:
        return None
    record = _object(record_value)
    status = _object(record.get("status"))
    if status.get("status_str") == "error":
        raise ProviderError("Local ComfyUI failed to render the LTX scene.")
    if status.get("completed") is not True:
        return None
    output = _object(_object(record.get("outputs")).get(LTX_I2V_OUTPUT_NODE_ID))
    images = output.get("images")
    if not isinstance(images, list):
        raise ProviderError("Local ComfyUI did not report the expected LTX video output.")
    root = output_root.resolve()
    for item in images:
        descriptor = _object(item)
        filename, subfolder = descriptor.get("filename"), descriptor.get("subfolder", "")
        if descriptor.get("type") != "output" or not isinstance(filename, str) or not filename.lower().endswith(".mp4") or not isinstance(subfolder, str):
            continue
        candidate = (root / subfolder / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProviderError("Local ComfyUI returned an unsafe LTX output path.") from exc
        if candidate.is_file():
            return candidate
    raise ProviderError("Local ComfyUI completed without a readable LTX MP4 output.")


class ComfyUILtx25I2VProvider:
    """Loopback-only provider bound to one captured, verified LTX 2.5 I2V workflow."""

    def __init__(self, *, workflow_path: Path, output_root: Path, render_root: Path, ffprobe_path: Path) -> None:
        self._workflow_path = workflow_path
        self._output_root = output_root
        self._render_root = render_root
        self._ffprobe_path = ffprobe_path
        self._session = requests.Session()

    def render(self, *, base_url: str, request: LtxI2VRequest, timeout_seconds: float = 1800.0) -> RenderResult:
        try:
            normalized = require_loopback_http_url(base_url)
            if urlsplit(normalized).scheme != "http":
                raise ValueError
        except ValueError as exc:
            raise ProviderError("ComfyUI URL must be a loopback HTTP address.") from exc
        template = load_ltx_i2v_workflow(self._workflow_path)
        self._validate_runtime(normalized, template)
        if not request.input_image.is_file():
            raise ProviderError("The input image is unavailable.")
        try:
            with Image.open(request.input_image) as image:
                image.verify()
        except (OSError, ValueError) as exc:
            raise ProviderError("The input image is invalid.") from exc
        # The original remains immutable.  LTX gets the same exact-final-size
        # fit staging policy already used by the MiniMax I2V provider.
        staged_source = preprocess_reference_image(request.input_image, request.width, request.height, request.reference_fit)
        try:
            staged = self._upload_image(normalized, staged_source)
        finally:
            staged_source.unlink(missing_ok=True)
        client_id = uuid.uuid4().hex
        payload = build_ltx_i2v_prompt_payload(template, request, staged, client_id)
        try:
            response = self._session.post(f"{normalized}/prompt", json=payload, timeout=30.0, allow_redirects=False)
            response.raise_for_status()
            prompt_id = _object(response.json()).get("prompt_id")
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("The local LTX prompt could not be submitted.") from exc
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ProviderError("Local ComfyUI did not return an LTX prompt ID.")
        deadline = time.monotonic() + timeout_seconds
        source: Path | None = None
        while time.monotonic() < deadline:
            try:
                response = self._session.get(f"{normalized}/history/{quote(prompt_id, safe='')}", timeout=30.0, allow_redirects=False)
                response.raise_for_status()
                source = _discover_ltx_output(response.json(), prompt_id, self._output_root)
            except ProviderError:
                raise
            except (requests.RequestException, ValueError) as exc:
                raise ProviderError("Local ComfyUI LTX history is unavailable.") from exc
            if source is not None:
                break
            time.sleep(2.0)
        if source is None:
            raise ProviderError("The local LTX render timed out.")
        video = probe_video(self._ffprobe_path, source)
        if (video.width, video.height, video.frame_count, video.audio_present) != (request.width, request.height, request.frame_count, True):
            raise ProviderError("The LTX output does not match the verified video and audio contract.")
        if video.fps not in {"24/1", "24"} or abs(video.duration_seconds - 5.0) > 0.25:
            raise ProviderError("The LTX output does not match the verified timing contract.")
        render_dir, output, metadata = self._adopt(source, prompt_id, request, video)
        return RenderResult(prompt_id, source, render_dir, output, metadata, video)

    def _validate_runtime(self, base_url: str, workflow: JsonObject) -> None:
        try:
            response = self._session.get(f"{base_url}/object_info", timeout=30.0, allow_redirects=False)
            response.raise_for_status()
            info = _object(response.json())
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("Local ComfyUI LTX compatibility metadata is unavailable.") from exc
        classes = {str(_object(node).get("class_type")) for node in workflow.values()}
        if not LTX_I2V_REQUIRED_NODES.issubset(classes) or any(node not in info for node in LTX_I2V_REQUIRED_NODES):
            raise ProviderError("Local ComfyUI is missing required LTX 2.5 workflow nodes.")

    def _upload_image(self, base_url: str, image: Path) -> str:
        try:
            with image.open("rb") as stream:
                response = self._session.post(f"{base_url}/upload/image", files={"image": (image.name, stream, "application/octet-stream")}, data={"type": "input", "overwrite": "false"}, timeout=60.0, allow_redirects=False)
                response.raise_for_status()
                payload = _object(response.json())
        except (OSError, requests.RequestException, ValueError) as exc:
            raise ProviderError("The LTX input image could not be staged in local ComfyUI.") from exc
        name, subfolder = payload.get("name"), payload.get("subfolder", "")
        if not isinstance(name, str) or not isinstance(subfolder, str):
            raise ProviderError("Local ComfyUI returned an invalid LTX staged image response.")
        staged = str(Path(subfolder) / name) if subfolder else name
        if Path(staged).is_absolute() or ".." in Path(staged).parts:
            raise ProviderError("Local ComfyUI returned an unsafe LTX staged image name.")
        return staged

    def _adopt(self, source: Path, prompt_id: str, request: LtxI2VRequest, video: VideoProbe) -> tuple[Path, Path, Path]:
        self._render_root.mkdir(parents=True, exist_ok=True)
        for number in range(1, 10000):
            directory = self._render_root / f"v{number:03d}"
            try:
                directory.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise ProviderError("No immutable LTX render version slot is available.")
        output, metadata = directory / f"SceneLTX_v{number:03d}.mp4", directory / "render-metadata.json"
        try:
            shutil.copy2(source, output)
            payload = {
                "schema_version": 1, "provider": "ComfyUILtx25I2VProvider", "created_at": datetime.now(UTC).isoformat(),
                "workflow_profile_id": "ltx_2_5_image_to_video", "workflow_version": "2.5", "workflow_sha256": LTX_I2V_WORKFLOW_SHA256,
                "prompt_id": prompt_id, "prompt": request.prompt, "input_image_reference": str(request.input_image),
                "models": sorted(LTX_I2V_MODELS), "prompt_enhance": request.prompt_enhance,
                "aspect_ratio": request.aspect_ratio, "resolution_megapixels": request.resolution_megapixels,
                "width": request.width, "height": request.height, "fps": request.fps, "duration_seconds": request.duration_seconds,
                "frame_count": request.frame_count, "seed": request.seed, "audio_capability": "synchronized_audio_decode",
                "input_image_sha256": hashlib.sha256(request.input_image.read_bytes()).hexdigest(),
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "ffprobe": asdict(video),
            }
            temporary = directory / f".metadata.{uuid.uuid4().hex}.tmp"
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, metadata)
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise ProviderError("The immutable LTX render version could not be created.") from exc
        return directory, output, metadata
