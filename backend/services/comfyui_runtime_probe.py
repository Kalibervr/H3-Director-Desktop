"""Read-only local ComfyUI capability probe and MiniMax H3 workflow validator."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, cast
from urllib.parse import urlsplit

import requests

from server_utils.loopback_url import require_loopback_http_url

JsonObject: TypeAlias = dict[str, Any]
ProbeState: TypeAlias = Literal["connected", "unavailable", "incompatible"]

REQUIRED_CLASS_INPUTS: dict[str, frozenset[str]] = {
    "BasicGuider": frozenset({"model", "conditioning"}),
    "BasicScheduler": frozenset({"model", "scheduler", "steps", "denoise"}),
    "CLIPLoader": frozenset({"clip_name", "type"}),
    "ComfyMathExpression": frozenset({"expression", "values"}),
    "CreateVideo": frozenset({"images", "fps"}),
    "GetImageSize": frozenset({"image"}),
    "ImageScaleToTotalPixels": frozenset({"image", "upscale_method", "megapixels", "resolution_steps"}),
    "KSamplerSelect": frozenset({"sampler_name"}),
    "LoadImage": frozenset({"image"}),
    "MiniMaxH3ImageToVideo": frozenset({"clip", "vae", "prompt", "width", "height", "length"}),
    "PrimitiveFloat": frozenset({"value"}),
    "RandomNoise": frozenset({"noise_seed"}),
    "ResolutionSelector": frozenset({"aspect_ratio", "megapixels", "multiple"}),
    "SamplerCustomAdvanced": frozenset({"noise", "guider", "sampler", "sigmas", "latent_image"}),
    "SaveVideo": frozenset({"video", "filename_prefix", "format", "codec"}),
    "UNETLoader": frozenset({"unet_name", "weight_dtype"}),
    "VAEDecode": frozenset({"samples", "vae"}),
    "VAEDecodeAudio": frozenset({"samples", "vae"}),
    "VAELoader": frozenset({"vae_name"}),
}

REQUIRED_OPTIONAL_CLASS_INPUTS: dict[str, frozenset[str]] = {
    "CreateVideo": frozenset({"audio"}),
    "MiniMaxH3ImageToVideo": frozenset({"first_frame", "last_frame"}),
}

REQUIRED_MODELS: dict[str, tuple[str, str]] = {
    "minimax_h3_fl2va_pruned_int8_convrot.safetensors": ("UNETLoader", "unet_name"),
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors": ("CLIPLoader", "clip_name"),
    "minimax_h3_video_vae_fp16.safetensors": ("VAELoader", "vae_name"),
    "minimax_h3_audio_vae_fp32.safetensors": ("VAELoader", "vae_name"),
}

EXPECTED_WORKFLOW_NODES: dict[str, tuple[str, frozenset[str]]] = {
    "92": ("SaveVideo", frozenset({"filename_prefix", "format", "codec", "video"})),
    "114": ("LoadImage", frozenset({"image"})),
    "115": ("ResolutionSelector", frozenset({"aspect_ratio", "megapixels", "multiple"})),
    "105:11": ("VAELoader", frozenset({"vae_name"})),
    "105:24": ("VAELoader", frozenset({"vae_name"})),
    "105:23": ("VAEDecodeAudio", frozenset({"samples", "vae"})),
    "105:10": ("VAEDecode", frozenset({"samples", "vae"})),
    "105:17": ("KSamplerSelect", frozenset({"sampler_name"})),
    "105:9": ("BasicScheduler", frozenset({"scheduler", "steps", "denoise", "model"})),
    "105:14": ("SamplerCustomAdvanced", frozenset({"noise", "guider", "sampler", "sigmas", "latent_image"})),
    "105:16": ("BasicGuider", frozenset({"model", "conditioning"})),
    "105:6": ("UNETLoader", frozenset({"unet_name", "weight_dtype"})),
    "105:13": ("CLIPLoader", frozenset({"clip_name", "type", "device"})),
    "105:15": ("RandomNoise", frozenset({"noise_seed"})),
    "105:91": ("CreateVideo", frozenset({"fps", "bit_depth", "images", "audio"})),
    "105:104": (
        "MiniMaxH3ImageToVideo",
        frozenset({"prompt", "width", "height", "length", "clip", "vae", "first_frame"}),
    ),
    "105:107": ("ComfyMathExpression", frozenset({"expression", "values.a"})),
    "105:111": ("PrimitiveFloat", frozenset({"value"})),
}

REQUIRED_LINKS: tuple[tuple[str, str, list[object]], ...] = (
    ("92", "video", ["105:91", 0]),
    ("105:91", "images", ["105:10", 0]),
    ("105:91", "audio", ["105:23", 0]),
    ("105:104", "first_frame", ["114", 0]),
    ("105:104", "width", ["115", 0]),
    ("105:104", "height", ["115", 1]),
    ("105:104", "length", ["105:107", 1]),
    ("105:107", "values.a", ["105:111", 0]),
)


@dataclass(frozen=True)
class WorkflowValidation:
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeProbeResult:
    status: ProbeState
    comfyui_version: str | None
    required_nodes_present: tuple[str, ...]
    required_nodes_missing: tuple[str, ...]
    required_models_present: tuple[str, ...]
    required_models_missing: tuple[str, ...]
    workflow_contract_valid: bool
    errors: tuple[str, ...]


def _as_object(value: object) -> JsonObject | None:
    return cast(JsonObject, value) if isinstance(value, dict) else None


def _input_names(class_info: JsonObject, group: str) -> set[str]:
    input_info = _as_object(class_info.get("input")) or {}
    fields = _as_object(input_info.get(group)) or {}
    return set(fields)


def _combo_options(object_info: JsonObject, class_type: str, input_name: str) -> set[str]:
    class_info = _as_object(object_info.get(class_type)) or {}
    required = _as_object((_as_object(class_info.get("input")) or {}).get("required")) or {}
    spec = required.get(input_name)
    if not isinstance(spec, list) or not spec or not isinstance(spec[0], list):
        return set()
    options = cast(list[object], spec[0])
    return {item for item in options if isinstance(item, str)}


def _is_api_node(value: object) -> bool:
    node = _as_object(value)
    return node is not None and isinstance(node.get("class_type"), str) and isinstance(node.get("inputs"), dict)


def validate_workflow_contract(workflow: object, object_info: object) -> WorkflowValidation:
    errors: list[str] = []
    workflow_object = _as_object(workflow)
    object_info_object = _as_object(object_info)
    if not workflow_object or not all(_is_api_node(node) for node in workflow_object.values()):
        return WorkflowValidation(False, ("Workflow is not a valid ComfyUI API-format node map.",))
    if object_info_object is None:
        return WorkflowValidation(False, ("ComfyUI node metadata is not a JSON object.",))

    workflow_classes = {cast(str, node["class_type"]) for node in workflow_object.values()}
    if not set(REQUIRED_CLASS_INPUTS).issubset(workflow_classes):
        errors.append("Workflow does not contain every required node type.")
    if not set(REQUIRED_CLASS_INPUTS).issubset(object_info_object):
        errors.append("ComfyUI node metadata is missing required node types.")

    for node_id, (expected_class, expected_inputs) in EXPECTED_WORKFLOW_NODES.items():
        node = _as_object(workflow_object.get(node_id))
        if node is None or node.get("class_type") != expected_class:
            errors.append("Workflow contract has a missing or changed required node.")
            continue
        inputs = _as_object(node.get("inputs")) or {}
        if not expected_inputs.issubset(inputs):
            errors.append("Workflow contract has a missing required input field.")

    for node_id, input_name, expected_link in REQUIRED_LINKS:
        node = _as_object(workflow_object.get(node_id)) or {}
        inputs = _as_object(node.get("inputs")) or {}
        if inputs.get(input_name) != expected_link:
            errors.append("Workflow contract has a changed required audio/video connection.")

    output_node = _as_object(workflow_object.get("92")) or {}
    if output_node.get("class_type") != "SaveVideo":
        errors.append("Workflow output node is missing or incompatible.")

    for filename, (node_id, input_name) in {
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors": ("105:6", "unet_name"),
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors": ("105:13", "clip_name"),
        "minimax_h3_video_vae_fp16.safetensors": ("105:11", "vae_name"),
        "minimax_h3_audio_vae_fp32.safetensors": ("105:24", "vae_name"),
    }.items():
        node = _as_object(workflow_object.get(node_id)) or {}
        inputs = _as_object(node.get("inputs")) or {}
        if inputs.get(input_name) != filename:
            errors.append("Workflow contract has a changed required model selection.")

    for class_type, required_fields in REQUIRED_CLASS_INPUTS.items():
        class_info = _as_object(object_info_object.get(class_type))
        if class_info is None:
            continue
        if not required_fields.issubset(_input_names(class_info, "required")):
            errors.append("ComfyUI node metadata is missing required input fields.")
        optional_fields = REQUIRED_OPTIONAL_CLASS_INPUTS.get(class_type, frozenset())
        if not optional_fields.issubset(_input_names(class_info, "optional")):
            errors.append("ComfyUI node metadata is missing required optional media fields.")

    save_video_info = _as_object(object_info_object.get("SaveVideo")) or {}
    if save_video_info.get("output_node") is not True:
        errors.append("ComfyUI SaveVideo is not advertised as an output node.")

    return WorkflowValidation(not errors, tuple(dict.fromkeys(errors)))


def _requests_get_json(url: str, timeout_seconds: float) -> object:
    response = requests.get(url, timeout=timeout_seconds, allow_redirects=False)
    if response.is_redirect:
        raise ValueError("Unexpected redirect")
    response.raise_for_status()
    return response.json()


class ComfyUIRuntimeProbe:
    """Development-only read probe; it never owns or mutates the ComfyUI process."""

    def __init__(self, get_json: Callable[[str, float], object] = _requests_get_json) -> None:
        self._get_json = get_json

    def probe(
        self,
        *,
        base_url: str,
        workflow: object,
        production_runtime: bool = False,
        timeout_seconds: float = 5.0,
    ) -> RuntimeProbeResult:
        try:
            normalized_url = require_loopback_http_url(base_url)
            if urlsplit(normalized_url).scheme != "http":
                raise ValueError("Only loopback HTTP URLs are allowed")
        except ValueError:
            return RuntimeProbeResult(
                status="incompatible",
                comfyui_version=None,
                required_nodes_present=(),
                required_nodes_missing=tuple(sorted(REQUIRED_CLASS_INPUTS)),
                required_models_present=(),
                required_models_missing=tuple(sorted(REQUIRED_MODELS)),
                workflow_contract_valid=False,
                errors=("ComfyUI URL must be a loopback HTTP address.",),
            )

        try:
            system_stats = self._get_json(f"{normalized_url}/system_stats", timeout_seconds)
            object_info = self._get_json(f"{normalized_url}/object_info", timeout_seconds)
        except (requests.RequestException, ValueError, TypeError):
            return RuntimeProbeResult(
                status="unavailable",
                comfyui_version=None,
                required_nodes_present=(),
                required_nodes_missing=tuple(sorted(REQUIRED_CLASS_INPUTS)),
                required_models_present=(),
                required_models_missing=tuple(sorted(REQUIRED_MODELS)),
                workflow_contract_valid=False,
                errors=("Local ComfyUI is unavailable or returned an invalid response.",),
            )

        stats_object = _as_object(system_stats) or {}
        system = _as_object(stats_object.get("system")) or {}
        version = system.get("comfyui_version") if isinstance(system.get("comfyui_version"), str) else None
        object_info_object = _as_object(object_info) or {}

        present_nodes = tuple(sorted(class_type for class_type in REQUIRED_CLASS_INPUTS if class_type in object_info_object))
        missing_nodes = tuple(sorted(set(REQUIRED_CLASS_INPUTS) - set(present_nodes)))
        present_models = tuple(
            sorted(
                filename
                for filename, (class_type, input_name) in REQUIRED_MODELS.items()
                if filename in _combo_options(object_info_object, class_type, input_name)
            )
        )
        missing_models = tuple(sorted(set(REQUIRED_MODELS) - set(present_models)))
        validation = validate_workflow_contract(workflow, object_info_object)

        errors = list(validation.errors)
        if missing_nodes:
            errors.append("Required ComfyUI nodes are missing.")
        if missing_models:
            errors.append("Required MiniMax H3 models are missing.")
        if version is None:
            errors.append("ComfyUI did not report a version.")

        argv = system.get("argv")
        argv_values = cast(Sequence[object], argv) if isinstance(argv, (list, tuple)) else ()
        telemetry_enabled = any(
            isinstance(arg, str) and "enable_telemetry=true" in arg.lower() for arg in argv_values
        )
        if production_runtime and telemetry_enabled:
            errors.append("Production ComfyUI configuration enables telemetry.")

        incompatible = bool(errors)
        return RuntimeProbeResult(
            status="incompatible" if incompatible else "connected",
            comfyui_version=version,
            required_nodes_present=present_nodes,
            required_nodes_missing=missing_nodes,
            required_models_present=present_models,
            required_models_missing=missing_models,
            workflow_contract_valid=validation.valid,
            errors=tuple(dict.fromkeys(errors)),
        )
