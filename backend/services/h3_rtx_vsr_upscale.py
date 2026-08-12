"""Local-only NVIDIA RTX VSR post-processing through verified ComfyUI nodes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from services.comfyui_minimax_h3_provider import ProviderError, VideoProbe, probe_video
from server_utils.loopback_url import require_loopback_http_url

RTX_VSR_NODE = "ImageResizeKJv2"
VIDEO_LOAD_NODE = "VHS_LoadVideo"
VIDEO_COMBINE_NODE = "VHS_VideoCombine"
OUTPUT_NODE = "3"


@dataclass(frozen=True)
class RtxVsrResult:
    prompt_id: str
    output_file: Path
    metadata_file: Path
    video: VideoProbe
    source_video_sha256: str
    output_sha256: str


def build_rtx_vsr_workflow(*, staged_video: str, source_fps: float, target_width: int, target_height: int, filename_prefix: str) -> dict[str, Any]:
    """The only verified local workflow: VHS decode -> KJ RTX VSR -> VHS combine."""
    return {
        "1": {"class_type": VIDEO_LOAD_NODE, "inputs": {
            "video": staged_video, "force_rate": source_fps, "custom_width": 0,
            "custom_height": 0, "frame_load_cap": 0, "skip_first_frames": 0,
            "select_every_nth": 1,
        }},
        "2": {"class_type": RTX_VSR_NODE, "inputs": {
            "image": ["1", 0], "width": target_width, "height": target_height,
            "upscale_method": "nvidia_rtx_vsr", "keep_proportion": "stretch",
            "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 8,
            "device": "gpu",
        }},
        OUTPUT_NODE: {"class_type": VIDEO_COMBINE_NODE, "inputs": {
            "images": ["2", 0], "frame_rate": source_fps, "loop_count": 0,
            "filename_prefix": filename_prefix, "format": "video/h264-mp4",
            "pingpong": False, "save_output": True, "audio": ["1", 2],
        }},
    }


def _fps_float(value: str) -> float:
    numerator, separator, denominator = value.partition("/")
    try:
        return float(numerator) / float(denominator) if separator else float(numerator)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ProviderError("The source video has an invalid frame rate.") from exc


def _safe_relative_video_name(name: str) -> str:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix.lower() != ".mp4":
        raise ProviderError("The staged video name is unsafe.")
    return candidate.as_posix()


def _history_output(history: object, prompt_id: str, output_root: Path) -> Path:
    if not isinstance(history, dict) or not isinstance(history.get(prompt_id), dict):
        raise ProviderError("Local ComfyUI did not return upscale history.")
    record = history[prompt_id]
    status = record.get("status")
    if isinstance(status, dict) and status.get("status_str") == "error":
        raise ProviderError("Local ComfyUI failed while upscaling the video.")
    outputs = record.get("outputs")
    if not isinstance(outputs, dict) or not isinstance(outputs.get(OUTPUT_NODE), dict):
        raise ProviderError("Local ComfyUI did not report the upscale output.")
    descriptors = outputs[OUTPUT_NODE].get("gifs") or outputs[OUTPUT_NODE].get("images")
    if not isinstance(descriptors, list):
        raise ProviderError("Local ComfyUI did not report an upscale MP4.")
    root = output_root.resolve()
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        filename, subfolder, file_type = descriptor.get("filename"), descriptor.get("subfolder", ""), descriptor.get("type")
        if not isinstance(filename, str) or not filename.lower().endswith(".mp4") or file_type != "output" or not isinstance(subfolder, str):
            continue
        candidate = (root / subfolder / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProviderError("Local ComfyUI returned an unsafe upscale output path.") from exc
        if candidate.is_file():
            return candidate
    raise ProviderError("Local ComfyUI completed without a readable upscale MP4.")


class ComfyUIRtxVsrUpscaler:
    def __init__(self, *, input_root: Path, output_root: Path, ffprobe_path: Path, session: requests.Session | None = None) -> None:
        self._input_root = input_root
        self._output_root = output_root
        self._ffprobe_path = ffprobe_path
        self._session = session or requests.Session()

    def upscale_2x(self, *, base_url: str, source_video: Path, destination_root: Path) -> RtxVsrResult:
        try:
            base_url = require_loopback_http_url(base_url)
        except ValueError as exc:
            raise ProviderError("ComfyUI URL must be a loopback HTTP address.") from exc
        if not source_video.is_file() or source_video.suffix.lower() != ".mp4":
            raise ProviderError("The selected source render is unavailable.")
        if not self._input_root.is_dir() or not self._output_root.is_dir():
            raise ProviderError("Configured local ComfyUI media folders are unavailable.")
        source_probe = probe_video(self._ffprobe_path, source_video)
        if source_probe.width % 8 or source_probe.height % 8:
            raise ProviderError("RTX VSR requires source dimensions divisible by 8.")
        source_sha256 = hashlib.sha256(source_video.read_bytes()).hexdigest()
        staged_relative = _safe_relative_video_name(f"h3-director-upscale/{uuid.uuid4().hex}.mp4")
        staged = self._input_root / Path(staged_relative)
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_video, staged)
        prompt_id: str | None = None
        try:
            workflow = build_rtx_vsr_workflow(
                staged_video=staged_relative, source_fps=_fps_float(source_probe.fps),
                target_width=source_probe.width * 2, target_height=source_probe.height * 2,
                filename_prefix=f"h3-director/upscale_{uuid.uuid4().hex[:8]}",
            )
            response = self._session.post(f"{base_url}/prompt", json={"prompt": workflow, "client_id": uuid.uuid4().hex}, timeout=30, allow_redirects=False)
            payload = response.json()
            prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
            if not response.ok or not isinstance(prompt_id, str) or not prompt_id:
                raise ProviderError("Local ComfyUI did not accept the RTX VSR job.")
            deadline = time.monotonic() + 1800
            source_output: Path | None = None
            while time.monotonic() < deadline:
                history = self._session.get(f"{base_url}/history/{prompt_id}", timeout=30, allow_redirects=False).json()
                try:
                    source_output = _history_output(history, prompt_id, self._output_root)
                except ProviderError:
                    if isinstance(history, dict) and isinstance(history.get(prompt_id), dict) and history[prompt_id].get("status", {}).get("completed") is True:
                        raise
                if source_output:
                    break
                time.sleep(1)
            if source_output is None:
                raise ProviderError("The local RTX VSR operation timed out.")
            video = probe_video(self._ffprobe_path, source_output)
            if video.width != source_probe.width * 2 or video.height != source_probe.height * 2:
                raise ProviderError("The RTX VSR output dimensions did not match the verified 2× target.")
            destination_root.mkdir(parents=True, exist_ok=True)
            for number in range(1, 10000):
                candidate = destination_root / f"v{number:03d}"
                try:
                    candidate.mkdir()
                    break
                except FileExistsError:
                    continue
            else:
                raise ProviderError("No immutable RTX VSR version slot is available.")
            output = candidate / "video.mp4"
            metadata = candidate / "metadata.json"
            try:
                shutil.copy2(source_output, output)
                output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
                payload = {"schema_version": 1, "backend": "nvidia_rtx_vsr", "created_at": datetime.now(UTC).isoformat(),
                    "source_video": str(source_video), "source_video_sha256": source_sha256,
                    "source_resolution": {"width": source_probe.width, "height": source_probe.height},
                    "output_resolution": {"width": video.width, "height": video.height}, "scale": 2,
                    "fps": video.fps, "duration_seconds": video.duration_seconds,
                    "audio_preserved": video.audio_present, "prompt_id": prompt_id,
                    "output_sha256": output_sha256, "ffprobe": asdict(video)}
                temporary = candidate / f".metadata.{uuid.uuid4().hex}.tmp"
                with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(payload, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, metadata)
            except OSError as exc:
                shutil.rmtree(candidate, ignore_errors=True)
                raise ProviderError("The immutable RTX VSR output could not be created.") from exc
            return RtxVsrResult(prompt_id, output, metadata, video, source_sha256, output_sha256)
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("The local ComfyUI RTX VSR operation is unavailable.") from exc
        finally:
            try:
                staged.unlink(missing_ok=True)
                if staged.parent != self._input_root:
                    staged.parent.rmdir()
            except OSError:
                pass
