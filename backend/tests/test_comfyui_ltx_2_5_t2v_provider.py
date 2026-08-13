import copy
import json
from pathlib import Path

import pytest

from services.comfyui_ltx_2_5_t2v_provider import (
    LTX_T2V_MAPPING,
    LtxT2VRequest,
    ProviderError,
    _discover_output,
    build_ltx_t2v_prompt_payload,
    validate_ltx_t2v_workflow,
)


ROOT = Path(__file__).resolve().parents[2]


def workflow() -> dict:
    return json.loads((ROOT / "workflows" / "ltx_2_5_text_to_video_api_official.json").read_text())


def request() -> LtxT2VRequest:
    return LtxT2VRequest("A quiet rain falls on an empty street.", True, 42, "16:9 (Widescreen)", 0.9, 1280, 704, 5.0, 24, 121, "scene")


def test_payload_maps_only_verified_t2v_nodes_without_image_fields():
    payload = build_ltx_t2v_prompt_payload(workflow(), request(), "clientabcd")
    prompt = payload["prompt"]
    assert prompt[LTX_T2V_MAPPING["prompt"]]["inputs"]["value"] == request().prompt
    assert prompt[LTX_T2V_MAPPING["prompt_enhance"]]["inputs"]["value"] is True
    assert prompt["405:362"]["inputs"]["value"] == 5.0
    assert prompt["405:361"]["inputs"]["value"] == 24
    assert prompt["405:339"]["inputs"]["noise_seed"] == 42
    assert prompt["409"]["inputs"] == {"aspect_ratio": "16:9 (Widescreen)", "megapixels": 0.9, "multiple": 32}
    assert all(
        not {"image", "first_frame", "last_frame"}.intersection(node["inputs"])
        for node in prompt.values()
    )
    assert prompt["405:370"]["inputs"]["audio"] == ["405:358", 0]
    assert prompt["75"]["inputs"]["video"] == ["405:370", 0]


def test_preflight_rejects_image_mutation():
    base = workflow(); info = {node["class_type"]: {} for node in base.values()}
    validate_ltx_t2v_workflow(base, info)
    mutated = copy.deepcopy(base); mutated["new"] = {"class_type": "LoadImage", "inputs": {"image": "bad.png"}}
    with pytest.raises(ProviderError, match="image dependency"):
        validate_ltx_t2v_workflow(mutated, info)


def test_output_polling_treats_absent_history_as_incomplete(tmp_path: Path):
    assert _discover_output({}, "pending-prompt", tmp_path) is None


@pytest.mark.parametrize("ratio,width,height", [("9:16 (Portrait Widescreen)", 704, 1280), ("1:1 (Square)", 960, 960)])
def test_supervised_ltx_t2v_geometry_candidate_maps_to_selector(ratio: str, width: int, height: int):
    payload = build_ltx_t2v_prompt_payload(workflow(), LtxT2VRequest("A quiet scene.", True, 42, ratio, 0.9, width, height, 5.0, 24, 121, "scene"), "clientabcd")
    assert payload["prompt"]["409"]["inputs"]["aspect_ratio"] == ratio
