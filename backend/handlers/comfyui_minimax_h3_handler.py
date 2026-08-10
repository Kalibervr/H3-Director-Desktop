"""Backend-only bridge from the H3 workspace to the verified local provider."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

import imageio_ffmpeg

from _routes._errors import HTTPError
from api_types import (
    ComfyUIProbeResponse,
    H3Project,
    H3ContinuityPrepareResponse,
    H3ProjectCreateRequest,
    H3ProjectRenderRequest,
    H3ProjectUpdateRequest,
    H3RenderVersion,
    H3Scene,
    H3SceneReorderRequest,
    H3SceneUpdateRequest,
    H3RenderRun,
    H3SequenceStartRequest,
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
from services.h3_project_store import H3ProjectStore, ProjectStoreError
from services.h3_continuity import ContinuityError, H3ContinuityExtractor, previous_scene, selected_completed_version
from services.h3_sequence import H3SequenceCoordinator


@dataclass(frozen=True)
class H3RuntimePaths:
    workflow: Path
    comfyui_output: Path
    render_root: Path
    ffprobe: Path
    ffmpeg: Path


def _environment_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def resolve_h3_runtime_paths(render_root_override: Path | None = None) -> H3RuntimePaths:
    repository_or_resources_root = Path(__file__).resolve().parents[2]
    workflow = _environment_path("H3_MINIMAX_WORKFLOW_PATH") or (
        repository_or_resources_root / "workflows" / "minimax_h3_single_scene_api.json"
    )

    app_data = os.environ.get("APPDATA", "").strip()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not app_data or not local_app_data:
        raise HTTPError(503, "Required local Windows application-data paths are unavailable.")

    comfyui_output = _environment_path("H3_COMFYUI_OUTPUT_DIR") or Path(app_data) / "ComfyUI" / "output"
    render_root = render_root_override or _environment_path("H3_RENDER_ROOT") or (
        Path(local_app_data) / "H3 Director Desktop" / "renders" / "single-scene"
    )
    imageio_dir = Path(imageio_ffmpeg.__file__).resolve().parent
    ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ffprobe = _environment_path("H3_FFPROBE_PATH") or imageio_dir / "binaries" / ffprobe_name
    ffmpeg = _environment_path("H3_FFMPEG_PATH") or imageio_dir / "binaries" / ffmpeg_name
    return H3RuntimePaths(workflow, comfyui_output, render_root, ffprobe, ffmpeg)


ProviderFactory = Callable[[H3RuntimePaths], ComfyUIMiniMaxH3Provider]
T = TypeVar("T")


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
        project_store: H3ProjectStore | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._runtime_probe = runtime_probe or ComfyUIRuntimeProbe()
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if project_store is None and not local_app_data:
            raise RuntimeError("Required local Windows application-data path is unavailable.")
        self._project_store = project_store or H3ProjectStore(
            Path(local_app_data) / "H3 Director Desktop" / "Projects"
        )
        self._sequence = H3SequenceCoordinator(self._project_store, self._render_for_sequence)

    def list_projects(self) -> list[H3Project]:
        return self._project_call(self._project_store.list_projects)

    def create_project(self, request: H3ProjectCreateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.create_project(request.name, request.scene_count))

    def get_project(self, project_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.get_project(project_id))

    def reopen_project(self, project_root: str) -> H3Project:
        return self._project_call(lambda: self._project_store.reopen_project(Path(project_root)))

    def update_project(self, project_id: str, request: H3ProjectUpdateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.rename_project(project_id, request.name))

    def update_scene(self, project_id: str, scene_id: str, request: H3SceneUpdateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.update_scene(project_id, scene_id, request))

    def select_scene(self, project_id: str, scene_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.select_scene(project_id, scene_id))

    def add_scene(self, project_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.add_scene(project_id))

    def duplicate_scene(self, project_id: str, scene_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.duplicate_scene(project_id, scene_id))

    def delete_scene(self, project_id: str, scene_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.delete_scene(project_id, scene_id))

    def reorder_scenes(self, project_id: str, request: H3SceneReorderRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.reorder_scenes(project_id, request.scene_ids))

    def prepare_continuity(self, project_id: str, scene_id: str) -> H3ContinuityPrepareResponse:
        try:
            project = self._project_store.get_project(project_id)
            scene = next((item for item in project.scenes if item.id == scene_id), None)
            if scene is None:
                raise ProjectStoreError("The selected scene could not be found.")
            paths = resolve_h3_runtime_paths()
            artifact = H3ContinuityExtractor(paths.ffmpeg, paths.ffprobe).extract(project, scene)
            project = self._project_store.add_continuity_artifact(project_id, scene_id, artifact)
            return H3ContinuityPrepareResponse(project=project, artifact=artifact)
        except (ProjectStoreError, ContinuityError) as exc:
            raise HTTPError(422, str(exc), code="H3_CONTINUITY_ERROR") from exc

    def start_sequence(self, project_id: str, request: H3SequenceStartRequest) -> H3RenderRun:
        status = self.get_status(request.base_url)
        if status.status != "connected" or not status.workflow_contract_valid:
            message = status.errors[0] if status.errors else "The local ComfyUI runtime is unavailable or incompatible."
            raise HTTPError(422, message, code="H3_SEQUENCE_RUNTIME_ERROR")
        try:
            return self._sequence.start(
                project_id,
                H3ProjectRenderRequest(base_url=request.base_url),
                kind=request.kind,
                start_scene_id=request.start_scene_id,
            )
        except ProjectStoreError as exc:
            raise HTTPError(422, str(exc), code="H3_SEQUENCE_ERROR") from exc

    def stop_sequence(self, project_id: str, run_id: str) -> H3RenderRun:
        try:
            return self._sequence.request_stop(project_id, run_id)
        except ProjectStoreError as exc:
            raise HTTPError(422, str(exc), code="H3_SEQUENCE_ERROR") from exc

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

    def render_project_scene(
        self,
        project_id: str,
        scene_id: str,
        request: H3ProjectRenderRequest,
        sequence_status_callback: Callable[[str], None] | None = None,
    ) -> H3Project:
        try:
            project = self._project_store.get_project(project_id)
            scene = next((item for item in project.scenes if item.id == scene_id), None)
            if scene is None:
                raise ProjectStoreError("The selected scene could not be found.")
            if not scene.prompt.strip():
                raise ProjectStoreError("The scene requires a prompt before rendering.")
            input_image = self._resolve_render_input(project, scene)
            scene_root = Path(project.project_root) / "scenes" / scene.storage_name
            paths = resolve_h3_runtime_paths(scene_root / "renders")
            provider = self._provider_factory(paths)
            self._project_store.set_scene_status(project_id, scene_id, "queued", error=None)

            def report(status: str, prompt_id: str | None) -> None:
                self._project_store.set_scene_status(
                    project_id, scene_id, status, prompt_id=prompt_id, error=None
                )
                if sequence_status_callback:
                    sequence_status_callback(status)

            result = provider.render(
                base_url=request.base_url,
                request=SingleSceneRequest(
                    prompt=scene.prompt,
                    input_image=input_image,
                    seed=scene.seed,
                    width=scene.width,
                    height=scene.height,
                    duration_seconds=scene.duration_seconds,
                    fps=scene.fps,
                    output_filename_prefix=f"scene_{scene.order:03d}",
                ),
                status_callback=report,
            )
            metadata_payload = json.loads(result.metadata_file.read_text(encoding="utf-8"))
            version_number = int(result.render_directory.name.removeprefix("v"))
            version = H3RenderVersion(
                id=result.render_directory.name,
                number=version_number,
                created_at=str(metadata_payload["created_at"]),
                root=str(result.render_directory),
                video_file=str(result.output_file),
                metadata_file=str(result.metadata_file),
                prompt=scene.prompt,
                input_image_reference=str(input_image),
                seed=scene.seed,
                width=scene.width,
                height=scene.height,
                fps=scene.fps,
                duration_seconds=scene.duration_seconds,
                frame_count=result.video.frame_count,
                prompt_id=result.prompt_id,
                input_image_sha256=str(metadata_payload["input_image_sha256"]),
                workflow_sha256=str(metadata_payload["workflow_sha256"]),
                output_sha256=str(metadata_payload["output_sha256"]),
                ffprobe=MiniMaxH3VideoProbeResponse(**result.video.__dict__),
            )
            return self._project_store.add_render_version(project_id, scene_id, version)
        except (ProviderError, ProjectStoreError, ContinuityError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            safe_error = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError, ContinuityError)) else "The verified render metadata could not be persisted."
            try:
                self._project_store.set_scene_status(
                    project_id, scene_id, "failed", error=safe_error
                )
            except ProjectStoreError:
                pass
            raise HTTPError(422, safe_error, code="MINIMAX_H3_RENDER_FAILED") from exc

    def _render_for_sequence(
        self,
        project_id: str,
        scene_id: str,
        request: H3ProjectRenderRequest,
        status_callback: Callable[[str], None],
    ) -> H3Project:
        return self.render_project_scene(project_id, scene_id, request, status_callback)

    def _resolve_render_input(self, project: H3Project, scene: H3Scene) -> Path:
        if scene.mode == "same_character_new_shot":
            raise ProjectStoreError(
                "Same Character, New Shot is unavailable because the verified workflow has no separate character input."
            )
        if scene.mode == "new_shot":
            if not scene.reference_image:
                raise ProjectStoreError("New Shot requires a selected reference image.")
            return Path(scene.reference_image)

        source_scene = previous_scene(project, scene.id)
        source_version = selected_completed_version(source_scene)
        matching = next((artifact for artifact in reversed(scene.continuity_artifacts) if (
            artifact.source_scene_id == source_scene.id
            and artifact.source_render_version_id == source_version.id
            and artifact.strategy == scene.continuity_strategy
            and artifact.offset_from_end_frames == (
                scene.continuity_offset_frames if scene.continuity_strategy == "offset_from_end" else 0
            )
            and Path(artifact.image_file).is_file()
        )), None)
        if matching is None:
            paths = resolve_h3_runtime_paths()
            matching = H3ContinuityExtractor(paths.ffmpeg, paths.ffprobe).extract(project, scene)
            project = self._project_store.add_continuity_artifact(project.id, scene.id, matching)
        return Path(matching.image_file)

    @staticmethod
    def _project_call(operation: Callable[[], T]) -> T:
        try:
            return operation()
        except ProjectStoreError as exc:
            raise HTTPError(422, str(exc), code="H3_PROJECT_ERROR") from exc
