"""Focused ordered queue, persistence, dependency-stop, and cancellation tests."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from api_types import H3ProjectRenderRequest, H3RenderRun, H3RenderVersion, H3SequenceItem, MiniMaxH3VideoProbeResponse
from services.h3_project_store import H3ProjectStore, ProjectStoreError
from services.h3_sequence import H3SequenceCoordinator
from services.comfyui_minimax_h3_provider import RenderCancelled


def _version(project_root: Path, storage_name: str, number: int, prompt_id: str) -> H3RenderVersion:
    root = project_root / "scenes" / storage_name / "renders" / f"v{number:03d}"
    root.mkdir(parents=True, exist_ok=False)
    video = root / "video.mp4"
    metadata = root / "metadata.json"
    video.write_bytes(prompt_id.encode())
    metadata.write_text("{}\n", encoding="utf-8")
    return H3RenderVersion(
        id=f"v{number:03d}", number=number, created_at="2026-08-10T00:00:00+00:00",
        root=str(root), video_file=str(video), metadata_file=str(metadata), prompt="prompt",
        input_image_reference="reference.png", seed=1, width=640, height=640, fps=24,
        duration_seconds=5.0, frame_count=124, prompt_id=prompt_id,
        input_image_sha256="a" * 64, workflow_sha256="b" * 64, output_sha256="c" * 64,
        ffprobe=MiniMaxH3VideoProbeResponse(codec="h264", width=640, height=640, fps="24/1", duration_seconds=5.167, frame_count=124, audio_present=True),
    )


def _wait(store: H3ProjectStore, project_id: str, run_id: str) -> object:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        project = store.get_project(project_id)
        run = next(item for item in project.render_runs if item.id == run_id)
        if run.status != "running":
            return run
        time.sleep(0.01)
    raise AssertionError("render run did not finish")


def test_render_from_here_uses_current_order_and_creates_new_versions(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Ordered", 5)
    order: list[str] = []

    def render(project_id, scene_id, request, report, cancel_requested):
        assert not cancel_requested()
        del request
        order.append(scene_id)
        report("Preparing", None, None, None)
        report("Sampling", 10, 20, None)
        report("Verifying", None, None, None)
        current = store.get_project(project_id)
        scene = next(item for item in current.scenes if item.id == scene_id)
        number = len(scene.render_versions) + 1
        store.add_render_version(project_id, scene_id, _version(Path(current.project_root), scene.storage_name, number, f"prompt-{scene.order}-{number}"))

    coordinator = H3SequenceCoordinator(store, render)
    expected = [scene.id for scene in project.scenes[2:]]
    run = coordinator.start(project.id, H3ProjectRenderRequest(), kind="from_here", start_scene_id=expected[0])
    completed = _wait(store, project.id, run.id)
    assert completed.status == "complete"
    assert completed.ordered_scene_ids == expected
    assert order == expected
    assert [item.render_version_id for item in completed.items] == ["v001"] * 3
    assert [item.prompt_id for item in completed.items] == ["prompt-3-1", "prompt-4-1", "prompt-5-1"]


def test_blocking_error_stops_and_skips_later_scenes(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Blocked", 3)

    def render(project_id, scene_id, request, report, cancel_requested):
        assert not cancel_requested()
        del project_id, request, report
        if scene_id == project.scenes[1].id:
            raise ProjectStoreError("Previous scene has no selected completed render.")
        scene = project.scenes[0]
        store.add_render_version(project.id, scene.id, _version(Path(project.project_root), scene.storage_name, 1, "prompt-one"))

    coordinator = H3SequenceCoordinator(store, render)
    run = coordinator.start(project.id, H3ProjectRenderRequest(), kind="all", start_scene_id=None)
    failed = _wait(store, project.id, run.id)
    assert [item.state for item in failed.items] == ["complete", "failed", "skipped"]
    assert failed.failure_or_cancel_reason == "Previous scene has no selected completed render."


def test_unexpected_errors_are_sanitized(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Sanitized")

    def render(project_id, scene_id, request, report, cancel_requested):
        assert not cancel_requested()
        del project_id, scene_id, request, report
        raise RuntimeError("C:\\Users\\private\\workflow.json secret-token")

    coordinator = H3SequenceCoordinator(store, render)
    run = coordinator.start(project.id, H3ProjectRenderRequest(), kind="all", start_scene_id=None)
    failed = _wait(store, project.id, run.id)
    assert failed.failure_or_cancel_reason == "The scene render failed safely."
    assert "private" not in (failed.items[0].error or "")


def test_stop_is_after_current_and_remaining_items_are_cancelled(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Stop", 3)
    entered = threading.Event()
    release = threading.Event()

    def render(project_id, scene_id, request, report, cancel_requested):
        assert not cancel_requested()
        del request
        entered.set()
        release.wait(2)
        current = store.get_project(project_id)
        scene = next(item for item in current.scenes if item.id == scene_id)
        store.add_render_version(project_id, scene_id, _version(Path(current.project_root), scene.storage_name, 1, "prompt-current"))
        report("Verifying", None, None, None)

    coordinator = H3SequenceCoordinator(store, render)
    run = coordinator.start(project.id, H3ProjectRenderRequest(), kind="all", start_scene_id=None)
    assert entered.wait(1)
    coordinator.request_stop(project.id, run.id)
    release.set()
    cancelled = _wait(store, project.id, run.id)
    assert [item.state for item in cancelled.items] == ["complete", "cancelled", "cancelled"]
    assert cancelled.stop_after_current_requested is True


def test_single_scene_stop_interrupts_current_render_without_version(tmp_path: Path) -> None:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Interrupt")
    entered = threading.Event()

    def render(project_id, scene_id, request, report, cancel_requested):
        del project_id, scene_id, request, report
        entered.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if cancel_requested():
                raise RenderCancelled("The render was cancelled by the user.")
            time.sleep(0.01)
        raise AssertionError("render cancellation was not requested")

    coordinator = H3SequenceCoordinator(store, render)
    run = coordinator.start(project.id, H3ProjectRenderRequest(), kind="scene", start_scene_id=project.scenes[0].id)
    assert entered.wait(1)
    coordinator.request_stop(project.id, run.id)
    cancelled = _wait(store, project.id, run.id)
    refreshed = store.get_project(project.id).scenes[0]
    assert cancelled.status == "cancelled"
    assert cancelled.items[0].state == "cancelled"
    assert refreshed.status == "cancelled"
    assert refreshed.render_versions == []


def test_active_queue_blocks_reorder_and_restart_marks_it_cancelled(tmp_path: Path) -> None:
    root = tmp_path / "Projects"
    store = H3ProjectStore(root)
    project = store.create_project("Recovery", 2)
    run = H3RenderRun(
        id="run-restart", kind="all", status="running", started_at="2026-08-10T00:00:00+00:00",
        ordered_scene_ids=[scene.id for scene in project.scenes], current_scene_id=project.scenes[0].id,
        items=[H3SequenceItem(scene_id=scene.id, scene_order=scene.order, state="rendering" if scene.order == 1 else "waiting") for scene in project.scenes],
    )
    store.add_render_run(project.id, run)
    with pytest.raises(ProjectStoreError, match="order cannot change"):
        store.reorder_scenes(project.id, list(reversed(run.ordered_scene_ids)))
    reopened = H3ProjectStore(root).get_project(project.id)
    recovered = next(item for item in reopened.render_runs if item.id == run.id)
    assert recovered.status == "cancelled"
    assert "not resumed" in (recovered.failure_or_cancel_reason or "")
