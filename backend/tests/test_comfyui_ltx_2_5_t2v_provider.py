import copy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from services.comfyui_ltx_2_5_t2v_provider import (
    ComfyUILtx25T2VProvider,
    LTX_T2V_MAPPING,
    LtxT2VRequest,
    ProviderError,
    _discover_output,
    build_ltx_t2v_prompt_payload,
    validate_ltx_t2v_workflow,
)
from services.comfyui_minimax_h3_provider import VideoProbe


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


def test_output_polling_treats_queued_history_as_incomplete(tmp_path: Path):
    history = {"queued-prompt": {"status": {"completed": False, "status_str": "queued"}, "outputs": {}}}
    assert _discover_output(history, "queued-prompt", tmp_path) is None


def test_output_polling_never_adopts_a_different_prompt_history(tmp_path: Path):
    assert _discover_output({"older-prompt": {"status": {"completed": True}, "outputs": {}}}, "submitted-prompt", tmp_path) is None


def test_adoption_persists_exact_submitted_prompt_and_authoritative_timing(tmp_path: Path):
    source = tmp_path / "source.mp4"; source.write_bytes(b"video")
    provider = ComfyUILtx25T2VProvider(workflow_path=ROOT / "workflows" / "ltx_2_5_text_to_video_api_official.json", output_root=tmp_path, render_root=tmp_path / "renders", ffprobe_path=tmp_path / "ffprobe")
    started, completed = datetime(2026, 8, 13, tzinfo=UTC), datetime(2026, 8, 13, 0, 1, tzinfo=UTC)
    _, _, metadata = provider._adopt(source, "submitted-prompt", request(), VideoProbe("h264", 1280, 704, "24/1", 5.0, 121, True), 60.0, started, completed)
    payload = json.loads(metadata.read_text())
    assert payload["raw_user_prompt"] == request().prompt
    assert payload["final_submitted_prompt"] == request().prompt
    assert payload["native_enhanced_prompt"] is None
    assert payload["render_elapsed_seconds"] == 60.0
    assert payload["render_started_at"] == started.isoformat()
    assert payload["render_completed_at"] == completed.isoformat()


@pytest.mark.parametrize("ratio,width,height", [("9:16 (Portrait Widescreen)", 704, 1280), ("1:1 (Square)", 960, 960)])
def test_supervised_ltx_t2v_geometry_candidate_maps_to_selector(ratio: str, width: int, height: int):
    payload = build_ltx_t2v_prompt_payload(workflow(), LtxT2VRequest("A quiet scene.", True, 42, ratio, 0.9, width, height, 5.0, 24, 121, "scene"), "clientabcd")
    assert payload["prompt"]["409"]["inputs"]["aspect_ratio"] == ratio
