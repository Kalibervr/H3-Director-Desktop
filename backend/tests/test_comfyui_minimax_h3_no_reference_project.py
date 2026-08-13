"""Project adoption tests for the verified MiniMax H3 Prompt Only binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_types import H3ProjectRenderRequest, H3SceneUpdateRequest
from handlers.comfyui_minimax_h3_handler import ComfyUIMiniMaxH3Handler, H3RuntimePaths
from services.comfyui_minimax_h3_provider import PromptOnlySceneRequest, RenderResult, VideoProbe
from services.h3_project_store import H3ProjectStore


class PromptOnlyProvider:
    def __init__(self, result: RenderResult) -> None:
        self.result = result
        self.request: PromptOnlySceneRequest | None = None

    def render_prompt_only(self, *, base_url: str, request: PromptOnlySceneRequest) -> RenderResult:
        assert base_url == "http://127.0.0.1:8188"
        self.request = request
        return self.result


def test_project_prompt_only_adopts_a_normal_immutable_h3_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Prompt Only", workflow_profile_id="minimax_h3_no_reference", workflow_mode="text_to_video")
    scene = project.scenes[0]
    project = store.update_scene(project.id, scene.id, H3SceneUpdateRequest(prompt="A local prompt-only test scene.", mode="new_shot"))
    scene = project.scenes[0]
    render_dir = Path(project.project_root) / "scenes" / scene.storage_name / "renders" / "v001"
    render_dir.mkdir()
    output = render_dir / "Scene01_v001.mp4"
    output.write_bytes(b"mp4")
    metadata = render_dir / "render-metadata.json"
    metadata.write_text(json.dumps({"created_at": "2026-08-12T00:00:00Z", "workflow_sha256": "contract", "output_sha256": "output", "reference_image_used": False, "mode": "prompt_only"}), encoding="utf-8")
    result = RenderResult("prompt-only-id", tmp_path / "comfy.mp4", render_dir, output, metadata, VideoProbe("h264", 640, 640, "24/1", 5.167, 124, True))
    provider = PromptOnlyProvider(result)
    paths = H3RuntimePaths(tmp_path / "workflow.json", tmp_path / "output", render_dir.parent, tmp_path / "ffprobe.exe", tmp_path / "ffmpeg.exe")
    monkeypatch.setattr("handlers.comfyui_minimax_h3_handler.resolve_minimax_h3_no_reference_runtime_paths", lambda _override=None: paths)
    handler = ComfyUIMiniMaxH3Handler(provider_factory=lambda _paths: provider, project_store=store)  # type: ignore[arg-type]

    updated = handler.render_project_scene(project.id, scene.id, H3ProjectRenderRequest(base_url="http://127.0.0.1:8188"))
    adopted = updated.scenes[0].render_versions[0]
    assert provider.request is not None
    assert not hasattr(provider.request, "input_image")
    assert provider.request.width == 640 and provider.request.height == 640
    assert provider.request.fps == 24 and provider.request.duration_seconds == 5.0
    assert adopted.video_file == str(output)
    assert adopted.input_image_reference == "No reference image used"
    assert adopted.input_image_sha256 == "not-applicable"
    assert adopted.prompt_id == "prompt-only-id"
    assert updated.scenes[0].status == "complete"


@pytest.mark.parametrize("changes", [{"reference_image": None, "mode": "continue_previous"}, {"width": 864, "height": 480, "aspect_ratio": "16:9 (Widescreen)"}])
def test_prompt_only_project_rejects_unverified_continuity_and_presets(changes: dict[str, object], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Prompt Only", workflow_profile_id="minimax_h3_no_reference", workflow_mode="text_to_video")
    scene = project.scenes[0]
    project = store.update_scene(project.id, scene.id, H3SceneUpdateRequest(prompt="A prompt", **changes))  # type: ignore[arg-type]
    handler = ComfyUIMiniMaxH3Handler(project_store=store)
    with pytest.raises(Exception):
        handler.render_project_scene(project.id, scene.id, H3ProjectRenderRequest(base_url="http://127.0.0.1:8188"))
