"""Capture one local-only H3 Ollama Prompt Assistant verification result.

This utility deliberately writes the result before process exit so terminal
capture cannot be mistaken for provider failure. It calls the same provider as
the FastAPI route; it does not call Ollama directly.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from api_types import H3PromptAssistantRequest
from services.h3_ollama_prompt_assistant import OllamaPromptAssistant


def atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = H3PromptAssistantRequest(
        endpoint="http://127.0.0.1:11434", model="qwen3:4b",
        raw_prompt="She continues walking and turns into a side street.",
        scene_number=2, scene_name="Scene 02", project_name="Ollama lifecycle validation",
        sequence_mode="continuous_sequence", scene_mode="continue_previous",
        previous_scene_number=1, previous_scene_name="Scene 01",
        previous_scene_prompt="A woman walks through a rainy city street at night.",
        aspect_ratio="16:9 (Widescreen)", width=1280, height=704, duration_seconds=5,
        fps=24, audio_mode="natural_ambience", no_speech=True, no_music=True,
    )
    started = time.monotonic()
    payload: dict[str, object] = {
        "started_at": datetime.now(UTC).isoformat(), "endpoint": request.endpoint,
        "model": request.model, "provider": "OllamaPromptAssistant",
    }
    try:
        result = OllamaPromptAssistant().improve(request)
        payload.update({
            "ok": True, "elapsed_seconds": round(time.monotonic() - started, 3),
            "suggestion": result.suggestion, "vision_context": result.vision_context,
            "fallback_used": False,
        })
    except Exception as exc:  # Persist an exact bounded diagnostic before exit.
        payload.update({"ok": False, "elapsed_seconds": round(time.monotonic() - started, 3), "error": str(exc)})
    payload["completed_at"] = datetime.now(UTC).isoformat()
    atomic_write(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
