"""Backend-only bridge from the H3 workspace to the verified local provider."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio_ffmpeg

from _routes._errors import HTTPError
from api_types import (
    ComfyUIProbeResponse,
    MiniMaxH3RenderRequest,
    MiniMaxH3RenderResponse,
    MiniMaxH3VideoProbeResponse,
)
from services.comfyui_minimax_h3_provider import (
    ComfyUIMiniMaxH3Provider,
    ProviderError,
    SingleSceneRequest,
    load_verified_workflow,
)
from services.comfyui_runtime_probe import ComfyUIRuntimeProbe


@dataclass(frozen=True)
class H3RuntimePaths:
    workflow: Path
    comfyui_output: Path
    render_root: Path
    ffprobe: Path


def _environment_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def resolve_h3_runtime_paths() -> H3RuntimePaths:
    repository_or_resources_root = Path(__file__).resolve().parents[2]
    workflow = _environment_path("H3_MINIMAX_WORKFLOW_PATH") or (
        repository_or_resources_root / "workflows" / "minimax_h3_single_scene_api.json"
    )

    app_data = os.environ.get("APPDATA", "").strip()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not app_data or not local_app_data:
        raise HTTPError(503, "Required local Windows application-data paths are unavailable.")

    comfyui_output = _environment_path("H3_COMFYUI_OUTPUT_DIR") or Path(app_data) / "ComfyUI" / "output"
    render_root = _environment_path("H3_RENDER_ROOT") or (
        Path(local_app_data) / "H3 Director Desktop" / "renders" / "single-scene"
    )
    imageio_dir = Path(imageio_ffmpeg.__file__).resolve().parent
    ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    ffprobe = _environment_path("H3_FFPROBE_PATH") or imageio_dir / "binaries" / ffprobe_name
    return H3RuntimePaths(workflow, comfyui_output, render_root, ffprobe)


ProviderFactory = Callable[[H3RuntimePaths], ComfyUIMiniMaxH3Provider]


def _default_provider_factory(paths: H3RuntimePaths) -> ComfyUIMiniMaxH3Provider:
    return ComfyUIMiniMaxH3Provider(
        workflow_path=paths.workflow,
        output_root=paths.comfyui_output,
        render_root=paths.render_root,
        ffprobe_path=paths.ffprobe,
    )


class ComfyUIMiniMaxH3Handler:
    def __init__(
        self,
        provider_factory: ProviderFactory = _default_provider_factory,
        runtime_probe: ComfyUIRuntimeProbe | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._runtime_probe = runtime_probe or ComfyUIRuntimeProbe()

    def get_status(self, base_url: str) -> ComfyUIProbeResponse:
        try:
            workflow = load_verified_workflow(resolve_h3_runtime_paths().workflow)
        except ProviderError as exc:
            return ComfyUIProbeResponse(
                status="incompatible",
                comfyui_version=None,
                required_nodes_present=[],
                required_nodes_missing=[],
                required_models_present=[],
                required_models_missing=[],
                workflow_contract_valid=False,
                errors=[str(exc)],
            )
        result = self._runtime_probe.probe(base_url=base_url, workflow=workflow)
        return ComfyUIProbeResponse(
            status=result.status,
            comfyui_version=result.comfyui_version,
            required_nodes_present=list(result.required_nodes_present),
            required_nodes_missing=list(result.required_nodes_missing),
            required_models_present=list(result.required_models_present),
            required_models_missing=list(result.required_models_missing),
            workflow_contract_valid=result.workflow_contract_valid,
            errors=list(result.errors),
        )

    def render_scene(self, request: MiniMaxH3RenderRequest) -> MiniMaxH3RenderResponse:
        paths = resolve_h3_runtime_paths()
        provider = self._provider_factory(paths)
        try:
            result = provider.render(
                base_url=request.base_url,
                request=SingleSceneRequest(
                    prompt=request.prompt,
                    input_image=Path(request.input_image),
                    seed=request.seed,
                    width=request.width,
                    height=request.height,
                    duration_seconds=request.duration_seconds,
                    fps=request.fps,
                    output_filename_prefix=request.output_filename_prefix,
                ),
            )
        except ProviderError as exc:
            raise HTTPError(422, str(exc), code="MINIMAX_H3_RENDER_FAILED") from exc
        return MiniMaxH3RenderResponse(
            prompt_id=result.prompt_id,
            output_file=str(result.output_file),
            metadata_file=str(result.metadata_file),
            video=MiniMaxH3VideoProbeResponse(**result.video.__dict__),
        )
