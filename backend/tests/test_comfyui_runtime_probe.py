"""Focused tests for the read-only ComfyUI runtime probe and workflow validator."""

from __future__ import annotations

import pytest
import requests

from handlers.comfyui_runtime_handler import ComfyUIRuntimeHandler
from services.comfyui_runtime_probe import (
    EXPECTED_WORKFLOW_NODES,
    REQUIRED_CLASS_INPUTS,
    REQUIRED_LINKS,
    REQUIRED_MODELS,
    REQUIRED_OPTIONAL_CLASS_INPUTS,
    ComfyUIRuntimeProbe,
    validate_no_reference_workflow_contract,
    validate_workflow_contract,
)


def _workflow() -> dict[str, object]:
    workflow: dict[str, object] = {}
    for node_id, (class_type, fields) in EXPECTED_WORKFLOW_NODES.items():
        workflow[node_id] = {"class_type": class_type, "inputs": {field: 1 for field in fields}}

    workflow["119"] = {
        "class_type": "ImageScaleToTotalPixels",
        "inputs": {"upscale_method": "nearest-exact", "megapixels": 1, "resolution_steps": 32},
    }
    workflow["120"] = {"class_type": "GetImageSize", "inputs": {"image": ["119", 0]}}

    for node_id, input_name, link in REQUIRED_LINKS:
        node = workflow[node_id]
        assert isinstance(node, dict) and isinstance(node["inputs"], dict)
        node["inputs"][input_name] = link

    selections = {
        "105:6": ("unet_name", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
        "105:13": ("clip_name", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
        "105:11": ("vae_name", "minimax_h3_video_vae_fp16.safetensors"),
        "105:24": ("vae_name", "minimax_h3_audio_vae_fp32.safetensors"),
    }
    for node_id, (input_name, filename) in selections.items():
        node = workflow[node_id]
        assert isinstance(node, dict) and isinstance(node["inputs"], dict)
        node["inputs"][input_name] = filename
    return workflow


def _object_info() -> dict[str, object]:
    info: dict[str, object] = {}
    for class_type, fields in REQUIRED_CLASS_INPUTS.items():
        required: dict[str, object] = {field: ["STRING", {}] for field in fields}
        optional: dict[str, object] = {
            field: ["STRING", {}] for field in REQUIRED_OPTIONAL_CLASS_INPUTS.get(class_type, frozenset())
        }
        info[class_type] = {
            "input": {"required": required, "optional": optional},
            "output_node": class_type == "SaveVideo",
        }

    for filename, (class_type, input_name) in REQUIRED_MODELS.items():
        class_info = info[class_type]
        assert isinstance(class_info, dict)
        input_info = class_info["input"]
        assert isinstance(input_info, dict)
        required = input_info["required"]
        assert isinstance(required, dict)
        existing = required.get(input_name)
        options = existing[0] if isinstance(existing, list) and existing and isinstance(existing[0], list) else []
        options.append(filename)
        required[input_name] = [options, {}]
    return info


def _no_reference_workflow() -> dict[str, object]:
    workflow = _workflow()
    for node_id in ("114", "119", "120"):
        del workflow[node_id]
    minimax = workflow["105:104"]
    assert isinstance(minimax, dict) and isinstance(minimax["inputs"], dict)
    del minimax["inputs"]["first_frame"]
    return workflow


def test_validates_verified_api_contract() -> None:
    result = validate_workflow_contract(_workflow(), _object_info())
    assert result.valid
    assert result.errors == ()


def test_prompt_only_contract_passes_without_i2v_image_requirements() -> None:
    result = validate_no_reference_workflow_contract(_no_reference_workflow(), _object_info())
    assert result.valid
    assert result.errors == ()


def test_prompt_only_contract_rejects_an_image_input_without_weakening_i2v() -> None:
    prompt_only = _no_reference_workflow()
    minimax = prompt_only["105:104"]
    assert isinstance(minimax, dict) and isinstance(minimax["inputs"], dict)
    minimax["inputs"]["first_frame"] = ["114", 0]
    result = validate_no_reference_workflow_contract(prompt_only, _object_info())
    assert not result.valid
    assert result.errors == ("Prompt Only workflow must not include an image input.",)
    assert validate_workflow_contract(_workflow(), _object_info()).valid


@pytest.mark.parametrize("workflow", [[], {}, {"nodes": [], "links": []}, {"1": {"class_type": "LoadImage"}}])
def test_rejects_non_api_workflow_structures(workflow: object) -> None:
    result = validate_workflow_contract(workflow, _object_info())
    assert not result.valid
    assert result.errors == ("Workflow is not a valid ComfyUI API-format node map.",)


def test_rejects_changed_audio_connection_without_echoing_graph() -> None:
    workflow = _workflow()
    create_video = workflow["105:91"]
    assert isinstance(create_video, dict) and isinstance(create_video["inputs"], dict)
    create_video["inputs"]["audio"] = ["unexpected-node", 0]

    result = validate_workflow_contract(workflow, _object_info())
    assert not result.valid
    assert result.errors == ("Workflow contract has a changed required audio/video connection.",)
    assert "unexpected-node" not in " ".join(result.errors)


def test_rejects_missing_required_metadata_field() -> None:
    object_info = _object_info()
    minimax = object_info["MiniMaxH3ImageToVideo"]
    assert isinstance(minimax, dict)
    required = minimax["input"]["required"]  # type: ignore[index]
    del required["prompt"]

    result = validate_workflow_contract(_workflow(), object_info)
    assert not result.valid
    assert "ComfyUI node metadata is missing required input fields." in result.errors


def test_validator_rejects_missing_required_class_type_metadata() -> None:
    object_info = _object_info()
    del object_info["MiniMaxH3ImageToVideo"]

    result = validate_workflow_contract(_workflow(), object_info)
    assert not result.valid
    assert "ComfyUI node metadata is missing required node types." in result.errors


def test_probe_calls_only_two_read_only_endpoints_and_returns_sanitized_status() -> None:
    calls: list[tuple[str, float]] = []

    def get_json(url: str, timeout: float) -> object:
        calls.append((url, timeout))
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.30.2", "argv": []}}
        if url.endswith("/object_info"):
            return _object_info()
        raise AssertionError("Unexpected endpoint")

    result = ComfyUIRuntimeProbe(get_json).probe(
        base_url="http://127.0.0.1:8188/",
        workflow=_workflow(),
    )

    assert result.status == "connected"
    assert result.comfyui_version == "0.30.2"
    assert result.workflow_contract_valid
    assert not result.required_nodes_missing
    assert not result.required_models_missing
    assert calls == [
        ("http://127.0.0.1:8188/system_stats", 5.0),
        ("http://127.0.0.1:8188/object_info", 5.0),
    ]


def test_prompt_only_probe_uses_its_own_node_requirements() -> None:
    def get_json(url: str, _timeout: float) -> object:
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.32.0", "argv": []}}
        object_info = _object_info()
        for i2v_only in ("LoadImage", "GetImageSize", "ImageScaleToTotalPixels"):
            del object_info[i2v_only]
        return object_info

    result = ComfyUIRuntimeProbe(get_json).probe(
        base_url="http://127.0.0.1:8188",
        workflow=_no_reference_workflow(),
        profile_id="minimax_h3_no_reference",
    )
    assert result.status == "connected"
    assert not result.required_nodes_missing
    assert result.workflow_contract_valid


def test_i2v_probe_still_requires_its_image_contract() -> None:
    def get_json(url: str, _timeout: float) -> object:
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.32.0", "argv": []}}
        object_info = _object_info()
        del object_info["LoadImage"]
        return object_info

    result = ComfyUIRuntimeProbe(get_json).probe(
        base_url="http://127.0.0.1:8188",
        workflow=_workflow(),
    )
    assert result.status == "incompatible"
    assert "LoadImage" in result.required_nodes_missing


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8188",
        "http://0.0.0.0:8188",
        "http://192.168.1.2:8188",
        "http://example.com:8188",
        "http://localhost.evil.example:8188",
        "http://user:password@localhost:8188",
    ],
)
def test_probe_rejects_non_loopback_or_non_http_urls_without_network(url: str) -> None:
    def unexpected_get(_url: str, _timeout: float) -> object:
        raise AssertionError("Network must not be called")

    result = ComfyUIRuntimeProbe(unexpected_get).probe(base_url=url, workflow=_workflow())
    assert result.status == "incompatible"
    assert result.errors == ("ComfyUI URL must be a loopback HTTP address.",)


