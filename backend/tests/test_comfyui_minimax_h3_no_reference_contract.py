"""Focused contract tests for the disabled MiniMax H3 no-reference seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.comfyui_minimax_h3_provider import (
    PromptOnlySceneRequest,
    ProviderError,
    build_no_reference_prompt_payload,
    load_verified_no_reference_workflow,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / "workflows" / "minimax_h3_no_reference_api.json"


def test_prompt_only_contract_is_hash_verified_and_has_no_image_node(tmp_path: Path) -> None:
    workflow = load_verified_no_reference_workflow(WORKFLOW_PATH)
    assert "114" not in workflow
    assert "first_frame" not in workflow["105:104"]["inputs"]
    assert "last_frame" not in workflow["105:104"]["inputs"]
    changed = tmp_path / "changed.json"
    changed.write_text(WORKFLOW_PATH.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ProviderError, match="has changed"):
        load_verified_no_reference_workflow(changed)


def test_prompt_only_payload_maps_only_contract_fields_and_never_uploads_an_image() -> None:
    template = load_verified_no_reference_workflow(WORKFLOW_PATH)
    original = json.dumps(template, sort_keys=True)
    request = PromptOnlySceneRequest(
        prompt="A quiet local prompt-only H3 scene.",
        seed=420024,
        output_filename_prefix="scene_001",
    )
    payload = build_no_reference_prompt_payload(template, request, "abcdef0123456789")
    graph = payload["prompt"]
    assert graph["105:104"]["inputs"]["prompt"] == request.prompt
    assert "first_frame" not in graph["105:104"]["inputs"]
    assert "last_frame" not in graph["105:104"]["inputs"]
    assert "114" not in graph
    assert graph["105:15"]["inputs"]["noise_seed"] == request.seed
    assert graph["115"]["inputs"] == {"aspect_ratio": "1:1 (Square)", "megapixels": 0.4, "multiple": 32}
    assert graph["105:111"]["inputs"]["value"] == 5.0
    assert graph["105:91"]["inputs"]["fps"] == 24
    assert graph["92"]["inputs"]["filename_prefix"] == "h3-director/scene_001_abcdef01"
    assert payload["client_id"] == "abcdef0123456789"
    assert json.dumps(template, sort_keys=True) == original


def test_prompt_only_payload_rejects_an_image_qualified_contract() -> None:
    workflow = load_verified_no_reference_workflow(WORKFLOW_PATH)
    workflow["105:104"]["inputs"]["first_frame"] = ["114", 0]
    with pytest.raises(ProviderError, match="must not include an image input"):
        build_no_reference_prompt_payload(workflow, PromptOnlySceneRequest(prompt="x", seed=1), "client")
