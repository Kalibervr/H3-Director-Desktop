"""Optional local-only Ollama provider for concise H3 video prompt suggestions."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from api_types import H3OllamaModel, H3PromptAssistantRequest, H3PromptAssistantStatusResponse
from server_utils.loopback_url import require_loopback_http_url
from services.h3_audio_guidance import H3AudioGuidance, compose_h3_prompt


class OllamaPromptAssistantError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaSuggestion:
    suggestion: str
    vision_context: str
    raw_response: dict[str, object]


class OllamaPromptAssistant:
    """Small provider boundary; all requests are restricted to a loopback Ollama API."""

    timeout_seconds = 45

    @staticmethod
    def _clean_suggestion(value: str) -> str:
        """Never surface local model reasoning blocks in the Director prompt preview."""
        return re.sub(r"<think>.*?</think>\s*", "", value, flags=re.IGNORECASE | re.DOTALL).strip()

    @staticmethod
    def _endpoint(endpoint: str) -> str:
        return require_loopback_http_url(endpoint)

    def _models(self, endpoint: str) -> list[H3OllamaModel]:
        payload = requests.get(f"{endpoint}/api/tags", timeout=5).json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        result: list[H3OllamaModel] = []
        for item in models:
            name = item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and name:
                result.append(H3OllamaModel(name=name))
        return result

    def _vision_capable(self, endpoint: str, model: str) -> bool:
        try:
            payload = requests.post(f"{endpoint}/api/show", json={"name": model}, timeout=8).json()
        except requests.RequestException:
            return False
        capabilities = payload.get("capabilities", []) if isinstance(payload, dict) else []
        return isinstance(capabilities, list) and "vision" in capabilities

    def status(self, endpoint: str, selected_model: str | None) -> H3PromptAssistantStatusResponse:
        try:
            endpoint = self._endpoint(endpoint)
            models = self._models(endpoint)
        except (ValueError, requests.RequestException):
            return H3PromptAssistantStatusResponse(status="not_running", endpoint="http://127.0.0.1:11434", message="Local Ollama is not running.")
        selected = next((item for item in models if item.name == selected_model), None)
        if selected_model and not selected:
            return H3PromptAssistantStatusResponse(status="model_not_installed", endpoint=endpoint, models=models, selected_model=selected_model, message="The selected local Ollama model is not installed.")
        if not models:
            return H3PromptAssistantStatusResponse(status="unavailable", endpoint=endpoint, models=[], message="Local Ollama has no installed models.")
        vision = self._vision_capable(endpoint, selected_model) if selected_model else False
        models = [item.model_copy(update={"vision_capable": item.name == selected_model and vision}) for item in models]
        return H3PromptAssistantStatusResponse(status="ready", endpoint=endpoint, models=models, selected_model=selected_model, selected_model_available=selected is not None, vision_capable=vision, message="Local Ollama is ready." if selected else "Choose an installed local Ollama model.")

    @staticmethod
    def _instruction(request: H3PromptAssistantRequest) -> str:
        previous = ""
        if request.previous_scene_prompt:
            previous = f" Previous scene {request.previous_scene_number or '?'} ({request.previous_scene_name or 'scene'}): {request.previous_scene_prompt}"
            if request.previous_final_prompt:
                previous += f" Previous final H3 prompt: {request.previous_final_prompt}"
            if request.continuity_source_version_id:
                previous += f" Continuity source version: {request.continuity_source_version_id}."
        return (
            "You are a concise H3 video prompt editor. Return only one improved video-generation prompt, no heading or explanation. "
            "Preserve the user's requested subject and events. Do not invent characters, dialogue, music, objects, camera changes, or story events. "
            "Make subject/action, motion, camera, environment, lighting, pacing, and continuity explicit only where supplied. "
            "For continuation scenes preserve established continuity unless the user explicitly changes it. "
            f"Project: {request.project_name}; sequence: {request.sequence_mode}. Current scene {request.scene_number} ({request.scene_name}), "
            f"mode {request.scene_mode}, {request.aspect_ratio}, {request.width}x{request.height}, {request.fps} FPS, {request.duration_seconds:g}s. "
            f"Raw prompt: {request.raw_prompt}.{previous}"
        )

    def improve(self, request: H3PromptAssistantRequest) -> OllamaSuggestion:
        endpoint = self._endpoint(request.endpoint)
        status = self.status(endpoint, request.model)
        if status.status != "ready" or not status.selected_model_available:
            raise OllamaPromptAssistantError(status.message)
        images: list[str] = []
        vision = "not_available"
        if status.vision_capable:
            candidate = request.continuity_frame_path or request.reference_image_path
            if candidate:
                path = Path(candidate)
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    images = [base64.b64encode(path.read_bytes()).decode("ascii")]
                    vision = "used"
        try:
            response = requests.post(
                f"{endpoint}/api/chat",
                json={"model": request.model, "stream": False, "messages": [{"role": "system", "content": self._instruction(request)}, {"role": "user", "content": request.raw_prompt, "images": images}]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            suggestion = payload.get("message", {}).get("content", "") if isinstance(payload, dict) else ""
        except requests.Timeout as exc:
            raise OllamaPromptAssistantError("Local Ollama timed out while improving the prompt.") from exc
        except requests.RequestException as exc:
            raise OllamaPromptAssistantError("Local Ollama could not improve the prompt.") from exc
        if not isinstance(suggestion, str) or not self._clean_suggestion(suggestion):
            raise OllamaPromptAssistantError("Local Ollama returned no prompt suggestion.")
        # Apply authoritative local audio rules after model output so they cannot be weakened.
        protected = compose_h3_prompt(self._clean_suggestion(suggestion), H3AudioGuidance(
            mode=request.audio_mode, no_speech=request.no_speech, no_music=request.no_music,
            custom_instruction=request.custom_audio_instruction,
        ))
        return OllamaSuggestion(suggestion=protected, vision_context=vision, raw_response=payload)
