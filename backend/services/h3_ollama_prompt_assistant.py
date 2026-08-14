"""Optional local-only Ollama provider for concise H3 video prompt suggestions."""

from __future__ import annotations

import base64
import json
import re
import time
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
    elapsed_seconds: float
    response_metadata: dict[str, int | str | bool | None]


class OllamaPromptAssistant:
    """Small provider boundary; all requests are restricted to a loopback Ollama API."""

    timeout_seconds = 120
    keep_alive = "30m"

    @staticmethod
    def _clean_suggestion(value: str) -> str:
        """Never surface local model reasoning blocks in the Director prompt preview."""
        return re.sub(r"<think>.*?</think>\s*", "", value, flags=re.IGNORECASE | re.DOTALL).strip()

    @classmethod
    def _visible_content(cls, payload: object) -> str:
        """Accept Ollama's non-stream chat shape without ever exposing `thinking`."""
        if not isinstance(payload, dict):
            raise OllamaPromptAssistantError("Local Ollama returned an invalid response payload.")
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else payload.get("response")
        if not isinstance(content, str):
            raise OllamaPromptAssistantError("Local Ollama returned no usable prompt text.")
        visible = cls._clean_suggestion(content)
        if not visible:
            raise OllamaPromptAssistantError("Local Ollama returned no usable prompt text.")
        return visible

    @staticmethod
    def _metadata(payload: dict[str, object]) -> dict[str, int | str | bool | None]:
        return {key: payload.get(key) if isinstance(payload.get(key), (int, str, bool)) else None for key in ("model", "done", "done_reason", "total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}

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

    @staticmethod
    def _running_model(endpoint: str, model: str | None) -> tuple[bool, int | None]:
        if not model:
            return False, None
        try:
            payload = requests.get(f"{endpoint}/api/ps", timeout=5).json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            for item in models:
                if isinstance(item, dict) and item.get("name") == model:
                    vram = item.get("size_vram")
                    return True, vram if isinstance(vram, int) and vram >= 0 else None
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            pass
        return False, None

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
        warm, vram = self._running_model(endpoint, selected_model)
        return H3PromptAssistantStatusResponse(status="ready", endpoint=endpoint, models=models, selected_model=selected_model, selected_model_available=selected is not None, vision_capable=vision, model_state="warm" if warm else "cold", model_vram_bytes=vram, message=("Local Ollama and the selected model are ready." if warm else "Local Ollama is ready; the selected model is not loaded yet.") if selected else "Choose an installed local Ollama model.")

    def warm(self, endpoint: str, model: str) -> H3PromptAssistantStatusResponse:
        endpoint = self._endpoint(endpoint)
        status = self.status(endpoint, model)
        if status.status != "ready" or not status.selected_model_available:
            raise OllamaPromptAssistantError(status.message)
        try:
            response = requests.post(f"{endpoint}/api/generate", json={"model": model, "prompt": "", "stream": False, "keep_alive": self.keep_alive}, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise OllamaPromptAssistantError("Local Ollama timed out while loading the selected model.") from exc
        except requests.RequestException as exc:
            raise OllamaPromptAssistantError("Local Ollama could not load the selected model.") from exc
        result = self.status(endpoint, model)
        return result.model_copy(update={"model_state": "warm" if result.model_state == "warm" else "unknown", "message": "Local Ollama model warmup completed." if result.model_state == "warm" else "Local Ollama accepted the model warmup request."})

    def release(self, endpoint: str, model: str) -> H3PromptAssistantStatusResponse:
        endpoint = self._endpoint(endpoint)
        try:
            response = requests.post(f"{endpoint}/api/generate", json={"model": model, "prompt": "", "stream": False, "keep_alive": 0}, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaPromptAssistantError("Local Ollama could not release the selected model before video rendering.") from exc
        result = self.status(endpoint, model)
        return result.model_copy(update={"model_state": "cold", "message": "Local Ollama model was released; the local server remains running."})

    @staticmethod
    def _instruction(request: H3PromptAssistantRequest) -> str:
        continuity = ""
        if any((request.current_location, request.current_state, request.next_action, request.persistent_visual_style, request.audio_state)):
            continuity = (
                " CONTINUATION CONTRACT:"
                f" CURRENT LOCATION (authoritative): {request.current_location or 'not supplied'}."
                f" CURRENT STATE: {request.current_state or 'not supplied'}."
                f" NEXT ACTION (highest priority): {request.next_action or request.raw_prompt}."
                f" PERSISTENT VISUAL STYLE: {request.persistent_visual_style or 'preserve only what is supplied'}."
                f" AUDIO STATE: {request.audio_state or 'follow the selected audio guidance'}."
                " The current location overrides historical environment text. Historical environment may influence only mood or style; never describe it as the current physical location. Do not replay prior actions."
            )
        previous = ""
        if request.previous_scene_prompt:
            previous = f" Historical context from scene {request.previous_scene_number or '?'} ({request.previous_scene_name or 'scene'}; secondary, do not replay): {request.previous_scene_prompt}"
            if request.previous_final_prompt:
                previous += f" Historical final H3 prompt (style and continuity only): {request.previous_final_prompt}"
            if request.continuity_source_version_id:
                previous += f" Continuity source version: {request.continuity_source_version_id}."
        return (
            "You are a concise H3 video prompt editor. Return only one improved video-generation prompt, no heading or explanation. "
            "Preserve the user's requested subject and events. Do not invent characters, dialogue, music, objects, camera changes, or story events. "
            "Make subject/action, motion, camera, environment, lighting, pacing, and continuity explicit only where supplied. "
            "For continuation scenes preserve established continuity unless the user explicitly changes it. "
            f"Project: {request.project_name}; sequence: {request.sequence_mode}. Current scene {request.scene_number} ({request.scene_name}), "
            f"mode {request.scene_mode}, {request.aspect_ratio}, {request.width}x{request.height}, {request.fps} FPS, {request.duration_seconds:g}s. "
            f"Raw prompt: {request.raw_prompt}.{continuity}{previous}"
        )

    @staticmethod
    def _next_scene_instruction(request: H3PromptAssistantRequest) -> str:
        """Keep action selection separate from the one-prompt editor contract."""
        return (
            "You are an H3 sequence director. Return exactly three distinct, concise next-scene actions "
            "as three numbered lines and nothing else. Each action must happen after the confirmed current "
            "state and begin from its current location. The CURRENT CONFIRMED OUTCOME and CURRENT LOCATION sections "
            "are authoritative; historical "
            "context must never pull the story backwards. Each action must be a single filmable next beat for a "
            "five-second scene. Do not repeat, summarize, or re-stage the previous action. Do not use vague filler, "
            "or passive descriptions of reflections, shadows, lighting, or atmosphere. Do not include dialogue, music, "
            "headings, explanations, resolution, FPS, or audio instructions. When SUGGESTION MODE is user_directed_variations, "
            "preserve the user's core action in every option and vary only camera, staging, timing, emphasis, or reaction.\n\n"
            f"{request.raw_prompt}"
        )

    def improve(self, request: H3PromptAssistantRequest) -> OllamaSuggestion:
        started = time.perf_counter()
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
                json={"model": request.model, "stream": False, "keep_alive": self.keep_alive, "messages": [{"role": "system", "content": self._instruction(request)}, {"role": "user", "content": request.raw_prompt, "images": images}]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            suggestion = self._visible_content(payload)
        except requests.Timeout as exc:
            raise OllamaPromptAssistantError("Local Ollama timed out while improving the prompt.") from exc
        except requests.RequestException as exc:
            raise OllamaPromptAssistantError("Local Ollama could not improve the prompt.") from exc
        # Apply authoritative local audio rules after model output so they cannot be weakened.
        protected = compose_h3_prompt(self._clean_suggestion(suggestion), H3AudioGuidance(
            mode=request.audio_mode, no_speech=request.no_speech, no_music=request.no_music,
            custom_instruction=request.custom_audio_instruction,
        ))
        return OllamaSuggestion(suggestion=protected, vision_context=vision, raw_response=payload, elapsed_seconds=time.perf_counter() - started, response_metadata=self._metadata(payload))

    def suggest_next_scene(self, request: H3PromptAssistantRequest) -> OllamaSuggestion:
        """Return raw numbered actions; never apply the single-prompt audio compositor here."""
        started = time.perf_counter()
        endpoint = self._endpoint(request.endpoint)
        status = self.status(endpoint, request.model)
        if status.status != "ready" or not status.selected_model_available:
            raise OllamaPromptAssistantError(status.message)
        try:
            response = requests.post(
                f"{endpoint}/api/chat",
                json={"model": request.model, "stream": False, "keep_alive": self.keep_alive, "messages": [
                    {"role": "system", "content": self._next_scene_instruction(request)},
                    {"role": "user", "content": request.raw_prompt},
                ]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            suggestion = self._visible_content(payload)
        except requests.Timeout as exc:
            raise OllamaPromptAssistantError("Local Ollama timed out while suggesting the next scene.") from exc
        except requests.RequestException as exc:
            raise OllamaPromptAssistantError("Local Ollama could not suggest the next scene.") from exc
        return OllamaSuggestion(suggestion=suggestion, vision_context="not_used", raw_response=payload, elapsed_seconds=time.perf_counter() - started, response_metadata=self._metadata(payload))
