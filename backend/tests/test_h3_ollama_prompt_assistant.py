from unittest.mock import Mock, patch

import requests

from api_types import H3PromptAssistantRequest
from services.h3_ollama_prompt_assistant import OllamaPromptAssistant, OllamaPromptAssistantError


def request(**changes: object) -> H3PromptAssistantRequest:
    values: dict[str, object] = {
        "model": "local-model", "raw_prompt": "A cyclist turns left.", "scene_number": 2,
        "scene_name": "Turn", "scene_mode": "continue_previous", "duration_seconds": 5,
        "aspect_ratio": "1:1 (Square)", "width": 640, "height": 640, "fps": 24,
        "project_name": "Local", "sequence_mode": "continuous_sequence", "previous_scene_number": 1,
        "previous_scene_name": "Arrival", "previous_scene_prompt": "A cyclist arrives.",
        "continuity_source_version_id": "v001", "audio_mode": "silent", "no_speech": True, "no_music": True,
    }
    values.update(changes)
    return H3PromptAssistantRequest(**values)


def response(payload: dict) -> Mock:
    result = Mock(); result.json.return_value = payload; result.raise_for_status.return_value = None
    return result


@patch("services.h3_ollama_prompt_assistant.requests.post")
@patch("services.h3_ollama_prompt_assistant.requests.get")
def test_status_enumerates_selected_local_model_and_vision(get: Mock, post: Mock) -> None:
    get.return_value = response({"models": [{"name": "local-model"}]})
    post.return_value = response({"capabilities": ["completion", "vision"]})
    status = OllamaPromptAssistant().status("http://127.0.0.1:11434", "local-model")
    assert status.status == "ready" and status.selected_model_available and status.vision_capable
    assert status.models[0].name == "local-model"


@patch("services.h3_ollama_prompt_assistant.requests.post")
@patch("services.h3_ollama_prompt_assistant.OllamaPromptAssistant.status")
def test_improve_preserves_authoritative_silent_audio_rules(status: Mock, post: Mock) -> None:
    status.return_value = type("Status", (), {"status": "ready", "selected_model_available": True, "vision_capable": False, "message": "ready"})()
    post.return_value = response({"message": {"content": "A cyclist continues forward."}})
    result = OllamaPromptAssistant().improve(request())
    assert "no music, no soundtrack" in result.suggestion.lower()
    assert "no speech, no dialogue" in result.suggestion.lower()
    assert result.vision_context == "not_available"


@patch("services.h3_ollama_prompt_assistant.requests.post", side_effect=requests.Timeout())
@patch("services.h3_ollama_prompt_assistant.OllamaPromptAssistant.status")
def test_timeout_is_safe_and_keeps_original_outside_provider(status: Mock, post: Mock) -> None:
    status.return_value = type("Status", (), {"status": "ready", "selected_model_available": True, "vision_capable": False, "message": "ready"})()
    try:
        OllamaPromptAssistant().improve(request())
    except OllamaPromptAssistantError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("expected a safe local timeout")


@patch("services.h3_ollama_prompt_assistant.requests.post")
@patch("services.h3_ollama_prompt_assistant.OllamaPromptAssistant.status")
def test_reasoning_blocks_are_never_returned_to_director(status: Mock, post: Mock) -> None:
    status.return_value = type("Status", (), {"status": "ready", "selected_model_available": True, "vision_capable": False, "message": "ready"})()
    post.return_value = response({"message": {"content": "<think>internal reasoning</think> A cyclist turns into a side street."}})
    result = OllamaPromptAssistant().improve(request())
    assert "internal reasoning" not in result.suggestion
    assert result.suggestion.startswith("A cyclist turns")
