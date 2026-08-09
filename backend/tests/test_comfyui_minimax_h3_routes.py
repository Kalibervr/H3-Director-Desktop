"""Focused backend integration tests for the H3 Director workspace boundary."""

from __future__ import annotations

from pathlib import Path

from api_types import (
    ComfyUIProbeResponse,
    MiniMaxH3RenderRequest,
    MiniMaxH3RenderResponse,
    MiniMaxH3VideoProbeResponse,
)
from handlers.comfyui_minimax_h3_handler import ComfyUIMiniMaxH3Handler, H3RuntimePaths
from services.comfyui_minimax_h3_provider import RenderResult, SingleSceneRequest, VideoProbe


class FakeProvider:
    def __init__(self, result: RenderResult) -> None:
        self.result = result
        self.base_url: str | None = None
        self.request: SingleSceneRequest | None = None

    def render(self, *, base_url: str, request: SingleSceneRequest) -> RenderResult:
        self.base_url = base_url
        self.request = request
        return self.result


class FakeWorkspaceHandler:
    def get_status(self, base_url: str) -> ComfyUIProbeResponse:
        assert base_url == "http://127.0.0.1:8188"
        return ComfyUIProbeResponse(
            status="connected",
            comfyui_version="0.30.2",
            required_nodes_present=[],
            required_nodes_missing=[],
            required_models_present=[],
            required_models_missing=[],
            workflow_contract_valid=True,
            errors=[],
        )

    def render_scene(self, request: MiniMaxH3RenderRequest) -> MiniMaxH3RenderResponse:
        assert request.input_image == "C:\\local\\reference.jpg"
        return MiniMaxH3RenderResponse(
            prompt_id="prompt-from-ui",
            output_file="C:\\local\\renders\\v001\\video.mp4",
            metadata_file="C:\\local\\renders\\v001\\metadata.json",
            video=MiniMaxH3VideoProbeResponse(
                codec="h264",
                width=640,
                height=640,
                fps="24/1",
                duration_seconds=5.167,
                frame_count=124,
                audio_present=True,
            ),
        )


def test_handler_maps_verified_ui_fields_to_existing_provider(monkeypatch, tmp_path: Path) -> None:
    input_image = tmp_path / "reference.jpg"
    input_image.write_bytes(b"image")
    source = tmp_path / "source.mp4"
    output = tmp_path / "renders" / "v001" / "video.mp4"
    metadata = output.with_name("metadata.json")
    result = RenderResult(
        prompt_id="real-prompt-id",
        source_output=source,
        render_directory=output.parent,
        output_file=output,
        metadata_file=metadata,
        video=VideoProbe("h264", 640, 640, "24/1", 5.167, 124, True),
    )
    provider = FakeProvider(result)
    paths = H3RuntimePaths(tmp_path / "workflow.json", tmp_path / "comfy-output", tmp_path / "renders", tmp_path / "ffprobe.exe")
    monkeypatch.setattr("handlers.comfyui_minimax_h3_handler.resolve_h3_runtime_paths", lambda: paths)
    handler = ComfyUIMiniMaxH3Handler(provider_factory=lambda received: provider)  # type: ignore[arg-type]

    response = handler.render_scene(MiniMaxH3RenderRequest(
        prompt="A verified local shot",
        input_image=str(input_image),
        seed=42,
        width=640,
        height=640,
        duration_seconds=5.0,
        fps=24,
        output_filename_prefix="MiniMax_H3",
    ))

    assert provider.base_url == "http://127.0.0.1:8188"
    assert provider.request == SingleSceneRequest(
        prompt="A verified local shot",
        input_image=input_image,
        seed=42,
        width=640,
        height=640,
        duration_seconds=5.0,
        fps=24,
        output_filename_prefix="MiniMax_H3",
    )
    assert response.prompt_id == "real-prompt-id"
    assert response.video.frame_count == 124


def test_workspace_status_route_returns_sanitized_status(client, test_state) -> None:
    test_state.comfyui_minimax_h3 = FakeWorkspaceHandler()
    response = client.get("/api/comfyui/minimax-h3/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["comfyui_version"] == "0.30.2"
    assert "workflow" not in payload
    assert "object_info" not in payload


def test_workspace_render_route_returns_only_safe_result(client, test_state) -> None:
    test_state.comfyui_minimax_h3 = FakeWorkspaceHandler()
    response = client.post("/api/comfyui/minimax-h3/render", json={
        "base_url": "http://127.0.0.1:8188",
        "prompt": "A verified local shot",
        "input_image": "C:\\local\\reference.jpg",
        "seed": 42,
        "width": 640,
        "height": 640,
        "duration_seconds": 5.0,
        "fps": 24,
        "output_filename_prefix": "MiniMax_H3",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["prompt_id"] == "prompt-from-ui"
    assert payload["video"]["audio_present"] is True
    assert "workflow" not in payload
    assert "prompt" not in payload
