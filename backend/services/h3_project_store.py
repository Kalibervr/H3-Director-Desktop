"""Atomic, app-owned persistence for H3 Director projects and scene versions."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from api_types import (
    H3_RESOLUTION_PRESETS,
    H3Project,
    H3ProjectSettings,
    H3ContinuityArtifact,
    H3ContinuityMemory,
    H3ContinuityMemoryEntry,
    H3RenderRun,
    H3RenderVersion,
    H3UpscaleVariant,
    H3Scene,
    H3SceneUpdateRequest,
)
from services.ltx_2_5_geometry import resolve_ltx_geometry


class ProjectStoreError(RuntimeError):
    """A safe persistence error suitable for the local UI."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_slug(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-_")
    return (normalized[:48] or "project").lower()


def _scene_storage_name(number: int) -> str:
    return f"scene_{number:03d}"


def _atomic_json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows can transiently hold project.json during a concurrent UI refresh.
        # The temporary file is complete and fsynced, so retrying the final atomic
        # replacement preserves the no-partial-write guarantee.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProjectStoreError("The local project could not be saved safely.") from exc


class H3ProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()
        # A run belongs to a coordinator only for the lifetime of this backend
        # process.  Persisted runs without that in-memory ownership are safe to
        # examine on reopen; this deliberately does not confuse a UI remount
        # with a still-live backend render.
        self._active_run_keys: set[tuple[str, str]] = set()
        self._active_run_lock = threading.RLock()

    def list_projects(self) -> list[H3Project]:
        if not self.projects_root.exists():
            return []
        projects: list[H3Project] = []
        try:
            candidates = list(self.projects_root.iterdir())
        except OSError as exc:
            raise ProjectStoreError("The local projects folder is unavailable.") from exc
        for directory in candidates:
            if not directory.is_dir():
                continue
            metadata = directory / "project.json"
            if not metadata.is_file():
                continue
            try:
                projects.append(self._read_file(metadata))
            except ProjectStoreError:
                continue
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def create_project(self, name: str, scene_count: int = 1, sequence_mode: str = "independent_shots", workflow_profile_id: str = "minimax_h3_image_to_video", workflow_mode: str = "image_to_video") -> H3Project:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ProjectStoreError("A project name is required.")
        project_id = uuid.uuid4().hex
        # The display name is deliberately not used as immutable identity: renaming a
        # project never moves its existing scenes or render references.
        creation_date = datetime.now(UTC).date().isoformat()
        root = self.projects_root / f"{creation_date} - {_safe_slug(cleaned_name)} [{project_id[:8]}]"
        if scene_count < 1 or scene_count > 999:
            raise ProjectStoreError("The scene count must be between 1 and 999.")
        try:
            root.mkdir(parents=True, exist_ok=False)
            (root / "assets" / "references").mkdir(parents=True)
            for number in range(1, scene_count + 1):
                scene_root = root / "scenes" / _scene_storage_name(number)
                (scene_root / "inputs").mkdir(parents=True)
                (scene_root / "renders").mkdir(parents=True)
        except OSError as exc:
            raise ProjectStoreError("The local project folder could not be created.") from exc
        timestamp = _now()
        scenes = [self._new_scene(number, _scene_storage_name(number), workflow_profile_id=workflow_profile_id, workflow_mode=workflow_mode) for number in range(1, scene_count + 1)]
        if workflow_profile_id == "ltx_2_5_image_to_video":
            # Preserve the independently verified I2V profile settings.
            scenes = [scene.model_copy(update={
                "aspect_ratio": "16:9 (Widescreen)",
                "resolution_megapixels": 0.9,
                "width": 1280,
                "height": 704,
                "fps": 24,
                "frame_count": 121,
                "ltx_prompt_enhance": True,
            }) for scene in scenes]
        if workflow_profile_id == "ltx_2_5_text_to_video":
            # The official T2V export independently proves this locked initial
            # configuration.  Keeping this block separate prevents T2V from
            # inheriting I2V image assumptions as profiles evolve.
            scenes = [scene.model_copy(update={
                "aspect_ratio": "16:9 (Widescreen)",
                "resolution_megapixels": 0.9,
                "width": 1280,
                "height": 704,
                "fps": 24,
                "frame_count": 121,
                "ltx_prompt_enhance": True,
            }) for scene in scenes]
        if sequence_mode == "continuous_sequence":
            scenes = [scene.model_copy(update={"mode": "new_shot" if scene.order == 1 else "continue_previous"}) for scene in scenes]
        project = H3Project(
            schema_version=18,
            id=project_id,
            name=cleaned_name,
            created_at=timestamp,
            updated_at=timestamp,
            project_root=str(root),
            settings=H3ProjectSettings(width=640, height=640, fps=24, duration_seconds=5.0, frame_count=124),
            sequence_mode=sequence_mode,
            workflow_profile_id=workflow_profile_id,
            workflow_mode=workflow_mode,
            scenes=scenes,
            selected_scene_id=scenes[0].id,
            render_runs=[],
            continuity_memory=H3ContinuityMemory(),
        )
        self.save_project(project)
        return project

    def get_project(self, project_id: str) -> H3Project:
        for project in self.list_projects():
            if project.id == project_id:
                return project
        raise ProjectStoreError("The local project could not be found.")

    def claim_active_run(self, project_id: str, run_id: str) -> None:
        """Record coordinator ownership before a persisted run can be reopened."""
        with self._active_run_lock:
            self._active_run_keys.add((project_id, run_id))

    def release_active_run(self, project_id: str, run_id: str) -> None:
        with self._active_run_lock:
            self._active_run_keys.discard((project_id, run_id))

    def _run_is_active_here(self, project_id: str, run_id: str) -> bool:
        with self._active_run_lock:
            return (project_id, run_id) in self._active_run_keys

    def reopen_project(self, project_root: Path) -> H3Project:
        resolved = project_root.resolve()
        try:
            resolved.relative_to(self.projects_root)
        except ValueError as exc:
            raise ProjectStoreError("Only app-owned H3 Director projects can be reopened.") from exc
        return self._read_file(resolved / "project.json")

    def save_project(self, project: H3Project) -> H3Project:
        root = Path(project.project_root).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as exc:
            raise ProjectStoreError("The project path is outside the app-owned projects folder.") from exc
        updated = project.model_copy(update={"updated_at": _now()})
        _atomic_json_write(root / "project.json", updated.model_dump(mode="json"))
        return updated

    def rename_project(self, project_id: str, name: str) -> H3Project:
        cleaned = name.strip()
        if not cleaned:
            raise ProjectStoreError("A project name is required.")
        project = self.get_project(project_id)
        return self.save_project(project.model_copy(update={"name": cleaned}))

    def delete_project(self, project_id: str) -> None:
        """Recoverably archive one app-owned project without following external paths."""
        project = self.get_project(project_id)
        self._require_no_active_run(project)
        root = Path(project.project_root).resolve()
        try:
            root.relative_to(self.projects_root)
        except ValueError as exc:
            raise ProjectStoreError("Only app-owned H3 Director projects can be deleted.") from exc
        trash_root = self.projects_root / ".trash"
        destination = trash_root / f"{project.id}-{uuid.uuid4().hex[:8]}"
        try:
            trash_root.mkdir(parents=True, exist_ok=True)
            os.replace(root, destination)
        except OSError as exc:
            raise ProjectStoreError("The project could not be moved to H3 Director Trash safely.") from exc

    def update_project(self, project_id: str, *, name: str | None = None, sequence_mode: str | None = None, workflow_profile_id: str | None = None, workflow_mode: str | None = None) -> H3Project:
        project = self.get_project(project_id)
        changes: dict[str, str] = {}
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ProjectStoreError("A project name is required.")
            changes["name"] = cleaned
        if sequence_mode is not None:
            changes["sequence_mode"] = sequence_mode
        if workflow_profile_id is not None:
            changes["workflow_profile_id"] = workflow_profile_id
        if workflow_mode is not None:
            changes["workflow_mode"] = workflow_mode
        return self.save_project(project.model_copy(update=changes))

    def update_scene(self, project_id: str, scene_id: str, update: H3SceneUpdateRequest) -> H3Project:
        project = self.get_project(project_id)
        target = next((scene for scene in project.scenes if scene.id == scene_id), None)
        if target is None:
            raise ProjectStoreError("The selected scene could not be found.")
        scenes: list[H3Scene] = []
        found = False
        changes = update.model_dump(exclude_none=True)
        aspect_ratio = changes.get("aspect_ratio", target.aspect_ratio)
        megapixels = changes.get("resolution_megapixels", target.resolution_megapixels)
        if "aspect_ratio" in changes or "resolution_megapixels" in changes:
            scene_profile_id = changes.get("workflow_profile_id", target.workflow_profile_id)
            if scene_profile_id in {"ltx_2_5_image_to_video", "ltx_2_5_text_to_video"}:
                geometry = resolve_ltx_geometry(aspect_ratio, megapixels)
                changes["width"], changes["height"] = geometry.final_width, geometry.final_height
            else:
                changes["width"], changes["height"] = H3_RESOLUTION_PRESETS[aspect_ratio][megapixels]
        for scene in project.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            found = True
            selected_version = changes.get("selected_render_version_id")
            if selected_version is not None and not any(
                version.id == selected_version for version in scene.render_versions
            ):
                raise ProjectStoreError("The selected render version could not be found.")
            if "confirmed_outcome" in changes:
                changes["confirmed_outcome_render_version_id"] = (
                    scene.selected_render_version_id if changes["confirmed_outcome"].strip() else None
                )
            scenes.append(scene.model_copy(update=changes))
        if not found:
            raise ProjectStoreError("The selected scene could not be found.")
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

    def select_scene(self, project_id: str, scene_id: str) -> H3Project:
        project = self.get_project(project_id)
        if not any(scene.id == scene_id for scene in project.scenes):
            raise ProjectStoreError("The selected scene could not be found.")
        return self.save_project(project.model_copy(update={"selected_scene_id": scene_id}))

    def add_scene(self, project_id: str) -> H3Project:
        project = self.get_project(project_id)
        storage_number = self._next_storage_number(project)
        scene = self._new_scene(len(project.scenes) + 1, _scene_storage_name(storage_number))
        return self._add_scene_folder_then_save(project, scene)

    def duplicate_scene(self, project_id: str, scene_id: str) -> H3Project:
        project = self.get_project(project_id)
        source = next((scene for scene in project.scenes if scene.id == scene_id), None)
        if source is None:
            raise ProjectStoreError("The selected scene could not be found.")
        storage_number = self._next_storage_number(project)
        duplicate = self._new_scene(
            len(project.scenes) + 1,
            _scene_storage_name(storage_number),
            source=source,
        )
        return self._add_scene_folder_then_save(project, duplicate)

    def reorder_scenes(self, project_id: str, scene_ids: list[str]) -> H3Project:
        project = self.get_project(project_id)
        self._require_no_active_run(project)
        current_ids = [scene.id for scene in project.scenes]
        if len(scene_ids) != len(set(scene_ids)) or set(scene_ids) != set(current_ids):
            raise ProjectStoreError("The scene order must contain every scene exactly once.")
        by_id = {scene.id: scene for scene in project.scenes}
        scenes = [by_id[scene_id].model_copy(update={"order": index}) for index, scene_id in enumerate(scene_ids, 1)]
        return self.save_project(project.model_copy(update={"scenes": scenes}))

    def delete_scene(self, project_id: str, scene_id: str) -> H3Project:
        project = self.get_project(project_id)
        self._require_no_active_run(project)
        if len(project.scenes) == 1:
            raise ProjectStoreError("A project must keep at least one scene.")
        target = next((scene for scene in project.scenes if scene.id == scene_id), None)
        if target is None:
            raise ProjectStoreError("The selected scene could not be found.")
        if target.status in {"queued", "preparing", "submitted", "rendering", "encoding", "verifying"}:
            raise ProjectStoreError("An active scene cannot be deleted.")
        root = Path(project.project_root)
        source = root / "scenes" / target.storage_name
        archive = root / "scenes" / "archive" / f"{target.storage_name}_{uuid.uuid4().hex}"
        try:
            archive.parent.mkdir(parents=True, exist_ok=True)
            source.replace(archive)
        except OSError as exc:
            raise ProjectStoreError("The scene folder could not be archived safely.") from exc
        remaining = [scene for scene in project.scenes if scene.id != scene_id]
        scenes = [scene.model_copy(update={"order": index}) for index, scene in enumerate(remaining, 1)]
        selected_id = project.selected_scene_id
        if selected_id == scene_id:
            selected_id = scenes[min(target.order - 1, len(scenes) - 1)].id
        try:
            return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": selected_id}))
        except ProjectStoreError:
            try:
                archive.replace(source)
            except OSError:
                pass
            raise

    def set_scene_status(
        self,
        project_id: str,
        scene_id: str,
        status: str,
        *,
        prompt_id: str | None = None,
        error: str | None = None,
        phase: str | None = None,
        progress_value: int | None = None,
        progress_max: int | None = None,
        diagnostics: str | None = None,
    ) -> H3Project:
        project = self.get_project(project_id)
        scenes = [
            scene.model_copy(update={
                "status": status,
                "active_prompt_id": prompt_id if prompt_id is not None else scene.active_prompt_id,
                "last_error": error,
                "current_phase": phase or status,
                "progress_value": progress_value,
                "progress_max": progress_max,
                "diagnostics": diagnostics,
            }) if scene.id == scene_id else scene
            for scene in project.scenes
        ]
        return self.save_project(project.model_copy(update={"scenes": scenes}))

    def add_render_version(
        self,
        project_id: str,
        scene_id: str,
        version: H3RenderVersion,
    ) -> H3Project:
        project = self.get_project(project_id)
        version = self._hydrate_render_timing(version)
        scenes: list[H3Scene] = []
        found = False
        for scene in project.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            found = True
            if any(item.id == version.id for item in scene.render_versions):
                raise ProjectStoreError("The immutable render version already exists.")
            scenes.append(scene.model_copy(update={
                "render_versions": [*scene.render_versions, version],
                "selected_render_version_id": version.id,
                "status": "complete",
                "active_prompt_id": version.prompt_id,
                "last_error": None,
                "current_phase": "Complete",
                "progress_value": None,
                "progress_max": None,
                "diagnostics": None,
            }))
        if not found:
            raise ProjectStoreError("The selected scene could not be found.")
        completed_scene = next(item for item in scenes if item.id == scene_id)
        prompt = version.final_submitted_prompt or version.final_prompt or version.prompt
        compact = re.sub(r"\s+", " ", prompt).strip()[:1200]
        confirmed = (
            completed_scene.confirmed_outcome.strip()
            if completed_scene.confirmed_outcome_render_version_id == version.id
            else ""
        )
        entry = H3ContinuityMemoryEntry(scene_id=scene_id, render_version_id=version.id, summary=compact, current_state=confirmed or compact[:600], audio_summary=completed_scene.custom_audio_instruction)
        memory = project.continuity_memory.model_copy(update={"entries": [*project.continuity_memory.entries, entry]})
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id, "continuity_memory": memory}))

    def add_upscale_variant(self, project_id: str, scene_id: str, source_version_id: str, variant: H3UpscaleVariant) -> H3Project:
        """Persist a derived render beside its immutable source version atomically."""
        project = self.get_project(project_id)
        scenes: list[H3Scene] = []
        found = False
        for scene in project.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            versions = []
            for version in scene.render_versions:
                if version.id != source_version_id:
                    versions.append(version)
                    continue
                found = True
                if any(item.id == variant.id for item in version.upscale_variants):
                    raise ProjectStoreError("The immutable RTX VSR version already exists.")
                versions.append(version.model_copy(update={"upscale_variants": [*version.upscale_variants, variant]}))
            scenes.append(scene.model_copy(update={"render_versions": versions}))
        if not found:
            raise ProjectStoreError("The source render version could not be found.")
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

    def add_continuity_artifact(
        self,
        project_id: str,
        scene_id: str,
        artifact: H3ContinuityArtifact,
    ) -> H3Project:
        project = self.get_project(project_id)
        scenes: list[H3Scene] = []
        found = False
        for scene in project.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            found = True
            if any(item.id == artifact.id for item in scene.continuity_artifacts):
                raise ProjectStoreError("The immutable continuity artifact already exists.")
            scenes.append(scene.model_copy(update={
                "continuity_artifacts": [*scene.continuity_artifacts, artifact],
                "selected_continuity_artifact_id": artifact.id,
            }))
        if not found:
            raise ProjectStoreError("The selected scene could not be found.")
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

    def add_render_run(self, project_id: str, run: H3RenderRun) -> H3Project:
        project = self.get_project(project_id)
        self._require_no_active_run(project)
        if any(item.id == run.id for item in project.render_runs):
            raise ProjectStoreError("The render run already exists.")
        return self.save_project(project.model_copy(update={"render_runs": [*project.render_runs, run]}))

    def update_render_run(self, project_id: str, run: H3RenderRun) -> H3Project:
        project = self.get_project(project_id)
        found = False
        runs: list[H3RenderRun] = []
        for existing in project.render_runs:
            if existing.id == run.id:
                found = True
                runs.append(run)
            else:
                runs.append(existing)
        if not found:
            raise ProjectStoreError("The render run could not be found.")
        return self.save_project(project.model_copy(update={"render_runs": runs}))

    @staticmethod
    def _require_no_active_run(project: H3Project) -> None:
        if any(run.status == "running" for run in project.render_runs):
            raise ProjectStoreError("Scene order cannot change while a render queue is active.")

    @staticmethod
    def _hydrate_render_timing(version: H3RenderVersion) -> H3RenderVersion:
        """Promote a provider's local elapsed measurement into project metadata.

        Older immutable versions remain intentionally unset; their file times are
        not a substitute for a measured render interval.
        """
        try:
            payload = json.loads(Path(version.metadata_file).read_text(encoding="utf-8"))
            changes: dict[str, object] = {}
            for field, metadata_key in (
                ("raw_user_prompt", "raw_user_prompt"),
                ("improved_prompt", "improved_prompt"),
                ("native_enhanced_prompt", "native_enhanced_prompt"),
                ("final_submitted_prompt", "final_submitted_prompt"),
                ("native_prompt_enhance", "native_prompt_enhance"),
            ):
                value = payload.get(metadata_key)
                if getattr(version, field) is None and (isinstance(value, str) or (field == "native_prompt_enhance" and isinstance(value, bool))):
                    changes[field] = value
            if version.render_elapsed_seconds is not None:
                return version.model_copy(update=changes) if changes else version
            elapsed = payload.get("render_elapsed_seconds", payload.get("elapsed_seconds"))
            if isinstance(elapsed, (int, float)) and elapsed >= 0:
                completed = version.render_completed_at or payload.get("render_completed_at") or version.created_at
                started = version.render_started_at or payload.get("render_started_at")
                if started is None:
                    try:
                        completed_at = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                        started = (completed_at - timedelta(seconds=float(elapsed))).isoformat()
                    except (TypeError, ValueError):
                        started = None
                return version.model_copy(update={**changes,
                    "render_elapsed_seconds": float(elapsed),
                    "render_started_at": started,
                    "render_completed_at": completed,
                })
            if changes:
                return version.model_copy(update=changes)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return version

    @staticmethod
    def _new_scene(
        order: int, storage_name: str, source: H3Scene | None = None,
        workflow_profile_id: str = "minimax_h3_image_to_video", workflow_mode: str = "image_to_video",
    ) -> H3Scene:
        return H3Scene(
            id=uuid.uuid4().hex,
            storage_name=storage_name,
            order=order,
            name=f"{source.name} Copy" if source else f"Scene {order:02d}",
            prompt=source.prompt if source else "",
            audio_mode=source.audio_mode if source else "natural_ambience",
            no_speech=source.no_speech if source else False,
            no_music=source.no_music if source else False,
            custom_audio_instruction=source.custom_audio_instruction if source else "",
            reference_image=source.reference_image if source else None,
            reference_fit=source.reference_fit if source else "fill_crop",
            ltx_prompt_enhance=source.ltx_prompt_enhance if source else False,
            workflow_profile_id=source.workflow_profile_id if source else workflow_profile_id,
            workflow_mode=source.workflow_mode if source else workflow_mode,
            aspect_ratio=source.aspect_ratio if source else "1:1 (Square)",
            resolution_megapixels=source.resolution_megapixels if source else 0.4,
            width=source.width if source else 640,
            height=source.height if source else 640,
            fps=source.fps if source else 24,
            duration_seconds=source.duration_seconds if source else 5.0,
            frame_count=source.frame_count if source else 124,
            seed=source.seed if source else 193554738272393,
            mode=source.mode if source else "new_shot",
            continuity_strategy=source.continuity_strategy if source else "last_valid_frame",
            continuity_offset_frames=source.continuity_offset_frames if source else 0,
            selected_continuity_artifact_id=None,
            continuity_artifacts=[],
            status="idle",
            selected_render_version_id=None,
            render_versions=[],
            last_error=None,
            active_prompt_id=None,
            current_phase=None,
            progress_value=None,
            progress_max=None,
            diagnostics=None,
        )

    @staticmethod
    def _next_storage_number(project: H3Project) -> int:
        numbers = [int(scene.storage_name.removeprefix("scene_")) for scene in project.scenes]
        scenes_root = Path(project.project_root) / "scenes"
        if scenes_root.exists():
            numbers.extend(
                int(path.name.removeprefix("scene_"))
                for path in scenes_root.glob("scene_[0-9][0-9][0-9]")
                if path.is_dir()
            )
        return max(numbers, default=0) + 1

    def _add_scene_folder_then_save(self, project: H3Project, scene: H3Scene) -> H3Project:
        scene_root = Path(project.project_root) / "scenes" / scene.storage_name
        try:
            (scene_root / "inputs").mkdir(parents=True, exist_ok=False)
            (scene_root / "renders").mkdir()
        except OSError as exc:
            raise ProjectStoreError("The scene folder could not be created safely.") from exc
        try:
            return self.save_project(project.model_copy(update={
                "scenes": [*project.scenes, scene],
                "selected_scene_id": scene.id,
            }))
        except ProjectStoreError:
            try:
                (scene_root / "inputs").rmdir()
                (scene_root / "renders").rmdir()
                scene_root.rmdir()
            except OSError:
                pass
            raise

    def _read_file(self, path: Path) -> H3Project:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            original_schema = payload.get("schema_version")
            migrated = original_schema in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}
            if payload.get("schema_version") == 1:
                for index, scene in enumerate(payload.get("scenes", []), 1):
                    scene["storage_name"] = _scene_storage_name(int(scene.get("order", index)))
            if migrated:
                payload["schema_version"] = 18
                payload.setdefault("continuity_memory", {"entries": []})
                payload.setdefault("sequence_mode", "independent_shots")
                payload.setdefault("workflow_profile_id", "minimax_h3_image_to_video")
                payload.setdefault("workflow_mode", "image_to_video")
                for scene in payload.get("scenes", []):
                    scene.setdefault("workflow_profile_id", payload["workflow_profile_id"])
                    scene.setdefault("workflow_mode", payload["workflow_mode"])
                    scene.setdefault("mode", "new_shot")
                    scene.setdefault("confirmed_outcome", "")
                    # v17 stored outcomes per scene. Bind a migrated outcome to
                    # the version selected at migration time rather than
                    # claiming it describes another version later.
                    scene.setdefault(
                        "confirmed_outcome_render_version_id",
                        scene.get("selected_render_version_id") if scene.get("confirmed_outcome", "").strip() else None,
                    )
                    scene.setdefault("reference_fit", "fill_crop")
                    scene.setdefault("ltx_prompt_enhance", False)
                    scene.setdefault("audio_mode", "natural_ambience")
                    scene.setdefault("no_speech", False)
                    scene.setdefault("no_music", False)
                    scene.setdefault("custom_audio_instruction", "")
                    scene.setdefault("aspect_ratio", "1:1 (Square)")
                    scene.setdefault("resolution_megapixels", 0.4)
                    scene.setdefault("continuity_strategy", "last_valid_frame")
                    scene.setdefault("continuity_offset_frames", 0)
                    scene.setdefault("selected_continuity_artifact_id", None)
                    scene.setdefault("continuity_artifacts", [])
                    scene.setdefault("current_phase", None)
                    scene.setdefault("progress_value", None)
                    scene.setdefault("progress_max", None)
                    scene.setdefault("diagnostics", None)
                payload.setdefault("render_runs", [])
                for scene in payload.get("scenes", []):
                    for version in scene.get("render_versions", []):
                        version.setdefault("final_prompt", version.get("prompt"))
                        version.setdefault("audio_mode", scene.get("audio_mode", "natural_ambience"))
                        version.setdefault("no_speech", scene.get("no_speech", False))
                        version.setdefault("no_music", scene.get("no_music", False))
                        version.setdefault("custom_audio_instruction", scene.get("custom_audio_instruction", ""))
                        version.setdefault("upscale_variants", [])
                        version.setdefault("render_started_at", None)
                        version.setdefault("render_completed_at", None)
                        version.setdefault("render_elapsed_seconds", None)
                        version.setdefault("raw_user_prompt", None)
                        version.setdefault("improved_prompt", None)
                        version.setdefault("native_enhanced_prompt", None)
                        version.setdefault("final_submitted_prompt", None)
                        version.setdefault("native_prompt_enhance", None)
                        for variant in version["upscale_variants"]:
                            variant.setdefault("processing_elapsed_seconds", None)
                for run in payload.get("render_runs", []):
                    for item in run.get("items", []):
                        item.setdefault("current_phase", None)
                        item.setdefault("progress_value", None)
                        item.setdefault("progress_max", None)
                        item.setdefault("diagnostics", None)
            # Legacy projects could retain a prompt-only/T2V project profile on
            # an incomplete continuation target. The target has a continuity
            # frame and must render through its verified I2V contract instead.
            normalized_continuation_profiles = False
            scenes_payload = payload.get("scenes", [])
            if isinstance(scenes_payload, list):
                ordered_payload = sorted(
                    (scene for scene in scenes_payload if isinstance(scene, dict)),
                    key=lambda scene: int(scene.get("order", 0)),
                )
                transitions = {
                    "minimax_h3_no_reference": ("minimax_h3_image_to_video", "image_to_video"),
                    "ltx_2_5_text_to_video": ("ltx_2_5_image_to_video", "image_to_video"),
                }
                for index, target in enumerate(ordered_payload):
                    if index == 0 or target.get("mode") != "continue_previous" or target.get("render_versions"):
                        continue
                    source = ordered_payload[index - 1]
                    destination = transitions.get(source.get("workflow_profile_id"))
                    if destination is None:
                        continue
                    if (target.get("workflow_profile_id"), target.get("workflow_mode")) != destination:
                        target["workflow_profile_id"], target["workflow_mode"] = destination
                        normalized_continuation_profiles = True
            project = H3Project.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ProjectStoreError("The local project metadata is invalid or unreadable.") from exc
        if Path(project.project_root).resolve() != path.parent.resolve():
            raise ProjectStoreError("The local project metadata has an invalid project root.")
        interrupted = False
        recovered_runs: list[H3RenderRun] = []
        recovered_scene_ids: set[str] = set()
        for run in project.render_runs:
            active_items = [item for item in run.items if item.state in {"waiting", "preparing", "rendering", "verifying"}]
            # Never infer that a submitted ComfyUI prompt has disappeared just
            # because this UI/backend instance was reopened.  A prompt ID must
            # be correlated with ComfyUI history/queue by the live provider.
            # Conversely, an unowned active item without a prompt ID cannot be
            # adopted into a render version and is safe to mark interrupted.
            recover_pre_submission = (
                run.status == "running"
                and bool(active_items)
                and not self._run_is_active_here(project.id, run.id)
                and all(item.prompt_id is None for item in active_items)
            )
            if not recover_pre_submission:
                recovered_runs.append(run)
                continue
            interrupted = True
            timestamp = _now()
            reason = "The render was interrupted before ComfyUI returned a prompt ID."
            items = [item.model_copy(update={
                "state": "cancelled" if item.state in {"waiting", "preparing", "rendering", "verifying"} else item.state,
                "completed_at": timestamp if item.state in {"waiting", "preparing", "rendering", "verifying"} else item.completed_at,
                "error": reason if item.state in {"waiting", "preparing", "rendering", "verifying"} else item.error,
            }) for item in run.items]
            recovered_scene_ids.update(item.scene_id for item in active_items)
            recovered_runs.append(run.model_copy(update={
                "status": "cancelled",
                "completed_at": timestamp,
                "current_scene_id": None,
                "stop_after_current_requested": True,
                "failure_or_cancel_reason": reason,
                "items": items,
            }))
        if interrupted:
            project = project.model_copy(update={"render_runs": recovered_runs})
        timing_hydrated = False
        hydrated_scenes: list[H3Scene] = []
        for scene in project.scenes:
            versions = [self._hydrate_render_timing(version) for version in scene.render_versions]
            timing_hydrated = timing_hydrated or any(before != after for before, after in zip(scene.render_versions, versions, strict=True))
            hydrated_scenes.append(scene.model_copy(update={"render_versions": versions}))
        if interrupted:
            hydrated_scenes = [
                scene.model_copy(update={
                    "status": "cancelled",
                    "active_prompt_id": None,
                    "last_error": None,
                    "current_phase": "Interrupted",
                    "progress_value": None,
                    "progress_max": None,
                    "diagnostics": None,
                }) if scene.id in recovered_scene_ids and scene.status in {"queued", "preparing", "submitted", "rendering", "encoding", "verifying"} else scene
                for scene in hydrated_scenes
            ]
        if timing_hydrated or interrupted:
            project = project.model_copy(update={"scenes": hydrated_scenes})
        if migrated or normalized_continuation_profiles or interrupted or timing_hydrated:
            _atomic_json_write(path, project.model_dump(mode="json"))
        return project
