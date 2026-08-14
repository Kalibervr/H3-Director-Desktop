"""Backend-only bridge from the H3 workspace to the verified local provider."""

from __future__ import annotations

import os
import json
import re
from collections import deque
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
    H3PromptAssistantRequest,
    H3PromptAssistantResponse,
    H3PromptAssistantStatusResponse,
    H3NextScenePromptRequest,
    H3NextScenePromptResponse,
    H3NextSceneSuggestionsResponse,
    H3WorkflowProfileInstallRequest,
    H3WorkflowProfileInstallResponse,
    H3Ltx25ModelImportRequest,
    H3Ltx25ModelImportResponse,
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
    PromptOnlySceneRequest,
    load_verified_no_reference_workflow,
    load_verified_workflow,
)
from services.comfyui_ltx_2_5_provider import ComfyUILtx25I2VProvider, LtxI2VRequest
from services.comfyui_ltx_2_5_t2v_provider import ComfyUILtx25T2VProvider, LtxT2VRequest
from services.ltx_2_5_geometry import is_ltx_product_validation_preset
from services.comfyui_runtime_probe import ComfyUIRuntimeProbe
from server_utils.loopback_url import require_loopback_http_url
from services.h3_project_store import H3ProjectStore, ProjectStoreError
from services.h3_continuity import ContinuityError, H3ContinuityExtractor, previous_scene, selected_completed_version
from services.h3_sequence import H3SequenceCoordinator, resolve_sequence_scenes
from services.h3_audio_guidance import H3AudioGuidance, compose_h3_prompt
from services.h3_rtx_vsr_upscale import ComfyUIRtxVsrUpscaler
from services.h3_ollama_prompt_assistant import OllamaPromptAssistant, OllamaPromptAssistantError
from services.h3_workflow_profiles import WorkflowProfileError, WorkflowProfileRegistry, validate_profile_package
from services.h3_ltx_2_5_model_import import Ltx25ModelImportError, import_ltx25_assets, inspect_ltx25_assets, resolve_shared_model_root
from services.h3_workflow_center import WorkflowCenter, WorkflowCenterError


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


def resolve_ltx_i2v_runtime_paths(render_root_override: Path | None = None) -> H3RuntimePaths:
    paths = resolve_h3_runtime_paths(render_root_override)
    repository_or_resources_root = Path(__file__).resolve().parents[2]
    workflow = _environment_path("H3_LTX_2_5_I2V_WORKFLOW_PATH") or (
        repository_or_resources_root / "workflows" / "ltx_2_5_image_to_video_api.json"
    )
    return H3RuntimePaths(workflow, paths.comfyui_output, paths.render_root, paths.ffprobe, paths.ffmpeg)


def resolve_ltx_t2v_runtime_paths(render_root_override: Path | None = None) -> H3RuntimePaths:
    paths = resolve_h3_runtime_paths(render_root_override)
    repository_or_resources_root = Path(__file__).resolve().parents[2]
    workflow = _environment_path("H3_LTX_2_5_T2V_WORKFLOW_PATH") or (
        repository_or_resources_root / "workflows" / "ltx_2_5_text_to_video_api_official.json"
    )
    return H3RuntimePaths(workflow, paths.comfyui_output, paths.render_root, paths.ffprobe, paths.ffmpeg)


def resolve_minimax_h3_no_reference_runtime_paths(render_root_override: Path | None = None) -> H3RuntimePaths:
    paths = resolve_h3_runtime_paths(render_root_override)
    repository_or_resources_root = Path(__file__).resolve().parents[2]
    workflow = _environment_path("H3_MINIMAX_NO_REFERENCE_WORKFLOW_PATH") or (
        repository_or_resources_root / "workflows" / "minimax_h3_no_reference_api.json"
    )
    return H3RuntimePaths(workflow, paths.comfyui_output, paths.render_root, paths.ffprobe, paths.ffmpeg)


ProviderFactory = Callable[[H3RuntimePaths], ComfyUIMiniMaxH3Provider]
T = TypeVar("T")


def _default_provider_factory(paths: H3RuntimePaths) -> ComfyUIMiniMaxH3Provider:
    return ComfyUIMiniMaxH3Provider(
        workflow_path=paths.workflow,
        output_root=paths.comfyui_output,
        render_root=paths.render_root,
        ffprobe_path=paths.ffprobe,
    )


