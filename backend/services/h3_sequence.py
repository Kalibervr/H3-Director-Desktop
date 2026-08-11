"""Ordered, manual multi-scene sequencing over the verified single-scene renderer."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from _routes._errors import HTTPError
from api_types import H3ProjectRenderRequest, H3RenderRun, H3SequenceItem
from services.h3_project_store import H3ProjectStore, ProjectStoreError
from services.comfyui_minimax_h3_provider import RenderCancelled


def _now() -> str:
    return datetime.now(UTC).isoformat()


RenderScene = Callable[[str, str, H3ProjectRenderRequest, Callable[[str, int | None, int | None, str | None], None], Callable[[], bool]], object]


class H3SequenceCoordinator:
    """Runs one project queue at a time and persists every truthful phase transition."""

    def __init__(self, store: H3ProjectStore, render_scene: RenderScene) -> None:
        self._store = store
        self._render_scene = render_scene
        self._lock = threading.RLock()
        self._stop_requests: set[tuple[str, str]] = set()
        self._cancel_requests: set[tuple[str, str]] = set()
        self._threads: dict[tuple[str, str], threading.Thread] = {}

    def start(
        self,
        project_id: str,
        request: H3ProjectRenderRequest,
        *,
        kind: str,
        start_scene_id: str | None,
    ) -> H3RenderRun:
        project = self._store.get_project(project_id)
        ordered = sorted(project.scenes, key=lambda scene: scene.order)
        if kind == "scene":
            if not start_scene_id:
                raise ProjectStoreError("Render Scene requires a selected scene.")
            ordered = [scene for scene in ordered if scene.id == start_scene_id]
            if not ordered:
                raise ProjectStoreError("The selected scene could not be found.")
        elif kind == "from_here":
            if not start_scene_id:
                raise ProjectStoreError("Render From Here requires a selected scene.")
            start_index = next((index for index, scene in enumerate(ordered) if scene.id == start_scene_id), None)
            if start_index is None:
                raise ProjectStoreError("The selected start scene could not be found.")
            ordered = ordered[start_index:]
        elif kind != "all":
            raise ProjectStoreError("The render queue type is invalid.")
        if not ordered:
            raise ProjectStoreError("The render queue has no active scenes.")

        run_id = uuid.uuid4().hex
        run = H3RenderRun(
            id=run_id,
            kind=kind,
            status="running",
            started_at=_now(),
            ordered_scene_ids=[scene.id for scene in ordered],
            items=[H3SequenceItem(scene_id=scene.id, scene_order=scene.order, state="waiting") for scene in ordered],
        )
        with self._lock:
            self._store.add_render_run(project_id, run)
            thread = threading.Thread(
                target=self._execute,
                args=(project_id, run_id, request),
                name=f"h3-sequence-{run_id[:8]}",
                daemon=True,
            )
            self._threads[(project_id, run_id)] = thread
            thread.start()
        return run

    def request_stop(self, project_id: str, run_id: str) -> H3RenderRun:
        with self._lock:
            run = self._get_run(project_id, run_id)
            if run.status != "running":
                raise ProjectStoreError("The render queue is no longer running.")
            self._stop_requests.add((project_id, run_id))
            if run.kind == "scene":
                self._cancel_requests.add((project_id, run_id))
            updated = run.model_copy(update={"stop_after_current_requested": True})
            self._store.update_render_run(project_id, updated)
            return updated

    def _execute(self, project_id: str, run_id: str, request: H3ProjectRenderRequest) -> None:
        key = (project_id, run_id)
        try:
            run = self._get_run(project_id, run_id)
            for scene_id in run.ordered_scene_ids:
                if key in self._stop_requests:
                    self._cancel_remaining(project_id, run_id, "Stopped after the previous scene completed.")
                    return
                self._set_item(project_id, run_id, scene_id, "preparing", started_at=_now(), current_phase="Preparing")
                try:
                    self._render_scene(
                        project_id,
                        scene_id,
                        request,
                        lambda phase, value, maximum, diagnostics, sid=scene_id: self._phase(
                            project_id, run_id, sid, phase, value, maximum, diagnostics
                        ),
                        lambda: key in self._cancel_requests,
                    )
                    project = self._store.get_project(project_id)
                    scene = next(item for item in project.scenes if item.id == scene_id)
                    version = next(item for item in scene.render_versions if item.id == scene.selected_render_version_id)
                    artifact_id = scene.selected_continuity_artifact_id if scene.mode == "continue_previous" else None
                    self._set_item(
                        project_id, run_id, scene_id, "complete", completed_at=_now(),
                        render_version_id=version.id, prompt_id=version.prompt_id,
                        continuity_artifact_id=artifact_id,
                        current_phase="Complete", progress_value=None, progress_max=None,
                    )
                except RenderCancelled:
                    self._store.set_scene_status(project_id, scene_id, "cancelled", error=None, phase="Cancelled")
                    self._set_item(project_id, run_id, scene_id, "cancelled", completed_at=_now(), error="Cancelled by the user.", current_phase="Cancelled", progress_value=None, progress_max=None)
                    self._cancel_remaining(project_id, run_id, "Cancelled by the user.")
                    return
                except Exception as exc:
                    message = str(exc).strip() if isinstance(exc, (HTTPError, ProjectStoreError)) else "The scene render failed safely."
                    project = self._store.get_project(project_id)
                    failed_scene = next((item for item in project.scenes if item.id == scene_id), None)
                    self._set_item(
                        project_id, run_id, scene_id, "failed", completed_at=_now(), error=message,
                        current_phase="Failed", progress_value=None, progress_max=None,
                        diagnostics=failed_scene.diagnostics if failed_scene else None,
                    )
                    self._fail_remaining(project_id, run_id, message)
                    return
                if key in self._stop_requests:
                    self._cancel_remaining(project_id, run_id, "Stopped after the current scene completed.")
                    return
            self._finish(project_id, run_id, "complete", None)
        finally:
            with self._lock:
                self._stop_requests.discard(key)
                self._cancel_requests.discard(key)
                self._threads.pop(key, None)

    def _phase(
        self, project_id: str, run_id: str, scene_id: str, phase: str,
        value: int | None, maximum: int | None, diagnostics: str | None,
    ) -> None:
        state = {
            "Preparing": "preparing", "Submitted": "rendering",
            "Preparing generation": "rendering", "Sampling": "rendering",
            "Decoding": "rendering", "Encoding": "rendering", "Verifying": "verifying",
        }.get(phase)
        if state:
            self._set_item(
                project_id, run_id, scene_id, state, current_phase=phase,
                progress_value=value, progress_max=maximum, diagnostics=diagnostics,
            )

    def _set_item(self, project_id: str, run_id: str, scene_id: str, state: str, **changes: object) -> None:
        with self._lock:
            run = self._get_run(project_id, run_id)
            items = [item.model_copy(update={"state": state, **changes}) if item.scene_id == scene_id else item for item in run.items]
            self._store.update_render_run(project_id, run.model_copy(update={"items": items, "current_scene_id": scene_id}))

    def _fail_remaining(self, project_id: str, run_id: str, reason: str) -> None:
        timestamp = _now()
        run = self._get_run(project_id, run_id)
        items = [item.model_copy(update={
            "state": "skipped", "completed_at": timestamp,
            "error": "Skipped after a blocking scene error.",
        }) if item.state == "waiting" else item for item in run.items]
        self._store.update_render_run(project_id, run.model_copy(update={
            "status": "failed", "completed_at": timestamp, "current_scene_id": None,
            "failure_or_cancel_reason": reason, "items": items,
        }))

    def _cancel_remaining(self, project_id: str, run_id: str, reason: str) -> None:
        timestamp = _now()
        run = self._get_run(project_id, run_id)
        items = [item.model_copy(update={
            "state": "cancelled", "completed_at": timestamp, "error": reason,
        }) if item.state == "waiting" else item for item in run.items]
        for item in run.items:
            if item.state == "waiting":
                self._store.set_scene_status(project_id, item.scene_id, "cancelled", error=None, phase="Cancelled")
        self._store.update_render_run(project_id, run.model_copy(update={
            "status": "cancelled", "completed_at": timestamp, "current_scene_id": None,
            "stop_after_current_requested": True, "failure_or_cancel_reason": reason, "items": items,
        }))

    def _finish(self, project_id: str, run_id: str, status: str, reason: str | None) -> None:
        run = self._get_run(project_id, run_id)
        self._store.update_render_run(project_id, run.model_copy(update={
            "status": status, "completed_at": _now(), "current_scene_id": None,
            "failure_or_cancel_reason": reason,
        }))

    def _get_run(self, project_id: str, run_id: str) -> H3RenderRun:
        project = self._store.get_project(project_id)
        run = next((item for item in project.render_runs if item.id == run_id), None)
        if run is None:
            raise ProjectStoreError("The render queue could not be found.")
        return run
