"""Focused tests for verified, immutable manual scene continuity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_types import H3RenderVersion, H3SceneUpdateRequest, MiniMaxH3VideoProbeResponse
from services.h3_continuity import ContinuityError, H3ContinuityExtractor, previous_scene
from services.h3_project_store import H3ProjectStore

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_ROOT = REPO_ROOT / "backend" / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries"
FFMPEG = BIN_ROOT / "ffmpeg.exe"
FFPROBE = BIN_ROOT / "ffprobe.exe"
EVIDENCE_VIDEO = REPO_ROOT / "test-assets" / "minimax-h3" / "single_scene_verified_output.mp4"


def _source_version(video: Path) -> H3RenderVersion:
    return H3RenderVersion(
        id="v001", number=1, created_at="2026-08-10T00:00:00+00:00",
        root=str(video.parent), video_file=str(video), metadata_file=str(video.with_suffix(".json")),
        prompt="Source", input_image_reference="reference.jpg", seed=1, width=640, height=640,
        fps=24, duration_seconds=5.0, frame_count=124, prompt_id="source-prompt",
        input_image_sha256="a" * 64, workflow_sha256="b" * 64, output_sha256="c" * 64,
        ffprobe=MiniMaxH3VideoProbeResponse(
            codec="h264", width=640, height=640, fps="24/1",
            duration_seconds=5.167, frame_count=124, audio_present=True,
        ),
    )


def _continuity_project(tmp_path: Path):
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Continuity", 3)
    first, second, _ = project.scenes
    project = store.add_render_version(project.id, first.id, _source_version(EVIDENCE_VIDEO))
    project = store.update_scene(project.id, second.id, H3SceneUpdateRequest(mode="continue_previous"))
    return store, project, first, project.scenes[1]


def test_previous_scene_uses_current_storyboard_order(tmp_path: Path) -> None:
    store, project, first, second = _continuity_project(tmp_path)
    assert previous_scene(project, second.id).id == first.id
    third = project.scenes[2]
    reordered = store.reorder_scenes(project.id, [second.id, third.id, first.id])
    assert previous_scene(reordered, first.id).id == third.id
    with pytest.raises(ContinuityError, match="scene before"):
        previous_scene(reordered, second.id)


def test_missing_previous_selected_render_blocks_without_reference_fallback(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Blocked", 2)
    second = project.scenes[1]
    project = store.update_scene(project.id, second.id, H3SceneUpdateRequest(
        mode="continue_previous", reference_image="C:\\private\\fallback.jpg",
    ))
    with pytest.raises(ContinuityError, match="selected completed render") as error:
        H3ContinuityExtractor(FFMPEG, FFPROBE).extract(project, project.scenes[1])
    assert "private" not in str(error.value)


@pytest.mark.skipif(not FFMPEG.is_file() or not FFPROBE.is_file(), reason="bundled media tools unavailable")
def test_extracts_immutable_last_frame_and_offset_with_persisted_metadata(tmp_path: Path) -> None:
    store, project, _, second = _continuity_project(tmp_path)
    extractor = H3ContinuityExtractor(FFMPEG, FFPROBE)
    last = extractor.extract(project, second)
    project = store.add_continuity_artifact(project.id, second.id, last)
    assert last.id == "c001"
    assert last.frame_index == 123
    assert last.timestamp_seconds == pytest.approx(5.125)
    assert Path(last.image_file).is_file()
    assert json.loads(Path(last.metadata_file).read_text(encoding="utf-8"))["source_scene_id"] == project.scenes[0].id

    project = store.update_scene(project.id, second.id, H3SceneUpdateRequest(
        continuity_strategy="offset_from_end", continuity_offset_frames=7,
    ))
    offset = extractor.extract(project, project.scenes[1])
    project = store.add_continuity_artifact(project.id, second.id, offset)
    assert offset.id == "c002"
    assert offset.frame_index == 116
    assert offset.offset_from_end_frames == 7
    assert Path(last.image_file).is_file()
    assert Path(offset.image_file).is_file()
    assert Path(last.image_file).read_bytes() != Path(offset.image_file).read_bytes()

    reopened = H3ProjectStore(tmp_path / "Projects").get_project(project.id)
    saved = reopened.scenes[1]
    assert saved.mode == "continue_previous"
    assert saved.continuity_strategy == "offset_from_end"
    assert saved.selected_continuity_artifact_id == "c002"
    assert [item.id for item in saved.continuity_artifacts] == ["c001", "c002"]
