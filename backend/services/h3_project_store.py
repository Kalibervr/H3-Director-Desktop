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

    def create_project(self, name: str) -> H3Project:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ProjectStoreError("A project name is required.")
        project_id = uuid.uuid4().hex
        root = self.projects_root / f"{_safe_slug(cleaned_name)}_{project_id[:8]}"
        try:
            root.mkdir(parents=True, exist_ok=False)
            (root / "assets" / "references").mkdir(parents=True)
            (root / "scenes" / "scene_001" / "inputs").mkdir(parents=True)
            (root / "scenes" / "scene_001" / "renders").mkdir(parents=True)
        except OSError as exc:
            raise ProjectStoreError("The local project folder could not be created.") from exc
        timestamp = _now()
        scene_id = uuid.uuid4().hex
        scene = H3Scene(
            id=scene_id,
            order=1,
            name="Scene 01",
            prompt="",
            reference_image=None,
            width=640,
            height=640,
            fps=24,
            duration_seconds=5.0,
            frame_count=124,
            seed=193554738272393,
            status="idle",
            selected_render_version_id=None,
            render_versions=[],
            last_error=None,
            active_prompt_id=None,
        )
        project = H3Project(
            schema_version=1,
            id=project_id,
            name=cleaned_name,
            created_at=timestamp,
            updated_at=timestamp,
            project_root=str(root),
            settings=H3ProjectSettings(width=640, height=640, fps=24, duration_seconds=5.0, frame_count=124),
            scenes=[scene],
            selected_scene_id=scene_id,
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
            scenes.append(scene.model_copy(update=changes))
        if not found:
            raise ProjectStoreError("The selected scene could not be found.")
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

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
        for scene in project.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            if any(item.id == version.id for item in scene.render_versions):
                raise ProjectStoreError("The immutable render version already exists.")
            scenes.append(scene.model_copy(update={
                "render_versions": [*scene.render_versions, version],
                "selected_render_version_id": version.id,
                "status": "complete",
                "active_prompt_id": version.prompt_id,
                "last_error": None,
            }))
        return self.save_project(project.model_copy(update={"scenes": scenes, "selected_scene_id": scene_id}))

    @staticmethod
    def _read_file(path: Path) -> H3Project:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            project = H3Project.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ProjectStoreError("The local project metadata is invalid or unreadable.") from exc
        if Path(project.project_root).resolve() != path.parent.resolve():
            raise ProjectStoreError("The local project metadata has an invalid project root.")
        return project
