"""Focused tests for the real, local-only single-scene ComfyUI provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from services.comfyui_minimax_h3_provider import (
    ComfyUIMiniMaxH3Provider,
    ProviderError,
    SingleSceneRequest,
    VideoProbe,
    build_prompt_payload,
    create_immutable_render_version,
    discover_output,
    load_verified_workflow,
    probe_video,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / "workflows" / "minimax_h3_single_scene_api.json"
FFPROBE_PATH = REPO_ROOT / "backend" / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries" / "ffprobe.exe"
EVIDENCE_MP4 = REPO_ROOT / "test-assets" / "minimax-h3" / "single_scene_verified_output.mp4"


def _request(image: Path, **changes: object) -> SingleSceneRequest:
    values: dict[str, object] = {
        "prompt": "A local single-scene test prompt with synchronized audio.",
        "input_image": image,
        "seed": 123456789,
    }
    values.update(changes)
    return SingleSceneRequest(**values)  # type: ignore[arg-type]


def _image(path: Path) -> Path:
    Image.new("RGB", (32, 32), "navy").save(path)
    return path


def test_loads_only_the_hash_verified_immutable_workflow(tmp_path: Path) -> None:
    workflow = load_verified_workflow(WORKFLOW_PATH)
    assert workflow["105:104"]["class_type"] == "MiniMaxH3ImageToVideo"
    changed = tmp_path / "workflow.json"
    changed.write_text(WORKFLOW_PATH.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ProviderError, match="workflow has changed"):
        load_verified_workflow(changed)


def test_maps_only_verified_fields_without_mutating_template(tmp_path: Path) -> None:
    template = load_verified_workflow(WORKFLOW_PATH)
    original = json.dumps(template, sort_keys=True)
    request = _request(_image(tmp_path / "input.png"), output_filename_prefix="scene_001")
    payload = build_prompt_payload(template, request, "staged/input.png", "abcdef0123456789")
    graph = payload["prompt"]
    assert graph["105:104"]["inputs"]["prompt"] == request.prompt
    assert graph["114"]["inputs"]["image"] == "staged/input.png"
    assert graph["105:15"]["inputs"]["noise_seed"] == request.seed
    assert graph["105:104"]["inputs"]["width"] == ["115", 0]
    assert graph["105:104"]["inputs"]["height"] == ["115", 1]
    assert graph["115"]["inputs"] == {
        "aspect_ratio": "1:1 (Square)",
        "megapixels": 0.4,
        "multiple": 32,
    }
    assert graph["105:111"]["inputs"]["value"] == 5.0
    assert graph["105:91"]["inputs"]["fps"] == 24
    assert graph["92"]["inputs"]["filename_prefix"] == "h3-director/scene_001_abcdef01"
    assert payload["client_id"] == "abcdef0123456789"
    assert json.dumps(template, sort_keys=True) == original


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"width": 1280}, "640x640"),
        ({"height": 720}, "640x640"),
        ({"duration_seconds": 6.0}, "5 second"),
        ({"fps": 30}, "24 FPS"),
    ],
)
def test_rejects_unverified_controls(tmp_path: Path, changes: dict[str, object], message: str) -> None:
    with pytest.raises(ProviderError, match=message):
        build_prompt_payload(
            load_verified_workflow(WORKFLOW_PATH),
            _request(_image(tmp_path / "input.png"), **changes),
            "input.png",
            "client",
        )


def test_prompt_submission_payload_contains_no_wrapper_graph_metadata(tmp_path: Path) -> None:
    payload = build_prompt_payload(
        load_verified_workflow(WORKFLOW_PATH),
        _request(_image(tmp_path / "input.png")),
        "input.png",
        "client",
    )
    assert set(payload) == {"prompt", "client_id"}
    assert "nodes" not in payload
    assert "links" not in payload


def test_discovers_safe_actual_output_from_documented_node(tmp_path: Path) -> None:
    output = tmp_path / "video" / "result.mp4"
    output.parent.mkdir()
    output.write_bytes(b"mp4")
    history = {
        "prompt-1": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {"92": {"images": [{"filename": "result.mp4", "subfolder": "video", "type": "output"}], "animated": [True]}},
        }
    }
    assert discover_output(history, "prompt-1", tmp_path) == output.resolve()
    assert discover_output({}, "prompt-1", tmp_path) is None


def test_output_discovery_rejects_traversal_and_sanitizes_failure(tmp_path: Path) -> None:
    history = {
        "prompt-1": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {"92": {"images": [{"filename": "secret.mp4", "subfolder": "..", "type": "output"}], "animated": [True]}},
        }
    }
    with pytest.raises(ProviderError) as caught:
        discover_output(history, "prompt-1", tmp_path)
    assert "secret.mp4" not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_creates_collision_safe_immutable_versions(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"render")
    image = _image(tmp_path / "input.png")
    probe = VideoProbe("h264", 640, 640, "24/1", 5.167, 124, True)
    first = create_immutable_render_version(tmp_path / "renders", source, "prompt-1", _request(image), probe)
    second = create_immutable_render_version(tmp_path / "renders", source, "prompt-2", _request(image), probe)
    assert first[0].name == "v001"
    assert second[0].name == "v002"
    assert first[1].read_bytes() == b"render"
    assert json.loads(first[2].read_text(encoding="utf-8"))["prompt_id"] == "prompt-1"


@pytest.mark.skipif(not FFPROBE_PATH.is_file(), reason="verified bundled ffprobe is unavailable")
def test_bundled_ffprobe_verifies_evidence_mp4() -> None:
    result = probe_video(FFPROBE_PATH, EVIDENCE_MP4)
    assert result.codec == "h264"
    assert (result.width, result.height) == (640, 640)
    assert result.fps == "24/1"
    assert result.frame_count == 124
    assert result.audio_present is True


def test_provider_rejects_non_loopback_before_any_io(tmp_path: Path) -> None:
    provider = ComfyUIMiniMaxH3Provider(
        workflow_path=WORKFLOW_PATH,
        output_root=tmp_path,
        render_root=tmp_path / "renders",
        ffprobe_path=FFPROBE_PATH,
    )
    with pytest.raises(ProviderError, match="loopback"):
        provider.render(
            base_url="http://example.com:8188",
            request=_request(tmp_path / "private-input.png"),
        )


def test_ffprobe_errors_do_not_expose_private_paths(tmp_path: Path) -> None:
    private = tmp_path / "private" / "secret.mp4"
    with pytest.raises(ProviderError) as caught:
        probe_video(tmp_path / "missing-ffprobe.exe", private)
    assert "secret.mp4" not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)
