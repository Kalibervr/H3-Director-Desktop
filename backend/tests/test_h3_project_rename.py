"""Focused regression coverage for project display-name changes."""

from pathlib import Path

import pytest

from services.h3_project_store import H3ProjectStore, ProjectStoreError


def test_rename_persists_without_changing_project_identity_or_scenes(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Original project", scene_count=2)
    original_id = project.id
    original_root = project.project_root
    original_scene_ids = [scene.id for scene in project.scenes]

    renamed = store.rename_project(project.id, "  Renamed project  ")
    reopened = H3ProjectStore(tmp_path / "Projects").get_project(project.id)

    assert renamed.name == "Renamed project"
    assert reopened.name == "Renamed project"
    assert reopened.id == original_id
    assert reopened.project_root == original_root
    assert [scene.id for scene in reopened.scenes] == original_scene_ids


@pytest.mark.parametrize("name", ["", "   "])
def test_rename_rejects_blank_display_names(tmp_path: Path, name: str) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Original project")

    with pytest.raises(ProjectStoreError, match="A project name is required"):
        store.rename_project(project.id, name)
