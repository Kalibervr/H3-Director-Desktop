"""Deterministic, local-only audio prompt guidance for MiniMax H3 scenes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AudioMode = Literal["natural_ambience", "dialogue", "silent"]


@dataclass(frozen=True)
class H3AudioGuidance:
    mode: AudioMode = "natural_ambience"
    no_speech: bool = False
    no_music: bool = False
    custom_instruction: str = ""


def compose_h3_prompt(original_prompt: str, guidance: H3AudioGuidance) -> str:
    """Append predictable audio instructions once, without changing user prose."""
    original = original_prompt.strip()
    if not original:
        raise ValueError("A scene prompt is required.")

    parts = [original]

    def append_once(instruction: str) -> None:
        if instruction.lower() not in original.lower() and all(instruction.lower() not in item.lower() for item in parts):
            parts.append(instruction)
    custom = guidance.custom_instruction.strip()
    if guidance.mode == "silent":
        # Silence has deterministic precedence over every audio option and custom sound.
        append_once("No speech, no dialogue, no voices, no vocalizations, no music, no soundtrack, no background score, no singing, no musical elements, no ambient sound.")
    else:
        if guidance.mode == "natural_ambience":
            append_once("Natural environmental ambience appropriate to the scene.")
        # Dialogue intentionally adds no invented words and never suppresses user dialogue.
        if custom:
            append_once(custom)
        if guidance.no_speech:
            append_once("No speech, no dialogue, no voices, no vocalizations.")
        if guidance.no_music:
            append_once("No music, no soundtrack, no background score, no singing, no musical elements.")
    return " ".join(parts)


def audio_summary(guidance: H3AudioGuidance) -> str:
    if guidance.mode == "silent":
        return "Silent"
    labels = ["Natural ambience" if guidance.mode == "natural_ambience" else "Dialogue"]
    if guidance.no_speech:
        labels.append("No speech")
    if guidance.no_music:
        labels.append("No music")
    return " · ".join(labels)
