"""Focused regression coverage for confirmed-outcome next-scene suggestions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_types import H3NextScenePromptRequest, H3RenderVersion, H3SceneUpdateRequest, MiniMaxH3VideoProbeResponse
from handlers.comfyui_minimax_h3_handler import ComfyUIMiniMaxH3Handler
from _routes._errors import HTTPError
from services.h3_ollama_prompt_assistant import OllamaSuggestion, OllamaPromptAssistant
from services.h3_project_store import H3ProjectStore


def _version(tmp_path: Path) -> H3RenderVersion:
    video = tmp_path / "source.mp4"
    return H3RenderVersion(
        id="v001", number=1, created_at="2026-08-14T00:00:00+00:00", root=str(tmp_path),
        video_file=str(video), metadata_file=str(tmp_path / "metadata.json"), prompt="Rainy street walk.",
        input_image_reference="none", seed=1, width=640, height=640, fps=24, duration_seconds=5,
        frame_count=124, prompt_id="prompt", input_image_sha256="a" * 64, workflow_sha256="b" * 64,
        output_sha256="c" * 64, ffprobe=MiniMaxH3VideoProbeResponse(codec="h264", width=640, height=640,
        fps="24/1", duration_seconds=5.167, frame_count=124, audio_present=True),
    )


def _request(direction: str = "") -> H3NextScenePromptRequest:
    return H3NextScenePromptRequest(endpoint="http://127.0.0.1:11434", model="qwen3:4b", current_user_instruction=direction, request_id="suggest-request")


def _handler(tmp_path: Path) -> tuple[ComfyUIMiniMaxH3Handler, str, str]:
    store = H3ProjectStore(tmp_path / "Projects")
    project = store.create_project("Continuity", 2, sequence_mode="continuous_sequence")
    source, target = project.scenes
    project = store.add_render_version(project.id, source.id, _version(tmp_path))
    project = store.update_scene(project.id, source.id, H3SceneUpdateRequest(confirmed_outcome="The lone figure reaches the apartment entrance and stands at the doorway."))
    return ComfyUIMiniMaxH3Handler(project_store=store), project.id, target.id


def _result(text: str) -> OllamaSuggestion:
    return OllamaSuggestion(suggestion=text, vision_context="not_used", raw_response={}, elapsed_seconds=1.0, response_metadata={})


def test_confirmed_outcome_outranks_historical_prompt_and_is_structured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    handler, project_id, scene_id = _handler(tmp_path)
    observed: list[str] = []
    monkeypatch.setattr(OllamaPromptAssistant, "suggest_next_scene", lambda _self, request: observed.append(request.raw_prompt) or _result(
        "1. The figure enters through the apartment entrance.\n2. The figure checks the doorway before entering.\n3. The figure opens the entrance door and steps inside."
    ))
    response = handler.suggest_next_scene(project_id, scene_id, _request())
    assert response.provider == "ollama"
    assert response.mode == "original_ideas"
    assert "CURRENT CONFIRMED OUTCOME (primary anchor):\nThe lone figure reaches the apartment entrance" in observed[0]
    assert "CURRENT LOCATION (primary anchor):\napartment entrance / doorway" in observed[0]
    assert "HISTORICAL CONTEXT (secondary; do not replay):\nRainy street walk." in observed[0]
    assert "OPTIONAL USER DIRECTION (highest priority when present):\n(none" in observed[0]
    assert all("entrance" in item.lower() or "door" in item.lower() for item in response.options)


def test_passive_or_ungrounded_suggestions_fail_without_generic_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    handler, project_id, scene_id = _handler(tmp_path)
    monkeypatch.setattr(OllamaPromptAssistant, "suggest_next_scene", lambda *_args: _result(
        "1. Figure pauses to observe rain reflections.\n2. Figure steps into a puddle.\n3. Figure's shadow merges with pavement."
    ))
    with pytest.raises(HTTPError, match="not grounded") as exc:
        handler.suggest_next_scene(project_id, scene_id, _request())
    diagnostics = exc.value.response.details["suggestion_diagnostics"]
    assert diagnostics["rejected_options"] == ["Figure pauses to observe rain reflections.", "Figure steps into a puddle.", "Figure's shadow merges with pavement."]
    assert "historical location is replayed" in "; ".join(diagnostics["rejection_reasons"])
    assert diagnostics["confirmed_outcome"].startswith("The lone figure reaches")
    memory = handler._project_store.get_project(project_id).continuity_memory.entries
    assert len(memory) == 1
    assert memory[0].current_state == "Rainy street walk."


def test_user_direction_returns_variations_that_preserve_its_core_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    handler, project_id, scene_id = _handler(tmp_path)
    observed: list[str] = []
    monkeypatch.setattr(OllamaPromptAssistant, "suggest_next_scene", lambda _self, request: observed.append(request.raw_prompt) or _result(
        "1. Close detail: the figure enters the door code, the lock clicks, and the door opens.\n"
        "2. Over the shoulder: the figure keys in the code and unlocks the entrance door.\n"
        "3. Medium close shot: the figure enters the keypad code, opens the door, and steps through."
    ))
    response = handler.suggest_next_scene(project_id, scene_id, _request("closer angle, enters the door code and opens the door"))
    assert response.mode == "user_directed_variations"
    assert "SUGGESTION MODE: user_directed_variations" in observed[0]
    assert "closer angle, enters the door code and opens the door" in observed[0]
    assert all(any(token in option.lower() for token in ("code", "keypad", "lock")) for option in response.options)
    assert all(any(token in option.lower() for token in ("open", "unlock")) for option in response.options)


def test_confirmed_outcome_persists_and_old_projects_default_empty(tmp_path: Path) -> None:
    handler, project_id, _ = _handler(tmp_path)
    reopened = handler._project_store.get_project(project_id)
    assert reopened.scenes[0].confirmed_outcome.startswith("The lone figure reaches")
    assert reopened.scenes[0].confirmed_outcome_render_version_id == "v001"
    project_file = Path(reopened.project_root) / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["schema_version"] = 17
    payload["scenes"][0].pop("confirmed_outcome_render_version_id")
    project_file.write_text(json.dumps(payload), encoding="utf-8")
    migrated = handler._project_store.get_project(project_id)
    assert migrated.schema_version == 18
    assert migrated.scenes[0].confirmed_outcome_render_version_id == "v001"


def test_confirmed_outcome_is_not_reused_for_a_different_selected_version(tmp_path: Path) -> None:
    handler, project_id, scene_id = _handler(tmp_path)
    project = handler._project_store.get_project(project_id)
    source = project.scenes[0]
    second = _version(tmp_path / "second")
    second = second.model_copy(update={"id": "v002", "number": 2, "prompt": "A different take ends in a lobby."})
    project = handler._project_store.add_render_version(project_id, source.id, second)
    project = handler._project_store.update_scene(project_id, source.id, H3SceneUpdateRequest(selected_render_version_id="v002"))
    target, selected_source, version = handler._next_scene_source(project, scene_id)
    state, historical = handler._confirmed_continuity_context(project, selected_source, version)
    assert target.id == scene_id
    assert state == "A different take ends in a lobby."
    assert historical == "A different take ends in a lobby."
