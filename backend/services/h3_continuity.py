"""Verified, immutable continuity-frame extraction for H3 Director scenes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from api_types import H3ContinuityArtifact, H3Project, H3RenderVersion, H3Scene
from services.comfyui_minimax_h3_provider import ProviderError, probe_video


class ContinuityError(RuntimeError):
    """A sanitized continuity error suitable for the local UI."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContinuityError("The continuity source could not be read.") from exc
    return digest.hexdigest()


def _atomic_json_write(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ContinuityError("The continuity metadata could not be saved safely.") from exc


def previous_scene(project: H3Project, scene_id: str) -> H3Scene:
    ordered = sorted(project.scenes, key=lambda item: item.order)
    index = next((position for position, scene in enumerate(ordered) if scene.id == scene_id), None)
    if index is None:
        raise ContinuityError("The selected scene could not be found.")
    if index == 0:
        raise ContinuityError("Continue Previous requires a scene before the selected scene.")
    return ordered[index - 1]


def selected_completed_version(scene: H3Scene) -> H3RenderVersion:
    if scene.status != "complete" or not scene.selected_render_version_id:
        raise ContinuityError("The previous scene requires a selected completed render version.")
    version = next(
        (item for item in scene.render_versions if item.id == scene.selected_render_version_id),
        None,
    )
    if version is None:
        raise ContinuityError("The previous scene's selected render version could not be found.")
    video = Path(version.video_file)
    if not video.is_file():
        raise ContinuityError("The previous scene's selected render file is unavailable.")
    return version


class H3ContinuityExtractor:
    def __init__(self, ffmpeg_path: Path, ffprobe_path: Path) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path

    def extract(self, project: H3Project, scene: H3Scene) -> H3ContinuityArtifact:
        if scene.mode != "continue_previous":
            raise ContinuityError("Continuity extraction requires Continue Previous mode.")
        source_scene = previous_scene(project, scene.id)
        source_version = selected_completed_version(source_scene)
        source_video = Path(source_version.video_file)
        try:
            video = probe_video(self._ffprobe_path, source_video)
        except ProviderError as exc:
            raise ContinuityError("The previous scene render failed ffprobe verification.") from exc
        if video.frame_count is None or video.frame_count < 1:
            raise ContinuityError("The previous scene render has no verified frame count.")
        offset = scene.continuity_offset_frames if scene.continuity_strategy == "offset_from_end" else 0
        if offset >= video.frame_count:
            raise ContinuityError("The continuity offset exceeds the previous scene's frame count.")
        frame_index = video.frame_count - 1 - offset
        try:
            fps = Fraction(video.fps)
        except (ValueError, ZeroDivisionError) as exc:
            raise ContinuityError("The previous scene render has an invalid verified FPS.") from exc
        if fps <= 0:
            raise ContinuityError("The previous scene render has an invalid verified FPS.")

        continuity_root = Path(project.project_root) / "scenes" / scene.storage_name / "continuity"
        continuity_root.mkdir(parents=True, exist_ok=True)
        number = self._next_number(continuity_root)
        artifact_root = continuity_root / f"c{number:03d}"
        try:
            artifact_root.mkdir(exist_ok=False)
        except OSError as exc:
            raise ContinuityError("A new immutable continuity folder could not be created.") from exc
        image_file = artifact_root / "frame.png"
        metadata_file = artifact_root / "metadata.json"
        command = [
            str(self._ffmpeg_path), "-v", "error", "-i", str(source_video),
            "-vf", f"select=eq(n\\,{frame_index})", "-frames:v", "1", "-fps_mode", "vfr",
            str(image_file),
        ]
        try:
            if not self._ffmpeg_path.is_file():
                raise ContinuityError("The verified bundled ffmpeg executable is unavailable.")
            result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
            if result.returncode != 0 or not image_file.is_file() or image_file.stat().st_size == 0:
                raise ContinuityError("The continuity frame could not be extracted with ffmpeg.")
            artifact = H3ContinuityArtifact(
                id=f"c{number:03d}", number=number,
                created_at=datetime.now(UTC).isoformat(), root=str(artifact_root),
                image_file=str(image_file), metadata_file=str(metadata_file),
                image_sha256=_sha256(image_file), source_scene_id=source_scene.id,
                source_render_version_id=source_version.id,
                source_video_reference=str(source_video), source_video_sha256=_sha256(source_video),
                frame_index=frame_index, timestamp_seconds=float(Fraction(frame_index, 1) / fps),
                strategy=scene.continuity_strategy, offset_from_end_frames=offset,
                source_frame_count=video.frame_count, source_fps=video.fps,
            )
            _atomic_json_write(metadata_file, artifact.model_dump(mode="json"))
            return artifact
        except (OSError, subprocess.SubprocessError) as exc:
            raise ContinuityError("The continuity frame could not be extracted with ffmpeg.") from exc

    @staticmethod
    def _next_number(root: Path) -> int:
        numbers = [
            int(path.name.removeprefix("c")) for path in root.glob("c[0-9][0-9][0-9]")
            if path.is_dir()
        ]
        return max(numbers, default=0) + 1