def test_probe_returns_safe_unavailable_error() -> None:
    def fail(_url: str, _timeout: float) -> object:
        raise requests.ConnectionError("secret-host and C:\\private\\workflow.json")

    result = ComfyUIRuntimeProbe(fail).probe(
        base_url="http://localhost:8188",
        workflow={"private_prompt": "do not echo"},
    )
    assert result.status == "unavailable"
    combined = " ".join(result.errors)
    assert combined == "Local ComfyUI is unavailable or returned an invalid response."
    assert "secret-host" not in combined
    assert "private_prompt" not in combined


def test_production_runtime_with_telemetry_is_incompatible() -> None:
    def get_json(url: str, _timeout: float) -> object:
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.30.2", "argv": ["--feature-flag", "enable_telemetry=true"]}}
        return _object_info()

    probe = ComfyUIRuntimeProbe(get_json)
    development = probe.probe(base_url="http://localhost:8188", workflow=_workflow())
    production = probe.probe(
        base_url="http://localhost:8188",
        workflow=_workflow(),
        production_runtime=True,
    )
    assert development.status == "connected"
    assert production.status == "incompatible"
    assert production.errors == ("Production ComfyUI configuration enables telemetry.",)


def test_missing_nodes_and_models_are_reported_by_name() -> None:
    def get_json(url: str, _timeout: float) -> object:
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.30.2", "argv": []}}
        return {}

    result = ComfyUIRuntimeProbe(get_json).probe(base_url="http://[::1]:8188", workflow=_workflow())
    assert result.status == "incompatible"
    assert set(result.required_nodes_missing) == set(REQUIRED_CLASS_INPUTS)
    assert set(result.required_models_missing) == set(REQUIRED_MODELS)


def test_probe_route_returns_only_sanitized_status(client, test_state) -> None:
    calls: list[str] = []

    def get_json(url: str, _timeout: float) -> object:
        calls.append(url)
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.30.2", "argv": []}}
        return _object_info()

    test_state.comfyui_runtime = ComfyUIRuntimeHandler(ComfyUIRuntimeProbe(get_json))
    response = client.post(
        "/api/comfyui/probe",
        json={
            "base_url": "http://127.0.0.1:8188",
            "workflow": _workflow(),
            "production_runtime": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["comfyui_version"] == "0.30.2"
    assert payload["workflow_contract_valid"] is True
    assert "workflow" not in payload
    assert "base_url" not in payload
    assert calls == [
        "http://127.0.0.1:8188/system_stats",
        "http://127.0.0.1:8188/object_info",
    ]