class SuggestionQualityError(ValueError):
    """A rejected local suggestion set, retained only for bounded diagnostics."""

    def __init__(self, reasons: list[str], options: list[str]) -> None:
        self.reasons = reasons
        self.options = options
        super().__init__("; ".join(reasons))


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
        # Request-local diagnostics are intentionally bounded and never affect
        # project continuity state or leave the local process.
        self._suggestion_diagnostics: deque[dict[str, object]] = deque(maxlen=20)
        self._sequence = H3SequenceCoordinator(self._project_store, self._render_for_sequence)

    def list_projects(self) -> list[H3Project]:
        return self._project_call(self._project_store.list_projects)

    def create_project(self, request: H3ProjectCreateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.create_project(request.name, request.scene_count, request.sequence_mode, request.workflow_profile_id, request.workflow_mode))

    def get_project(self, project_id: str) -> H3Project:
        return self._project_call(lambda: self._project_store.get_project(project_id))

    def reopen_project(self, project_root: str) -> H3Project:
        return self._project_call(lambda: self._project_store.reopen_project(Path(project_root)))

    def update_project(self, project_id: str, request: H3ProjectUpdateRequest) -> H3Project:
        return self._project_call(lambda: self._project_store.update_project(
            project_id, name=request.name, sequence_mode=request.sequence_mode, workflow_profile_id=request.workflow_profile_id, workflow_mode=request.workflow_mode,
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

    def delete_project(self, project_id: str) -> None:
        self._project_call(lambda: self._project_store.delete_project(project_id))

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
                processing_elapsed_seconds=(float(metadata["processing_elapsed_seconds"]) if isinstance(metadata.get("processing_elapsed_seconds"), (int, float)) else None),
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

    def get_prompt_assistant_status(self, endpoint: str, selected_model: str | None) -> H3PromptAssistantStatusResponse:
        return OllamaPromptAssistant().status(endpoint, selected_model)

    def improve_prompt(self, request: H3PromptAssistantRequest) -> H3PromptAssistantResponse:
        try:
            result = OllamaPromptAssistant().improve(request)
            return H3PromptAssistantResponse(
                suggestion=result.suggestion, model=request.model, vision_context=result.vision_context,
                message="AI-enhanced local suggestion from Local Ollama.", request_id=request.request_id, elapsed_seconds=result.elapsed_seconds,
            )
        except (OllamaPromptAssistantError, ValueError) as exc:
            raise HTTPError(422, str(exc), code="H3_OLLAMA_PROMPT_ERROR") from exc

    def _next_scene_source(self, project: H3Project, scene_id: str) -> tuple[H3Scene, H3Scene, H3RenderVersion]:
        target = next((item for item in project.scenes if item.id == scene_id), None)
        if target is None: raise HTTPError(422, "The selected scene could not be found.", code="H3_SEQUENCE_PROMPT_ERROR")
        prior = [item for item in project.scenes if item.order < target.order]
        if not prior: raise HTTPError(422, "Develop Next Scene requires a previous completed scene.", code="H3_SEQUENCE_PROMPT_ERROR")
        source = max(prior, key=lambda item: item.order)
        version = next((item for item in source.render_versions if item.id == source.selected_render_version_id), None)
        if version is None: raise HTTPError(422, "The previous scene has no selected completed render version.", code="H3_SEQUENCE_PROMPT_ERROR")
        return target, source, version

    @staticmethod
    def _confirmed_continuity_context(project: H3Project, source: H3Scene, version: H3RenderVersion) -> tuple[str, str]:
        """Prefer a user-confirmed outcome over planned prompt prose.

        A render cannot truthfully be visually interpreted without a verified vision
        workflow, so the editable outcome is intentionally the authority when set.
        """
        memory = next((entry for entry in reversed(project.continuity_memory.entries)
                       if entry.scene_id == source.id and entry.render_version_id == version.id), None)
        confirmed_outcome = (
            source.confirmed_outcome.strip()
            if source.confirmed_outcome_render_version_id == version.id
            else ""
        )
        current_state = confirmed_outcome or (memory.current_state if memory else "") or source.prompt
        historical = (memory.summary if memory else source.prompt).strip()
        return current_state[:600], historical[:1200]

    @staticmethod
    def _parsed_suggestion_options(raw: str) -> list[str]:
        lines = [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", line).strip() for line in raw.splitlines()]
        return [line for line in lines if line and "no speech" not in line.lower() and "no music" not in line.lower()]

    @classmethod
    def _suggestion_options(cls, raw: str, current_state: str, historical: str, user_direction: str) -> list[str]:
        options = cls._parsed_suggestion_options(raw)
        reasons: list[str] = []
        if len(options) != 3:
            reasons.append("malformed option count: exactly three concise options are required")
        normalized = [re.sub(r"[^a-z0-9]+", " ", item.lower()).strip() for item in options]
        if len(set(normalized)) != 3:
            reasons.append("duplicate or near-duplicate actions")
        passive = {"reflection", "reflections", "shadow", "shadows", "lighting", "light", "rain", "pavement", "atmosphere"}
        actions = {"enter", "enters", "step", "steps", "open", "opens", "unlock", "unlocks", "check", "checks", "notice", "notices", "turn", "turns", "look", "looks", "wait", "waits", "move", "moves", "reach", "reaches", "approach", "approaches"}
        if any(not (set(re.findall(r"[a-z]+", item.lower())) & actions) for item in options):
            reasons.append("one or more options are too passive or lack a concrete action")
        if all(set(re.findall(r"[a-z]+", item.lower())).issubset(passive | {"the", "a", "an", "and", "with", "at", "in", "of", "to", "figure"}) for item in options):
            reasons.append("all options are atmosphere-only")
        ignored = {"the", "and", "with", "from", "that", "this", "figure", "subject", "same", "scene", "current", "state", "reaches", "reached", "standing", "outside", "night"}
        anchors = {word for word in re.findall(r"[a-z]{4,}", current_state.lower()) if word not in ignored}
        # Keep the check concrete without requiring the model to repeat a location
        # verbatim (for example, "doorway" is a truthful synonym for "entrance").
        synonyms = {
            "entrance": {"entrance", "door", "doorway", "threshold", "lobby"},
            "apartment": {"apartment", "door", "doorway", "threshold", "lobby"},
        }
        grounded = 0
        for option in options:
            words = set(re.findall(r"[a-z]+", option.lower()))
            if words & anchors or any(words & synonyms.get(anchor, set()) for anchor in anchors):
                grounded += 1
        if anchors and grounded < 2:
            reasons.append("current location or confirmed state is not preserved by at least two options")
        historical_words = set(re.findall(r"[a-z]+", historical.lower()))
        prior_place_words = historical_words & {"street", "pavement", "puddle", "sidewalk"}
        if "street" in prior_place_words:
            prior_place_words |= {"pavement", "puddle", "sidewalk"}
        if prior_place_words and any((set(re.findall(r"[a-z]+", item.lower())) & prior_place_words) and not (set(re.findall(r"[a-z]+", item.lower())) & {"entrance", "door", "doorway", "threshold", "lobby"}) for item in options):
            reasons.append("historical location is replayed instead of advancing from the current location")
        direction_words = {word for word in re.findall(r"[a-z]{3,}", user_direction.lower()) if word not in {"closer", "angle", "camera", "shot", "scene", "with", "the", "and", "then", "this", "that", "figure", "subject"}}
        concept_groups = []
        if direction_words & {"code", "keypad", "pin", "digits"}:
            concept_groups.append({"code", "keypad", "pin", "digits", "lock"})
        if direction_words & {"open", "opens", "unlock", "unlocks"}:
            concept_groups.append({"open", "opens", "unlock", "unlocks", "opens"})
        if not (direction_words & {"code", "keypad", "pin", "digits"}) and direction_words & {"enter", "enters", "inside", "through"}:
            concept_groups.append({"enter", "enters", "inside", "through", "step", "steps"})
        if direction_words and not concept_groups:
            concept_groups.append(direction_words)
        if concept_groups:
            for option in options:
                words = set(re.findall(r"[a-z]+", option.lower()))
                if any(not (words & group) for group in concept_groups):
                    reasons.append("user-directed core action is not preserved in every option")
                    break
        if reasons:
            raise SuggestionQualityError(reasons, options)
        return options

    @staticmethod
    def _continuity_location(current_state: str) -> str:
        words = set(re.findall(r"[a-z]+", current_state.lower()))
        if words & {"entrance", "door", "doorway", "threshold", "lobby"}:
            return "apartment entrance / doorway"
        return current_state

    @staticmethod
    def _last_confirmed_action(current_state: str) -> str:
        compact = re.sub(r"^(?:the )?(?:lone )?(?:figure|subject)\s+", "", current_state.strip(), flags=re.IGNORECASE)
        return compact or current_state

    def _record_suggestion_diagnostic(self, *, project: H3Project, target: H3Scene, source: H3Scene, version: H3RenderVersion, request: H3NextScenePromptRequest, current_state: str, user_direction: str, options: list[str], reasons: list[str], elapsed_seconds: float) -> dict[str, object]:
        diagnostic: dict[str, object] = {
            "request_id": request.request_id,
            "project_id": project.id,
            "scene_id": target.id,
            "source_scene_id": source.id,
            "source_render_version_id": version.id,
            "confirmed_outcome": current_state[:600],
            "user_creative_direction": user_direction[:600] or None,
            "rejected_options": [item[:400] for item in options[:3]],
            "rejection_reasons": reasons[:8],
            "provider": "ollama",
            "model": request.model,
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
        self._suggestion_diagnostics.append(diagnostic)
        return diagnostic

    def develop_next_scene(self, project_id: str, scene_id: str, request: H3NextScenePromptRequest) -> H3NextScenePromptResponse:
        project = self._project_store.get_project(project_id); target, source, version = self._next_scene_source(project, scene_id)
        current_state, historical = self._confirmed_continuity_context(project, source, version)
        continuity = f"CURRENT STATE (authoritative): {current_state}\nHISTORICAL CONTEXT (do not replay): {historical}"
        context = H3PromptAssistantRequest(endpoint=request.endpoint, model=request.model, raw_prompt=request.current_user_instruction, scene_number=target.order, scene_name=target.name, scene_mode="continue_previous", duration_seconds=target.duration_seconds, aspect_ratio=target.aspect_ratio, width=target.width, height=target.height, fps=target.fps, project_name=project.name, sequence_mode=project.sequence_mode, previous_scene_number=source.order, previous_scene_name=source.name, previous_scene_prompt=continuity, previous_final_prompt=version.final_submitted_prompt or version.final_prompt, continuity_source_version_id=version.id, audio_mode=target.audio_mode, no_speech=target.no_speech, no_music=target.no_music, custom_audio_instruction=target.custom_audio_instruction)
        try:
            ollama_result = OllamaPromptAssistant().improve(context); developed = ollama_result.suggestion; elapsed_seconds = ollama_result.elapsed_seconds; provider = "ollama"
        except (OllamaPromptAssistantError, ValueError):
            developed = f"Continue directly from the supplied frame of the previous scene. {request.current_user_instruction.strip()} Preserve only known subject, location, atmosphere, and audio continuity; advance the action without replaying the prior scene."; elapsed_seconds = 0.0; provider = "deterministic_local"
        artifact = target.selected_continuity_artifact_id
        message = "Review before applying; this draft is not confirmed continuity." if provider == "ollama" else "Local Ollama was unavailable; a deterministic local draft is ready for review."
        return H3NextScenePromptResponse(provider=provider, developed_prompt=developed, updated_continuity_summary=request.current_user_instruction.strip(), next_scene_summary=request.current_user_instruction.strip(), source_scene_id=source.id, source_render_version_id=version.id, continuity_artifact_id=artifact, message=message, request_id=request.request_id, elapsed_seconds=elapsed_seconds)

    def suggest_next_scene(self, project_id: str, scene_id: str, request: H3NextScenePromptRequest) -> H3NextSceneSuggestionsResponse:
        project = self._project_store.get_project(project_id); target, source, version = self._next_scene_source(project, scene_id)
        state, historical = self._confirmed_continuity_context(project, source, version)
        user_direction = request.current_user_instruction.strip()
        mode = "user_directed_variations" if user_direction else "original_ideas"
        elapsed_seconds = 0.0
        try:
            structured = f"SUGGESTION MODE: {mode}\n\nCURRENT CONFIRMED OUTCOME (primary anchor):\n{state}\n\nCURRENT LOCATION (primary anchor):\n{self._continuity_location(state)}\n\nLAST CONFIRMED ACTION:\n{self._last_confirmed_action(state)}\n\nPERSISTENT CONTINUITY:\nSame lone figure; rainy night; wet urban environment; cinematic realism; natural ambience.\n\nHISTORICAL CONTEXT (secondary; do not replay):\n{historical}\n\nOPTIONAL USER DIRECTION (highest priority when present):\n{user_direction or '(none — invent original next beats)'}\n\nTASK:\n{'Create three concise, genuinely different variations of the user direction. Preserve its core action; vary camera, staging, timing, or emphasis.' if user_direction else 'Create three concise, original next actions that happen immediately after the confirmed outcome.'}"
            context = H3PromptAssistantRequest(endpoint=request.endpoint, model=request.model, raw_prompt=structured, scene_number=target.order, scene_name=target.name, scene_mode="continue_previous", duration_seconds=target.duration_seconds, aspect_ratio=target.aspect_ratio, width=target.width, height=target.height, fps=target.fps, project_name=project.name, sequence_mode=project.sequence_mode, previous_scene_number=source.order, previous_scene_name=source.name, previous_scene_prompt=historical, previous_final_prompt=version.final_submitted_prompt or version.final_prompt, continuity_source_version_id=version.id, audio_mode=target.audio_mode, no_speech=target.no_speech, no_music=target.no_music, custom_audio_instruction=target.custom_audio_instruction, request_id=request.request_id)
            ollama_result = OllamaPromptAssistant().suggest_next_scene(context); raw = ollama_result.suggestion; elapsed_seconds = ollama_result.elapsed_seconds
            options = self._suggestion_options(raw, state, historical, user_direction)
        except SuggestionQualityError as exc:
            diagnostic = self._record_suggestion_diagnostic(project=project, target=target, source=source, version=version, request=request, current_state=state, user_direction=user_direction, options=exc.options, reasons=exc.reasons, elapsed_seconds=elapsed_seconds)
            raise HTTPError(422, "Suggestions were not grounded in the confirmed scene outcome. Refine Scene Outcome and retry.", code="H3_SEQUENCE_SUGGESTION_QUALITY", details={"suggestion_diagnostics": diagnostic}) from exc
        except OllamaPromptAssistantError as exc:
            raise HTTPError(422, str(exc), code="H3_SEQUENCE_SUGGESTION_ERROR") from exc
        message = "Three local Ollama variations based on your direction are ready to stage." if user_direction else "Three local Ollama ideas based on the current scene are ready to stage."
        return H3NextSceneSuggestionsResponse(options=options, source_scene_id=source.id, source_render_version_id=version.id, provider="ollama", mode=mode, message=message, request_id=request.request_id, elapsed_seconds=elapsed_seconds)

    def warm_prompt_assistant(self, endpoint: str, model: str) -> H3PromptAssistantStatusResponse:
        try:
            return OllamaPromptAssistant().warm(endpoint, model)
        except (OllamaPromptAssistantError, ValueError) as exc:
            raise HTTPError(422, str(exc), code="H3_OLLAMA_WARM_ERROR") from exc

    def release_prompt_assistant(self, endpoint: str, model: str) -> H3PromptAssistantStatusResponse:
        try:
            return OllamaPromptAssistant().release(endpoint, model)
        except (OllamaPromptAssistantError, ValueError) as exc:
            raise HTTPError(422, str(exc), code="H3_OLLAMA_RELEASE_ERROR") from exc

    def install_workflow_profile(self, request: H3WorkflowProfileInstallRequest) -> H3WorkflowProfileInstallResponse:
        """Copies only a validated declarative local package into H3 app data."""
        try:
            source = Path(request.folder)
            profile = validate_profile_package(source)
            root = Path(os.environ.get("LOCALAPPDATA", "")) / "H3 Director Desktop" / "workflow-profiles"
            installed = WorkflowProfileRegistry(root).install(source)
            return H3WorkflowProfileInstallResponse(profile_id=str(profile["id"]), version=str(profile["version"]), installed_path=str(installed))
        except (WorkflowProfileError, OSError, ValueError) as exc:
            raise HTTPError(422, str(exc) if isinstance(exc, WorkflowProfileError) else "The local workflow profile could not be installed safely.", code="H3_PROFILE_INSTALL_ERROR") from exc

    def import_ltx25_models(self, request: H3Ltx25ModelImportRequest) -> H3Ltx25ModelImportResponse:
        """Validate/copy exact user-selected gated assets without any download path."""
        try:
            root = resolve_shared_model_root(request.shared_model_paths_config)
            if request.file_paths:
                assets, imported = import_ltx25_assets(root, request.file_paths)
            else:
                assets, imported = inspect_ltx25_assets(root), 0
            return H3Ltx25ModelImportResponse(model_root=str(root), assets=assets, imported_count=imported)
        except (Ltx25ModelImportError, OSError) as exc:
            raise HTTPError(422, str(exc) if isinstance(exc, Ltx25ModelImportError) else "Downloaded model files could not be imported safely.", code="H3_LTX25_MODEL_IMPORT_ERROR") from exc

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

    def continue_from_previous(self, project_id: str, scene_id: str) -> H3ContinuityPrepareResponse:
        """Configure visual-frame continuation within a verified model family."""
        try:
            project = self._project_store.get_project(project_id)
            source = previous_scene(project, scene_id)
            target = next((item for item in project.scenes if item.id == scene_id), None)
            if target is None:
                raise ProjectStoreError("The selected scene could not be found.")
            transitions = {
                "minimax_h3_no_reference": ("minimax_h3_image_to_video", "image_to_video"),
                "ltx_2_5_text_to_video": ("ltx_2_5_image_to_video", "image_to_video"),
            }
            destination = transitions.get(source.workflow_profile_id)
            if destination is None:
                if source.workflow_profile_id not in {"minimax_h3_image_to_video", "ltx_2_5_image_to_video"}:
                    raise ProjectStoreError("This completed scene has no verified image-to-video continuation path.")
                destination = (source.workflow_profile_id, source.workflow_mode)
            project = self._project_store.update_scene(project_id, scene_id, H3SceneUpdateRequest(
                workflow_profile_id=destination[0], workflow_mode=destination[1], mode="continue_previous",
                reference_image=None,
            ))
            scene = next(item for item in project.scenes if item.id == scene_id)
            paths = resolve_h3_runtime_paths()
            artifact = H3ContinuityExtractor(paths.ffmpeg, paths.ffprobe).extract(project, scene)
            project = self._project_store.add_continuity_artifact(project_id, scene_id, artifact)
            return H3ContinuityPrepareResponse(project=project, artifact=artifact)
        except (ProjectStoreError, ContinuityError) as exc:
            raise HTTPError(422, str(exc), code="H3_CONTINUITY_ERROR") from exc

    def start_sequence(self, project_id: str, request: H3SequenceStartRequest) -> H3RenderRun:
        project = self._project_store.get_project(project_id)
        try:
            queued_scenes = resolve_sequence_scenes(project, kind=request.kind, start_scene_id=request.start_scene_id)
        except ProjectStoreError as exc:
            raise HTTPError(422, str(exc), code="H3_SEQUENCE_ERROR") from exc
        # Scene generation contracts, not the project creation profile or the
        # continuity source profile, control the render queue. A prompt-only/T2V
        # source may legitimately transition its next scene to a verified I2V
        # profile after continuity extraction.
        if any(scene.workflow_profile_id != "minimax_h3_image_to_video" for scene in queued_scenes):
            raise HTTPError(422, "This workflow profile is not verified for local rendering.", code="H3_PROFILE_NOT_READY")
        status = self.get_status(request.base_url, "minimax_h3_image_to_video")
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

    def get_status(
        self,
        base_url: str,
        workflow_profile_id: str = "minimax_h3_image_to_video",
    ) -> ComfyUIProbeResponse:
        try:
            if workflow_profile_id == "minimax_h3_no_reference":
                workflow = load_verified_no_reference_workflow(resolve_minimax_h3_no_reference_runtime_paths().workflow)
            else:
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
        result = self._runtime_probe.probe(
            base_url=base_url,
            workflow=workflow,
            profile_id=("minimax_h3_no_reference" if workflow_profile_id == "minimax_h3_no_reference" else "minimax_h3_image_to_video"),
            production_runtime=True,
        )
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
        sequence_status_callback: Callable[[str, str | None, int | None, int | None, str | None], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> H3Project:
        try:
            project = self._project_store.get_project(project_id)
            scene = next((item for item in project.scenes if item.id == scene_id), None)
            if scene is None:
                raise ProjectStoreError("The selected scene could not be found.")
            profile_id = scene.workflow_profile_id
            if profile_id == "ltx_2_5_image_to_video":
                return self._render_ltx_i2v_project_scene(project, scene_id, request)
            if profile_id == "ltx_2_5_text_to_video":
                return self._render_ltx_t2v_project_scene(project, scene_id, request)
            if profile_id == "minimax_h3_no_reference":
                return self._render_minimax_h3_no_reference_project_scene(project, scene_id, request)
            if profile_id != "minimax_h3_image_to_video":
                raise ProjectStoreError("This workflow profile is not verified for local rendering.")
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
                    sequence_status_callback(phase, prompt_id, progress_value, progress_max, diagnostics)

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

    def _render_minimax_h3_no_reference_project_scene(
        self,
        project: H3Project,
        scene_id: str,
        request: H3ProjectRenderRequest,
    ) -> H3Project:
        """Adopt the verified prompt-only output through the normal H3 version flow."""
        scene = next((item for item in project.scenes if item.id == scene_id), None)
        if scene is None:
            raise ProjectStoreError("The selected scene could not be found.")
        if not scene.prompt.strip():
            raise ProjectStoreError("The scene requires a prompt before rendering.")
        if scene.mode != "new_shot":
            raise ProjectStoreError("Prompt Only currently supports independent New Shot scenes only.")
        if (scene.aspect_ratio, scene.resolution_megapixels, scene.width, scene.height, scene.fps, scene.duration_seconds, scene.frame_count) != (
            "1:1 (Square)", 0.4, 640, 640, 24, 5.0, 124,
        ):
            raise ProjectStoreError("Only the verified Prompt Only 1:1 / 640x640 / 24 FPS / 5-second profile is enabled.")
        final_prompt = compose_h3_prompt(scene.prompt, H3AudioGuidance(
            mode=scene.audio_mode, no_speech=scene.no_speech, no_music=scene.no_music,
            custom_instruction=scene.custom_audio_instruction,
        ))
        scene_root = Path(project.project_root) / "scenes" / scene.storage_name
        paths = resolve_minimax_h3_no_reference_runtime_paths(scene_root / "renders")
        provider = self._provider_factory(paths)
        self._project_store.set_scene_status(project.id, scene.id, "rendering", error=None, phase="Submitting Prompt Only")
        try:
            result = provider.render_prompt_only(
                base_url=request.base_url,
                request=PromptOnlySceneRequest(
                    prompt=final_prompt, original_prompt=scene.prompt, seed=scene.seed,
                    aspect_ratio=scene.aspect_ratio, resolution_megapixels=scene.resolution_megapixels,
                    width=scene.width, height=scene.height, duration_seconds=scene.duration_seconds,
                    fps=scene.fps, output_filename_prefix=f"prompt_only_scene_{scene.order:03d}",
                    managed_filename_prefix=f"Scene{scene.order:02d}", audio_mode=scene.audio_mode,
                    no_speech=scene.no_speech, no_music=scene.no_music,
                    custom_audio_instruction=scene.custom_audio_instruction,
                ),
            )
            payload = json.loads(result.metadata_file.read_text(encoding="utf-8"))
            version = H3RenderVersion(
                id=result.render_directory.name, number=int(result.render_directory.name.removeprefix("v")),
                created_at=str(payload["created_at"]), root=str(result.render_directory),
                video_file=str(result.output_file), metadata_file=str(result.metadata_file),
                prompt=scene.prompt, final_prompt=final_prompt, audio_mode=scene.audio_mode,
                no_speech=scene.no_speech, no_music=scene.no_music,
                custom_audio_instruction=scene.custom_audio_instruction,
                input_image_reference="No reference image used", seed=scene.seed, width=scene.width,
                height=scene.height, fps=scene.fps, duration_seconds=scene.duration_seconds,
                frame_count=result.video.frame_count, prompt_id=result.prompt_id,
                input_image_sha256="not-applicable", workflow_sha256=str(payload["workflow_sha256"]),
                output_sha256=str(payload["output_sha256"]), ffprobe=MiniMaxH3VideoProbeResponse(**result.video.__dict__),
            )
            updated = self._project_store.add_render_version(project.id, scene.id, version)
            return self._project_store.set_scene_status(updated.id, scene.id, "complete", error=None, phase="Complete")
        except (ProviderError, ProjectStoreError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            safe_error = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError)) else "The local Prompt Only render could not be adopted safely."
            self._project_store.set_scene_status(project.id, scene.id, "failed", error=safe_error, phase="Failed")
            raise HTTPError(422, safe_error, code="MINIMAX_H3_NO_REFERENCE_RENDER_FAILED") from exc

    def _render_ltx_i2v_project_scene(
        self,
        project: H3Project,
        scene_id: str,
        request: H3ProjectRenderRequest,
    ) -> H3Project:
        scene = next((item for item in project.scenes if item.id == scene_id), None)
        if scene is None:
            raise ProjectStoreError("The selected scene could not be found.")
        if not scene.prompt.strip():
            raise ProjectStoreError("LTX 2.5 Image-to-Video requires a prompt.")
        if not is_ltx_product_validation_preset(scene.aspect_ratio, scene.resolution_megapixels, scene.width, scene.height) or (scene.fps, scene.duration_seconds, scene.frame_count) != (24, 5.0, 121):
            raise ProjectStoreError("Only the runtime-verified LTX configuration or an approved supervised validation preset is supported.")
        scene_root = Path(project.project_root) / "scenes" / scene.storage_name
        paths = resolve_ltx_i2v_runtime_paths(scene_root / "renders")
        provider = ComfyUILtx25I2VProvider(
            workflow_path=paths.workflow, output_root=paths.comfyui_output,
            render_root=paths.render_root, ffprobe_path=paths.ffprobe,
        )
        self._project_store.set_scene_status(project.id, scene.id, "rendering", error=None, phase="Submitting LTX 2.5")
        try:
            input_image = self._resolve_render_input(project, scene)
            result = provider.render(
                base_url=request.base_url,
                request=LtxI2VRequest(
                    prompt=scene.prompt, input_image=input_image, seed=scene.seed,
                    prompt_enhance=scene.ltx_prompt_enhance, aspect_ratio=scene.aspect_ratio,
                    resolution_megapixels=scene.resolution_megapixels, width=scene.width, height=scene.height,
                    duration_seconds=scene.duration_seconds, fps=scene.fps, frame_count=scene.frame_count,
                    output_filename_prefix=f"ltx_scene_{scene.order:03d}", reference_fit=scene.reference_fit,
                ),
            )
            payload = json.loads(result.metadata_file.read_text(encoding="utf-8"))
            number = int(result.render_directory.name.removeprefix("v"))
            version = H3RenderVersion(
                id=result.render_directory.name, number=number, created_at=str(payload["created_at"]),
                root=str(result.render_directory), video_file=str(result.output_file), metadata_file=str(result.metadata_file),
                prompt=scene.prompt, final_prompt=scene.prompt, audio_mode="natural_ambience", no_speech=False,
                no_music=False, custom_audio_instruction="", input_image_reference=str(input_image),
                seed=scene.seed, width=scene.width, height=scene.height, fps=scene.fps,
                duration_seconds=scene.duration_seconds, frame_count=result.video.frame_count, prompt_id=result.prompt_id,
                input_image_sha256=str(payload["input_image_sha256"]), workflow_sha256=str(payload["workflow_sha256"]),
                output_sha256=str(payload["output_sha256"]), ffprobe=MiniMaxH3VideoProbeResponse(**result.video.__dict__),
            )
            updated = self._project_store.add_render_version(project.id, scene.id, version)
            return self._project_store.set_scene_status(updated.id, scene.id, "complete", error=None, phase="Complete")
        except (ProviderError, ProjectStoreError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            safe_error = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError)) else "The local LTX render could not be adopted safely."
            self._project_store.set_scene_status(project.id, scene.id, "failed", error=safe_error, phase="Failed")
            raise HTTPError(422, safe_error, code="LTX_2_5_I2V_RENDER_FAILED") from exc

    def _render_ltx_t2v_project_scene(self, project: H3Project, scene_id: str, request: H3ProjectRenderRequest) -> H3Project:
        scene = next((item for item in project.scenes if item.id == scene_id), None)
        if scene is None: raise ProjectStoreError("The selected scene could not be found.")
        if not scene.prompt.strip(): raise ProjectStoreError("LTX 2.5 Text-to-Video requires a prompt.")
        if not is_ltx_product_validation_preset(scene.aspect_ratio, scene.resolution_megapixels, scene.width, scene.height) or (scene.fps, scene.duration_seconds, scene.frame_count) != (24, 5.0, 121):
            raise ProjectStoreError("Only the runtime-verified LTX configuration or an approved supervised validation preset is supported.")
        scene_root = Path(project.project_root) / "scenes" / scene.storage_name
        paths = resolve_ltx_t2v_runtime_paths(scene_root / "renders")
        provider = ComfyUILtx25T2VProvider(workflow_path=paths.workflow, output_root=paths.comfyui_output, render_root=paths.render_root, ffprobe_path=paths.ffprobe)
        self._project_store.set_scene_status(project.id, scene.id, "rendering", error=None, phase="Submitting LTX 2.5 T2V")
        try:
            audio_guidance = compose_h3_prompt(scene.prompt, H3AudioGuidance(
                mode=scene.audio_mode, no_speech=scene.no_speech,
                no_music=scene.no_music, custom_instruction=scene.custom_audio_instruction,
            ))
            result = provider.render(base_url=request.base_url, request=LtxT2VRequest(prompt=scene.prompt, prompt_enhance=scene.ltx_prompt_enhance, seed=scene.seed, aspect_ratio=scene.aspect_ratio, resolution_megapixels=scene.resolution_megapixels, width=scene.width, height=scene.height, duration_seconds=scene.duration_seconds, fps=scene.fps, frame_count=scene.frame_count, output_filename_prefix=f"ltx_t2v_scene_{scene.order:03d}", audio_guidance=audio_guidance))
            payload = json.loads(result.metadata_file.read_text(encoding="utf-8")); number = int(result.render_directory.name.removeprefix("v"))
            version = H3RenderVersion(id=result.render_directory.name, number=number, created_at=str(payload["created_at"]), render_started_at=payload.get("render_started_at"), render_completed_at=payload.get("render_completed_at"), render_elapsed_seconds=payload.get("render_elapsed_seconds", payload.get("elapsed_seconds")), root=str(result.render_directory), video_file=str(result.output_file), metadata_file=str(result.metadata_file), prompt=scene.prompt, final_prompt=payload.get("final_submitted_prompt", scene.prompt), raw_user_prompt=payload.get("raw_user_prompt"), improved_prompt=payload.get("improved_prompt"), native_enhanced_prompt=payload.get("native_enhanced_prompt"), final_submitted_prompt=payload.get("final_submitted_prompt"), native_prompt_enhance=payload.get("native_prompt_enhance"), audio_mode=scene.audio_mode, no_speech=scene.no_speech, no_music=scene.no_music, custom_audio_instruction=scene.custom_audio_instruction, input_image_reference="No reference image used", seed=scene.seed, width=scene.width, height=scene.height, fps=scene.fps, duration_seconds=scene.duration_seconds, frame_count=result.video.frame_count, prompt_id=result.prompt_id, input_image_sha256="not-applicable", workflow_sha256=str(payload["workflow_sha256"]), output_sha256=str(payload["output_sha256"]), ffprobe=MiniMaxH3VideoProbeResponse(**result.video.__dict__))
            updated = self._project_store.add_render_version(project.id, scene.id, version)
            return self._project_store.set_scene_status(updated.id, scene.id, "complete", error=None, phase="Complete")
        except (ProviderError, ProjectStoreError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            safe_error = str(exc) if isinstance(exc, (ProviderError, ProjectStoreError)) else "The local LTX T2V render could not be adopted safely."
            self._project_store.set_scene_status(project.id, scene.id, "failed", error=safe_error, phase="Failed")
            raise HTTPError(422, safe_error, code="LTX_2_5_T2V_RENDER_FAILED") from exc

    def _render_for_sequence(
        self,
        project_id: str,
        scene_id: str,
        request: H3ProjectRenderRequest,
        status_callback: Callable[[str, int | None, int | None, str | None], None],
        cancel_requested: Callable[[], bool],
    ) -> H3Project:
        return self.render_project_scene(project_id, scene_id, request, status_callback, cancel_requested)

    @staticmethod
    def _workflow_center() -> WorkflowCenter:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if not local:
            raise HTTPError(503, "The local H3 application-data folder is unavailable.")
        return WorkflowCenter(Path(local) / "H3 Director Desktop" / "workflow-center")

    def list_workflow_center(self) -> list[dict[str, object]]:
        return self._workflow_center().list()

    def import_workflow_center(self, source_path: str) -> dict[str, object]:
        try:
            return self._workflow_center().import_json(Path(source_path))
        except WorkflowCenterError as exc:
            raise HTTPError(422, str(exc), code="H3_WORKFLOW_IMPORT_ERROR") from exc

    def validate_workflow_center(self, workflow_id: str, base_url: str, model_roots: list[str]) -> dict[str, object]:
        try:
            endpoint = require_loopback_http_url(base_url)
            response = requests.get(f"{endpoint}/object_info", timeout=10)
            response.raise_for_status()
            roots = [Path(item).resolve() for item in model_roots if item and Path(item).is_dir()]
            return self._workflow_center().validate(workflow_id, response.json(), roots)
        except (requests.RequestException, WorkflowCenterError, ValueError) as exc:
            raise HTTPError(422, f"Workflow validation could not complete: {exc}", code="H3_WORKFLOW_VALIDATION_ERROR") from exc

    def save_workflow_center_mappings(self, workflow_id: str, mappings: list[dict[str, str]]) -> dict[str, object]:
        try: return self._workflow_center().save_mappings(workflow_id, mappings)
        except WorkflowCenterError as exc: raise HTTPError(422, str(exc), code="H3_WORKFLOW_MAPPING_ERROR") from exc

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
