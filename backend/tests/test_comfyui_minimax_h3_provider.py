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
    parse_comfyui_progress_event,
    preprocess_reference_image,
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
        ({"width": 1280}, "incompatible dimensions"),
        ({"height": 720}, "incompatible dimensions"),
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


@pytest.mark.parametrize(
    ("aspect_ratio", "megapixels", "width", "height"),
    [
        ("1:1 (Square)", 0.4, 640, 640), ("1:1 (Square)", 0.6, 800, 800),
        ("1:1 (Square)", 0.8, 928, 928), ("1:1 (Square)", 1.0, 1024, 1024),
        ("16:9 (Widescreen)", 0.4, 864, 480), ("16:9 (Widescreen)", 0.6, 1056, 608),
        ("16:9 (Widescreen)", 0.8, 1216, 672), ("16:9 (Widescreen)", 1.0, 1376, 768),
        ("9:16 (Portrait Widescreen)", 0.4, 480, 864), ("9:16 (Portrait Widescreen)", 0.6, 608, 1056),
        ("9:16 (Portrait Widescreen)", 0.8, 672, 1216), ("9:16 (Portrait Widescreen)", 1.0, 768, 1376),
    ],
)
def test_maps_verified_aspect_ratio_presets_to_resolution_selector(
    tmp_path: Path, aspect_ratio: str, megapixels: float, width: int, height: int,
) -> None:
    payload = build_prompt_payload(
        load_verified_workflow(WORKFLOW_PATH),
        _request(_image(tmp_path / "input.png"), aspect_ratio=aspect_ratio, resolution_megapixels=megapixels, width=width, height=height),
        "input.png",
        "client",
    )
    assert payload["prompt"]["115"]["inputs"]["aspect_ratio"] == aspect_ratio
    assert payload["prompt"]["115"]["inputs"]["megapixels"] == megapixels
    assert payload["prompt"]["105:104"]["inputs"]["width"] == ["115", 0]
    assert payload["prompt"]["105:104"]["inputs"]["height"] == ["115", 1]


@pytest.mark.parametrize("target", [(640, 640), (1056, 608), (1216, 672), (768, 1376)])
def test_reference_fit_stages_exact_dimensions_for_each_verified_preset(tmp_path: Path, target: tuple[int, int]) -> None:
    source = _image(tmp_path / "source.png")
    before = source.read_bytes()
    staged = preprocess_reference_image(source, *target, "fill_crop")
    try:
        with Image.open(staged) as staged_image:
            assert staged_image.size == target
        assert source.read_bytes() == before
    finally:
        staged.unlink(missing_ok=True)


def test_rejects_unverified_resolution_preset(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="resolution preset"):
        build_prompt_payload(
            load_verified_workflow(WORKFLOW_PATH),
            _request(_image(tmp_path / "input.png"), resolution_megapixels=1.2),
            "input.png",
            "client",
        )


def test_maps_duration_to_the_verified_workflow_expression_input(tmp_path: Path) -> None:
    payload = build_prompt_payload(
        load_verified_workflow(WORKFLOW_PATH),
        _request(_image(tmp_path / "input.png"), duration_seconds=10.0),
        "input.png",
        "client",
    )
    assert payload["prompt"]["105:111"]["inputs"]["value"] == 10.0


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
    assert json.loads(first[2].read_text(encoding="utf-8"))["input_image_reference"] == str(image)
    assert list(first[0].glob(".metadata.*.tmp")) == []


def test_project_managed_render_names_and_metadata_keep_original_prompt(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"render")
    image = _image(tmp_path / "input.png")
    request = _request(image, prompt="Original. No music.", original_prompt="Original.", managed_filename_prefix="Scene02", audio_mode="natural_ambience", no_music=True)
    version, output, metadata = create_immutable_render_version(tmp_path / "project" / "scenes" / "scene_002" / "renders", source, "prompt-1", request, VideoProbe("h264", 640, 640, "24/1", 5.167, 124, True))
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert version.name == "v001"
    assert output.name == "Scene02_v001.mp4"
    assert metadata.name == "render-metadata.json"
    assert source.read_bytes() == output.read_bytes()
    assert payload["original_user_prompt"] == "Original."
    assert payload["final_composed_prompt"] == "Original. No music."
    assert payload["audio_guidance"]["no_music"] is True
    assert payload["staged_input_dimensions"] == {"width": 640, "height": 640}


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


def test_maps_only_verified_websocket_progress_events() -> None:
    prompt_id = "prompt-1"
    progress = parse_comfyui_progress_event(json.dumps({
        "type": "progress", "data": {"value": 7, "max": 20, "prompt_id": prompt_id, "node": "105:14"},
    }), prompt_id)
    assert progress is not None
    assert (progress.phase, progress.value, progress.maximum) == ("Sampling", 7, 20)
    assert parse_comfyui_progress_event(json.dumps({
        "type": "progress", "data": {"value": 7, "max": 20, "prompt_id": prompt_id, "node": "unverified"},
    }), prompt_id) is None
    assert parse_comfyui_progress_event(json.dumps({
        "type": "progress", "data": {"value": 7, "max": 20, "prompt_id": "another", "node": "105:14"},
    }), prompt_id) is None


@pytest.mark.parametrize(("node", "phase"), [
    ("105:104", "Preparing generation"), ("105:14", "Sampling"),
    ("105:23", "Decoding"), ("105:91", "Encoding"), ("92", "Encoding"),
])
def test_maps_verified_executing_nodes_to_truthful_phases(node: str, phase: str) -> None:
    update = parse_comfyui_progress_event(json.dumps({
        "type": "executing", "data": {"node": node, "display_node": node, "prompt_id": "prompt-1"},
    }), "prompt-1")
    assert update is not None and update.phase == phase
    assert update.value is None and update.maximum is None


def test_execution_error_diagnostics_are_allowlisted_and_sanitized() -> None:
    update = parse_comfyui_progress_event(json.dumps({
        "type": "execution_error",
        "data": {
            "prompt_id": "prompt-1", "node_type": "LoadImage",
            "exception_type": "PIL.UnidentifiedImageError",
            "exception_message": "C:\\Users\\private\\secret.png token=secret",
            "traceback": ["private traceback"],
        },
    }), "prompt-1")
    assert update is not None
    assert update.terminal == "error"
    assert update.diagnostics == "LoadImage · PIL.UnidentifiedImageError"
    assert "private" not in update.diagnostics
