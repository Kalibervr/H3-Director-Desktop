"""Focused persistence and immutable version tests for H3 projects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_types import H3RenderVersion, H3SceneUpdateRequest, MiniMaxH3VideoProbeResponse
from services.h3_project_store import H3ProjectStore, ProjectStoreError


def _version(root: Path, number: int) -> H3RenderVersion:
    directory = root / f"v{number:03d}"
    directory.mkdir(parents=True)
    video = directory / "video.mp4"
    metadata = directory / "metadata.json"
    video.write_bytes(f"video-{number}".encode())
    metadata.write_text("{}\n", encoding="utf-8")
    return H3RenderVersion(
        id=f"v{number:03d}",
        number=number,
        created_at="2026-08-10T00:00:00+00:00",
        root=str(directory),
        video_file=str(video),
        metadata_file=str(metadata),
        prompt="A persisted scene",
        input_image_reference="C:\\reference.jpg",
        seed=42,
        width=640,
        height=640,
        fps=24,
        duration_seconds=5.0,
        frame_count=124,
        prompt_id=f"prompt-{number}",
        input_image_sha256="a" * 64,
        workflow_sha256="b" * 64,
        output_sha256="c" * 64,
        ffprobe=MiniMaxH3VideoProbeResponse(
            codec="h264", width=640, height=640, fps="24/1",
            duration_seconds=5.167, frame_count=124, audio_present=True,
        ),
    )


def test_project_survives_store_restart_and_autosaved_scene_settings(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("My Film: Opening")
    scene = project.scenes[0]
    assert Path(project.project_root).name.startswith("my-film-opening_")
    assert (Path(project.project_root) / "project.json").is_file()

    renamed = store.rename_project(project.id, "Renamed Film")
    saved = store.update_scene(renamed.id, scene.id, H3SceneUpdateRequest(
        prompt="A real saved prompt",
        reference_image="C:\\local\\reference.jpg",
        seed=123,
        selected_render_version_id=None,
    ))
    reopened = H3ProjectStore(tmp_path / "Projects").get_project(saved.id)
    assert reopened.name == "Renamed Film"
    assert reopened.selected_scene_id == scene.id
    assert reopened.scenes[0].prompt == "A real saved prompt"
    assert reopened.scenes[0].reference_image == "C:\\local\\reference.jpg"
    assert reopened.scenes[0].seed == 123
    assert reopened.schema_version == 2
    assert reopened.scenes[0].storage_name == "scene_001"


def test_five_scene_project_operations_preserve_independent_data_and_storage(tmp_path: Path) -> None:
    root = tmp_path / "Projects"
    store = H3ProjectStore(root)
    project = store.create_project("Five Scenes", 5)
    assert [scene.order for scene in project.scenes] == [1, 2, 3, 4, 5]
    assert [scene.storage_name for scene in project.scenes] == [f"scene_{number:03d}" for number in range(1, 6)]

    first, second = project.scenes[:2]
    project = store.update_scene(project.id, first.id, H3SceneUpdateRequest(prompt="First", seed=101))
    project = store.update_scene(project.id, second.id, H3SceneUpdateRequest(prompt="Second", seed=202))
    render_root = Path(project.project_root) / "scenes"
    project = store.add_render_version(project.id, first.id, _version(render_root / first.storage_name / "renders", 1))
    project = store.add_render_version(project.id, second.id, _version(render_root / second.storage_name / "renders", 1))

    project = store.duplicate_scene(project.id, second.id)
    duplicate = project.scenes[-1]
    assert duplicate.prompt == "Second"
    assert duplicate.seed == 202
    assert duplicate.render_versions == []
    assert duplicate.selected_render_version_id is None
    assert duplicate.storage_name == "scene_006"

    ids = [duplicate.id, first.id, *[scene.id for scene in project.scenes if scene.id not in {duplicate.id, first.id}]]
    project = store.reorder_scenes(project.id, ids)
    assert project.scenes[0].id == duplicate.id
    assert project.scenes[1].storage_name == "scene_001"
    deleted = project.scenes[-1]
    project = store.delete_scene(project.id, deleted.id)

    reopened = H3ProjectStore(root).get_project(project.id)
    assert len(reopened.scenes) == 5
    assert [scene.id for scene in reopened.scenes] == [scene.id for scene in project.scenes]
    assert reopened.selected_scene_id == duplicate.id
    assert next(scene for scene in reopened.scenes if scene.id == first.id).render_versions[0].id == "v001"
    assert next(scene for scene in reopened.scenes if scene.id == second.id).render_versions[0].id == "v001"
    assert any((Path(reopened.project_root) / "scenes" / "archive").iterdir())


def test_schema_one_project_migrates_atomically_without_data_loss(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Migration")
    metadata = Path(project.project_root) / "project.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload["scenes"][0].pop("storage_name")
    metadata.write_text(json.dumps(payload), encoding="utf-8")

    reopened = H3ProjectStore(tmp_path / "Projects").get_project(project.id)
    migrated = json.loads(metadata.read_text(encoding="utf-8"))
    assert reopened.schema_version == 2
    assert reopened.scenes[0].id == project.scenes[0].id
    assert reopened.scenes[0].storage_name == "scene_001"
    assert migrated["schema_version"] == 2
    assert list(Path(project.project_root).glob(".project.json.*.tmp")) == []


def test_render_versions_are_appended_and_selected_without_overwrite(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Versions")
    scene = project.scenes[0]
    render_root = Path(project.project_root) / "scenes" / "scene_001" / "renders"
    first = store.add_render_version(project.id, scene.id, _version(render_root, 1))
    second = store.add_render_version(project.id, scene.id, _version(render_root, 2))
    assert [item.id for item in second.scenes[0].render_versions] == ["v001", "v002"]
    assert second.scenes[0].selected_render_version_id == "v002"
    with pytest.raises(ProjectStoreError, match="already exists"):
        store.add_render_version(project.id, scene.id, first.scenes[0].render_versions[0])
    assert (render_root / "v001" / "video.mp4").read_bytes() == b"video-1"


def test_project_writes_leave_no_temporary_files_and_reject_outside_reopen(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Atomic")
    store.rename_project(project.id, "Atomic Save")
    root = Path(project.project_root)
    assert list(root.glob(".project.json.*.tmp")) == []
    payload = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert payload["name"] == "Atomic Save"
    with pytest.raises(ProjectStoreError, match="app-owned"):
        store.reopen_project(tmp_path / "outside")
