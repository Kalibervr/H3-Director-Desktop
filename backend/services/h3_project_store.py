"""Atomic, app-owned persistence for H3 Director projects and scene versions."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from api_types import (
    H3Project,
    H3ProjectSettings,
    H3RenderVersion,
    H3Scene,
    H3SceneUpdateRequest,
)


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
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProjectStoreError("The local project could not be saved safely.") from exc


class H3ProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()

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

    def create_project(self, name: str, scene_count: int = 1) -> H3Project:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ProjectStoreError("A project name is required.")
        project_id = uuid.uuid4().hex
        root = self.projects_root / f"{_safe_slug(cleaned_name)}_{project_id[:8]}"
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
        scenes = [self._new_scene(number, _scene_storage_name(number)) for number in range(1, scene_count + 1)]
        project = H3Project(
            schema_version=2,
            id=project_id,
            name=cleaned_name,
            created_at=timestamp,
            updated_at=timestamp,
            project_root=str(root),
            settings=H3ProjectSettings(width=640, height=640, fps=24, duration_seconds=5.0, frame_count=124),
            scenes=scenes,
            selected_scene_id=scenes[0].id,
        )
        self.save_project(project)
        return project

    def get_project(self, project_id: str) -> H3Project:
        for project in self.list_projects():
            if project.id == project_id:
                return project
        raise ProjectStoreError("The local project could not be found.")

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

    def update_scene(self, project_id: str, scene_id: str, update: H3SceneUpdateRequest) -> H3Project:
        project = self.get_project(project_id)
        scenes: list[H3Scene] = []
        found = False
        changes = update.model_dump(exclude_none=True)
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
        current_ids = [scene.id for scene in project.scenes]
        if len(scene_ids) != len(set(scene_ids)) or set(scene_ids) != set(current_ids):
            raise ProjectStoreError("The scene order must contain every scene exactly once.")
        by_id = {scene.id: scene for scene in project.scenes}
        scenes = [by_id[scene_id].model_copy(update={"order": index}) for index, scene_id in enumerate(scene_ids, 1)]
        return self.save_project(project.model_copy(update={"scenes": scenes}))

    def delete_scene(self, project_id: str, scene_id: str) -> H3Project:
        project = self.get_project(project_id)
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
    ) -> H3Project:
        project = self.get_project(project_id)
        scenes = [
            scene.model_copy(update={
                "status": status,
                "active_prompt_id": prompt_id if prompt_id is not None else scene.active_prompt_id,
                "last_error": error,
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
            }))
        if not found:
            raise ProjectStoreError("The selected scene could not be found.")
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

    @staticmethod
    def _new_scene(order: int, storage_name: str, source: H3Scene | None = None) -> H3Scene:
        return H3Scene(
            id=uuid.uuid4().hex,
            storage_name=storage_name,
            order=order,
            name=f"{source.name} Copy" if source else f"Scene {order:02d}",
            prompt=source.prompt if source else "",
            reference_image=source.reference_image if source else None,
            width=source.width if source else 640,
            height=source.height if source else 640,
            fps=source.fps if source else 24,
            duration_seconds=source.duration_seconds if source else 5.0,
            frame_count=source.frame_count if source else 124,
            seed=source.seed if source else 193554738272393,
            status="idle",
            selected_render_version_id=None,
            render_versions=[],
            last_error=None,
            active_prompt_id=None,
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

    @staticmethod
    def _read_file(path: Path) -> H3Project:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            migrated = payload.get("schema_version") == 1
            if migrated:
                payload["schema_version"] = 2
                for index, scene in enumerate(payload.get("scenes", []), 1):
                    scene["storage_name"] = _scene_storage_name(int(scene.get("order", index)))
            project = H3Project.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ProjectStoreError("The local project metadata is invalid or unreadable.") from exc
        if Path(project.project_root).resolve() != path.parent.resolve():
            raise ProjectStoreError("The local project metadata has an invalid project root.")
        if migrated:
            _atomic_json_write(path, project.model_dump(mode="json"))
        return project
