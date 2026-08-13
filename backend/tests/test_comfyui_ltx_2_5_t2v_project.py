"""Project routing and immutable-version adoption for LTX 2.5 T2V."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_types import H3ProjectRenderRequest, H3SceneUpdateRequest
from handlers.comfyui_minimax_h3_handler import ComfyUIMiniMaxH3Handler, H3RuntimePaths
from services.comfyui_ltx_2_5_t2v_provider import LtxT2VRequest
from services.comfyui_minimax_h3_provider import RenderResult, VideoProbe
from services.h3_project_store import H3ProjectStore


class T2VProvider:
    def __init__(self, result: RenderResult) -> None:
        self.result = result
        self.request: LtxT2VRequest | None = None

    def render(self, *, base_url: str, request: LtxT2VRequest) -> RenderResult:
        assert base_url == "http://127.0.0.1:8190"
        self.request = request
        return self.result


def test_t2v_routes_directly_to_image_free_provider_and_adopts_normal_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project(
        "LTX T2V", workflow_profile_id="ltx_2_5_text_to_video", workflow_mode="text_to_video",
    )
    scene = project.scenes[0]
    project = store.update_scene(project.id, scene.id, H3SceneUpdateRequest(prompt="A quiet rain falls."))
    scene = project.scenes[0]
    render_dir = Path(project.project_root) / "scenes" / scene.storage_name / "renders" / "v001"
    render_dir.mkdir()
    output = render_dir / "SceneLTXT2V_v001.mp4"
    output.write_bytes(b"mp4")
    metadata = render_dir / "render-metadata.json"
    metadata.write_text(json.dumps({
        "created_at": "2026-08-13T00:00:00Z",
        "workflow_sha256": "official-contract",
        "output_sha256": "output",
        "workflow_profile_id": "ltx_2_5_text_to_video",
        "mode": "text_to_video",
        "reference_image_used": False,
    }), encoding="utf-8")
    result = RenderResult(
        "ltx-t2v-prompt", tmp_path / "comfy.mp4", render_dir, output, metadata,
        VideoProbe("h264", 1280, 704, "24/1", 5.0, 121, True),
    )
    provider = T2VProvider(result)
    paths = H3RuntimePaths(tmp_path / "workflow.json", tmp_path / "output", render_dir.parent, tmp_path / "ffprobe.exe", tmp_path / "ffmpeg.exe")
    monkeypatch.setattr("handlers.comfyui_minimax_h3_handler.resolve_ltx_t2v_runtime_paths", lambda _override=None: paths)
    monkeypatch.setattr("handlers.comfyui_minimax_h3_handler.ComfyUILtx25T2VProvider", lambda **_kwargs: provider)
    handler = ComfyUIMiniMaxH3Handler(project_store=store)

    updated = handler.render_project_scene(project.id, scene.id, H3ProjectRenderRequest(base_url="http://127.0.0.1:8190"))

    assert provider.request is not None
    assert not hasattr(provider.request, "input_image")
    assert (provider.request.width, provider.request.height, provider.request.fps, provider.request.frame_count) == (1280, 704, 24, 121)
    adopted = updated.scenes[0].render_versions[0]
    assert adopted.video_file == str(output)
    assert adopted.input_image_reference == "No reference image used"
    assert adopted.input_image_sha256 == "not-applicable"
    assert adopted.prompt_id == "ltx-t2v-prompt"
    assert updated.scenes[0].status == "complete"


def test_t2v_never_requires_the_i2v_reference_image(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project(
        "LTX T2V", workflow_profile_id="ltx_2_5_text_to_video", workflow_mode="text_to_video",
    )
    scene = project.scenes[0]
    assert scene.reference_image is None
    assert (scene.aspect_ratio, scene.resolution_megapixels, scene.width, scene.height, scene.fps, scene.frame_count) == (
        "16:9 (Widescreen)", 0.9, 1280, 704, 24, 121,
    )
