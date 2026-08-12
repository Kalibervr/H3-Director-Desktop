"""Backend-only bridge from the H3 workspace to the verified local provider."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

import imageio_ffmpeg
import requests

from _routes._errors import HTTPError
from api_types import (
    ComfyUIProbeResponse,
    H3Project,
    H3ContinuityPrepareResponse,
    H3ProjectCreateRequest,
    H3ProjectRenderRequest,
    H3ProjectUpdateRequest,
    H3RenderVersion,
    H3UpscaleRequest,
    H3UpscaleVariant,
    H3UpscaleAvailabilityResponse,
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
    RenderCancelled,
    SingleSceneRequest,
    load_verified_workflow,
)
from services.comfyui_runtime_probe import ComfyUIRuntimeProbe
from server_utils.loopback_url import require_loopback_http_url
from services.h3_project_store import H3ProjectStore, ProjectStoreError
from services.h3_continuity import ContinuityError, H3ContinuityExtractor, previous_scene, selected_completed_version
from services.h3_sequence import H3SequenceCoordinator
from services.h3_audio_guidance import H3AudioGuidance, compose_h3_prompt
from services.h3_rtx_vsr_upscale import ComfyUIRtxVsrUpscaler


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
        return self._project_call(lambda: self._project_store.create_project(request.name, request.scene_count, request.sequence_mode))

    def get_project(self, project_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.get_project(project_id))

    def reopen_project(self, project_root: str) -> H3Project:
        return self._project_call(lambda: self._project_store.reopen_project(Path(project_root)))

    def update_project(self, project_id: str, request: H3ProjectUpdateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.update_project(
            project_id, name=request.name, sequence_mode=request.sequence_mode,
        ))

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

    def upscale_project_render(
        self, project_id: str, scene_id: str, source_version_id: str, request: H3UpscaleRequest,
    ) -> H3Project:
        """Create one project-owned immutable 2x RTX VSR derivative."""
        try:
            project = self._project_store.get_project(project_id)
            scene = next((item for item in project.scenes if item.id == scene_id), None)
            if scene is None:
                raise ProjectStoreError("The selected scene could not be found.")
            source = next((item for item in scene.render_versions if item.id == source_version_id), None)
            if source is None:
                raise ProjectStoreError("The selected source render version could not be found.")
            if any(item.backend == "nvidia_rtx_vsr" and item.scale == 2 for item in source.upscale_variants):
                raise ProjectStoreError("An immutable RTX VSR 2× version already exists for this source render.")
            project_root = Path(project.project_root).resolve()
            source_file = Path(source.video_file).resolve()
            source_root = Path(source.root).resolve()
            try:
                source_file.relative_to(project_root)
                source_root.relative_to(project_root)
            except ValueError as exc:
                raise ProjectStoreError("The source render is outside the app-owned project.") from exc
            paths = resolve_h3_runtime_paths()
            result = ComfyUIRtxVsrUpscaler(
                input_root=Path(request.input_directory), output_root=Path(request.output_directory),
                ffprobe_path=paths.ffprobe,
            ).upscale_2x(
                base_url=request.base_url, source_video=source_file,
                destination_root=source_root / "derived" / "nvidia_rtx_vsr",
            )
            metadata = json.loads(result.metadata_file.read_text(encoding="utf-8"))
            variant = H3UpscaleVariant(
                id=result.output_file.parent.name, number=int(result.output_file.parent.name.removeprefix("v")),
                created_at=str(metadata["created_at"]), root=str(result.output_file.parent),
                video_file=str(result.output_file), metadata_file=str(result.metadata_file),
                backend="nvidia_rtx_vsr", source_render_version_id=source.id,
                source_width=source.width, source_height=source.height,
                width=result.video.width, height=result.video.height, scale=2,
                fps=source.fps, duration_seconds=result.video.duration_seconds,
                audio_preserved=result.video.audio_present, prompt_id=result.prompt_id,
                source_video_sha256=result.source_video_sha256, output_sha256=result.output_sha256,
                ffprobe=MiniMaxH3VideoProbeResponse(**result.video.__dict__),
            )
            return self._project_store.add_upscale_variant(project_id, scene_id, source.id, variant)
        except (ProviderError, ProjectStoreError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            message = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError)) else "The RTX VSR result could not be persisted safely."
            raise HTTPError(422, message, code="RTX_VSR_UPSCALE_FAILED") from exc

    def get_upscale_availability(self, base_url: str) -> H3UpscaleAvailabilityResponse:
        """Read-only contract check; runtime execution remains the final authority."""
        try:
            base_url = require_loopback_http_url(base_url)
            response = requests.get(f"{base_url}/object_info", timeout=10, allow_redirects=False)
            payload = response.json()
            resize = payload.get("ImageResizeKJv2") if isinstance(payload, dict) else None
            load = payload.get("VHS_LoadVideo") if isinstance(payload, dict) else None
            combine = payload.get("VHS_VideoCombine") if isinstance(payload, dict) else None
            methods = resize.get("input", {}).get("required", {}).get("upscale_method", [[]])[0] if isinstance(resize, dict) else []
            if not (isinstance(methods, list) and "nvidia_rtx_vsr" in methods and isinstance(load, dict) and isinstance(combine, dict)):
                return H3UpscaleAvailabilityResponse(available=False, reason="Local RTX VSR video nodes are unavailable in the configured ComfyUI runtime.")
            return H3UpscaleAvailabilityResponse(available=True, reason="NVIDIA RTX VSR is ready for verified 2× local video upscaling.")
        except (ValueError, requests.RequestException, json.JSONDecodeError):
            return H3UpscaleAvailabilityResponse(available=False, reason="The configured local ComfyUI runtime could not be checked for RTX VSR.")

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
        result = self._runtime_probe.probe(base_url=base_url, workflow=workflow, production_runtime=True)
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
                    reference_fit=request.reference_fit,
                    aspect_ratio=request.aspect_ratio,
                    resolution_megapixels=request.resolution_megapixels,
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
        sequence_status_callback: Callable[[str, int | None, int | None, str | None], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> H3Project:
        try:
            project = self._project_store.get_project(project_id)
            scene = next((item for item in project.scenes if item.id == scene_id), None)
            if scene is None:
                raise ProjectStoreError("The selected scene could not be found.")
            if not scene.prompt.strip():
                raise ProjectStoreError("The scene requires a prompt before rendering.")
            input_image = self._resolve_render_input(project, scene)
            final_prompt = compose_h3_prompt(scene.prompt, H3AudioGuidance(
                mode=scene.audio_mode,
                no_speech=scene.no_speech,
                no_music=scene.no_music,
                custom_instruction=scene.custom_audio_instruction,
            ))
            scene_root = Path(project.project_root) / "scenes" / scene.storage_name
            paths = resolve_h3_runtime_paths(scene_root / "renders")
            provider = self._provider_factory(paths)
            self._project_store.set_scene_status(project_id, scene_id, "queued", error=None)

            def report(
                phase: str,
                prompt_id: str | None,
                progress_value: int | None,
                progress_max: int | None,
                diagnostics: str | None,
            ) -> None:
                status = {
                    "Preparing": "preparing",
                    "Submitted": "submitted",
                    "Preparing generation": "rendering",
                    "Sampling": "rendering",
                    "Decoding": "rendering",
                    "Encoding": "encoding",
                    "Verifying": "verifying",
                }.get(phase, "rendering")
                self._project_store.set_scene_status(
                    project_id, scene_id, status, prompt_id=prompt_id, error=None,
                    phase=phase, progress_value=progress_value, progress_max=progress_max,
                    diagnostics=diagnostics,
                )
                if sequence_status_callback:
                    sequence_status_callback(phase, progress_value, progress_max, diagnostics)

            result = provider.render(
                base_url=request.base_url,
                request=SingleSceneRequest(
                    prompt=final_prompt,
                    original_prompt=scene.prompt,
                    input_image=input_image,
                    seed=scene.seed,
                    width=scene.width,
                    height=scene.height,
                    duration_seconds=scene.duration_seconds,
                    fps=scene.fps,
                    reference_fit=scene.reference_fit,
                    aspect_ratio=scene.aspect_ratio,
                    resolution_megapixels=scene.resolution_megapixels,
                    output_filename_prefix=f"scene_{scene.order:03d}",
                    managed_filename_prefix=f"Scene{scene.order:02d}",
                    audio_mode=scene.audio_mode,
                    no_speech=scene.no_speech,
                    no_music=scene.no_music,
                    custom_audio_instruction=scene.custom_audio_instruction,
                ),
                status_callback=report,
                cancel_requested=cancel_requested,
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
                final_prompt=final_prompt,
                audio_mode=scene.audio_mode,
                no_speech=scene.no_speech,
                no_music=scene.no_music,
                custom_audio_instruction=scene.custom_audio_instruction,
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
        except RenderCancelled:
            self._project_store.set_scene_status(project_id, scene_id, "cancelled", error=None, phase="Cancelled")
            raise
        except (ProviderError, ProjectStoreError, ContinuityError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            safe_error = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError, ContinuityError)) else "The verified render metadata could not be persisted."
            try:
                self._project_store.set_scene_status(
                    project_id, scene_id, "failed", error=safe_error,
                    phase="Failed",
                    diagnostics=exc.diagnostics if isinstance(exc, ProviderError) else None,
                )
            except ProjectStoreError:
                pass
            raise HTTPError(422, safe_error, code="MINIMAX_H3_RENDER_FAILED") from exc

    def _render_for_sequence(
        self,
        project_id: str,
        scene_id: str,
        request: H3ProjectRenderRequest,
        status_callback: Callable[[str, int | None, int | None, str | None], None],
        cancel_requested: Callable[[], bool],
    ) -> H3Project:
        return self.render_project_scene(project_id, scene_id, request, status_callback, cancel_requested)

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
