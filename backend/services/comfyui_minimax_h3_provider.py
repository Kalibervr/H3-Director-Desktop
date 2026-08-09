"""Minimal real single-scene MiniMax H3 provider for a local ComfyUI runtime."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol, cast
from urllib.parse import quote, urlsplit

import requests
from PIL import Image

from server_utils.loopback_url import require_loopback_http_url
from services.comfyui_runtime_probe import ComfyUIRuntimeProbe

JsonObject = dict[str, Any]
VERIFIED_WORKFLOW_SHA256 = "51febcadb3d33f2850f2a9ec905e16c34c8ac3d28d70b3fdbe6c228addc55030"
VERIFIED_WIDTH = 640
VERIFIED_HEIGHT = 640
VERIFIED_DURATION_SECONDS = 5.0
VERIFIED_FPS = 24
OUTPUT_NODE_ID = "92"


class ProviderError(RuntimeError):
    """A safe error whose message may be returned to a local client."""


class HttpResponse(Protocol):
    is_redirect: bool

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class HttpSession(Protocol):
    def get(self, url: str, **kwargs: object) -> HttpResponse: ...
    def post(self, url: str, **kwargs: object) -> HttpResponse: ...


@dataclass(frozen=True)
class SingleSceneRequest:
    prompt: str
    input_image: Path
    seed: int
    width: int = VERIFIED_WIDTH
    height: int = VERIFIED_HEIGHT
    duration_seconds: float = VERIFIED_DURATION_SECONDS
    fps: int = VERIFIED_FPS
    output_filename_prefix: str = "MiniMax_H3"


@dataclass(frozen=True)
class VideoProbe:
    codec: str
    width: int
    height: int
    fps: str
    duration_seconds: float
    frame_count: int | None
    audio_present: bool


@dataclass(frozen=True)
class RenderResult:
    prompt_id: str
    source_output: Path
    render_directory: Path
    output_file: Path
    metadata_file: Path
    video: VideoProbe


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ProviderError("Local ComfyUI returned an incompatible response.")
    return cast(JsonObject, value)


def _safe_json(response: HttpResponse) -> object:
    if response.is_redirect:
        raise ProviderError("Local ComfyUI returned an unexpected redirect.")
    try:
        response.raise_for_status()
        return response.json()
    except ProviderError:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise ProviderError("Local ComfyUI returned an invalid response.") from exc


def load_verified_workflow(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderError("The verified MiniMax H3 workflow is unavailable.") from exc
    if hashlib.sha256(raw).hexdigest() != VERIFIED_WORKFLOW_SHA256:
        raise ProviderError("The verified MiniMax H3 workflow has changed.")
    try:
        return _json_object(json.loads(raw))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderError("The verified MiniMax H3 workflow is invalid.") from exc


def build_prompt_payload(
    template: JsonObject,
    request: SingleSceneRequest,
    staged_image_name: str,
    client_id: str,
) -> JsonObject:
    if not request.prompt.strip():
        raise ProviderError("A prompt is required.")
    if (request.width, request.height) != (VERIFIED_WIDTH, VERIFIED_HEIGHT):
        raise ProviderError("Only the verified 640x640 resolution is currently supported.")
    if request.duration_seconds != VERIFIED_DURATION_SECONDS:
        raise ProviderError("Only the verified 5 second duration is currently supported.")
    if request.fps != VERIFIED_FPS:
        raise ProviderError("Only the verified 24 FPS rate is currently supported.")
    if request.seed < 0 or request.seed > 0xFFFFFFFFFFFFFFFF:
        raise ProviderError("Seed is outside the verified node range.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", request.output_filename_prefix):
        raise ProviderError("Output filename prefix contains unsupported characters.")
    if not staged_image_name or Path(staged_image_name).is_absolute() or ".." in Path(staged_image_name).parts:
        raise ProviderError("Local ComfyUI returned an unsafe staged image name.")

    workflow = copy.deepcopy(template)
    workflow["105:104"]["inputs"]["prompt"] = request.prompt.strip()
    workflow["114"]["inputs"]["image"] = staged_image_name.replace("\\", "/")
    workflow["105:15"]["inputs"]["noise_seed"] = request.seed
    workflow["115"]["inputs"]["aspect_ratio"] = "1:1 (Square)"
    workflow["115"]["inputs"]["megapixels"] = 0.4
    workflow["115"]["inputs"]["multiple"] = 32
    workflow["105:111"]["inputs"]["value"] = request.duration_seconds
    workflow["105:91"]["inputs"]["fps"] = request.fps
    workflow["92"]["inputs"]["filename_prefix"] = (
        f"h3-director/{request.output_filename_prefix}_{client_id[:8]}"
    )
    return {"prompt": workflow, "client_id": client_id}


def discover_output(history: object, prompt_id: str, output_root: Path) -> Path | None:
    history_object = _json_object(history)
    record = history_object.get(prompt_id)
    if record is None:
        return None
    record_object = _json_object(record)
    status = _json_object(record_object.get("status"))
    if status.get("status_str") == "error":
        raise ProviderError("Local ComfyUI failed to render the scene.")
    if status.get("completed") is not True:
        return None
    outputs = _json_object(record_object.get("outputs"))
    output_node = _json_object(outputs.get(OUTPUT_NODE_ID))
    if output_node.get("animated") != [True]:
        raise ProviderError("Local ComfyUI did not report an animated output.")
    descriptors = output_node.get("images")
    if not isinstance(descriptors, list):
        raise ProviderError("Local ComfyUI did not report the expected video output.")

    root = output_root.resolve()
    for value in cast(list[object], descriptors):
        descriptor = _json_object(value)
        filename = descriptor.get("filename")
        subfolder = descriptor.get("subfolder", "")
        if descriptor.get("type") != "output" or not isinstance(filename, str) or not filename.lower().endswith(".mp4"):
            continue
        if not isinstance(subfolder, str):
            continue
        candidate = (root / subfolder / filename).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProviderError("Local ComfyUI returned an unsafe output path.") from exc
        if candidate.is_file():
            return candidate
    raise ProviderError("Local ComfyUI completed without a readable MP4 output.")


def probe_video(ffprobe_path: Path, video_path: Path, timeout_seconds: float = 30.0) -> VideoProbe:
    if not ffprobe_path.is_file():
        raise ProviderError("The verified bundled ffprobe executable is unavailable.")
    if not video_path.is_file():
        raise ProviderError("The rendered MP4 is unavailable.")
    command = [
        str(ffprobe_path), "-v", "error", "-show_streams", "-show_format",
        "-count_frames", "-of", "json", str(video_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        if completed.returncode != 0:
            raise ProviderError("The rendered MP4 failed ffprobe verification.")
        payload = _json_object(json.loads(completed.stdout))
    except ProviderError:
        raise
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ProviderError("The rendered MP4 could not be verified.") from exc
    streams_value = payload.get("streams")
    if not isinstance(streams_value, list):
        raise ProviderError("The rendered MP4 has invalid stream metadata.")
    streams = [_json_object(stream) for stream in cast(list[object], streams_value)]
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise ProviderError("The rendered MP4 has no video stream.")
    audio_present = any(stream.get("codec_type") == "audio" for stream in streams)
    duration_raw = (_json_object(payload.get("format"))).get("duration")
    try:
        if not isinstance(duration_raw, (str, int, float)):
            raise ValueError
        duration = float(duration_raw)
        frame_raw = video.get("nb_read_frames") or video.get("nb_frames")
        if frame_raw not in (None, "N/A") and not isinstance(frame_raw, (str, int)):
            raise ValueError
        frame_count = int(frame_raw) if isinstance(frame_raw, (str, int)) else None
        codec = video.get("codec_name")
        width = video.get("width")
        height = video.get("height")
        fps = video.get("avg_frame_rate") or video.get("r_frame_rate")
        if not isinstance(codec, str) or not isinstance(width, int) or not isinstance(height, int) or not isinstance(fps, str):
            raise ValueError
        return VideoProbe(
            codec=codec, width=width, height=height, fps=fps,
            duration_seconds=duration, frame_count=frame_count, audio_present=audio_present,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("The rendered MP4 has incomplete stream metadata.") from exc


def create_immutable_render_version(
    render_root: Path,
    source_output: Path,
    prompt_id: str,
    request: SingleSceneRequest,
    video: VideoProbe,
) -> tuple[Path, Path, Path]:
    render_root.mkdir(parents=True, exist_ok=True)
    version_dir: Path | None = None
    for number in range(1, 10000):
        candidate = render_root / f"v{number:03d}"
        try:
            candidate.mkdir()
            version_dir = candidate
            break
        except FileExistsError:
            continue
    if version_dir is None:
        raise ProviderError("No immutable render version slot is available.")
    output = version_dir / "video.mp4"
    metadata = version_dir / "metadata.json"
    try:
        shutil.copy2(source_output, output)
        metadata_payload = {
            "schema_version": 1,
            "provider": "ComfyUIMiniMaxH3Provider",
            "created_at": datetime.now(UTC).isoformat(),
            "prompt_id": prompt_id,
            "prompt": request.prompt,
            "seed": request.seed,
            "width": request.width,
            "height": request.height,
            "duration_seconds": request.duration_seconds,
            "fps": request.fps,
            "input_image_sha256": hashlib.sha256(request.input_image.read_bytes()).hexdigest(),
            "workflow_sha256": VERIFIED_WORKFLOW_SHA256,
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "ffprobe": asdict(video),
        }
        metadata.write_text(json.dumps(metadata_payload, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        shutil.rmtree(version_dir, ignore_errors=True)
        raise ProviderError("The immutable render version could not be created.") from exc
    return version_dir, output, metadata


class ComfyUIMiniMaxH3Provider:
    """Development provider; it connects to but does not own the ComfyUI lifecycle."""

    def __init__(
        self,
        *,
        workflow_path: Path,
        output_root: Path,
        render_root: Path,
        ffprobe_path: Path,
        session: HttpSession | None = None,
        runtime_probe: ComfyUIRuntimeProbe | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._workflow_path = workflow_path
        self._output_root = output_root
        self._render_root = render_root
        self._ffprobe_path = ffprobe_path
        self._session = session or cast(HttpSession, requests.Session())
        self._runtime_probe = runtime_probe or ComfyUIRuntimeProbe()
        self._sleep = sleep

    def render(
        self,
        *,
        base_url: str,
        request: SingleSceneRequest,
        timeout_seconds: float = 1800.0,
        poll_interval_seconds: float = 2.0,
    ) -> RenderResult:
        try:
            normalized_url = require_loopback_http_url(base_url)
            if urlsplit(normalized_url).scheme != "http":
                raise ValueError
        except ValueError as exc:
            raise ProviderError("ComfyUI URL must be a loopback HTTP address.") from exc
        template = load_verified_workflow(self._workflow_path)
        runtime = self._runtime_probe.probe(base_url=normalized_url, workflow=template)
        if runtime.status != "connected":
            raise ProviderError("Local ComfyUI is unavailable or incompatible with the verified workflow.")
        if not request.input_image.is_file():
            raise ProviderError("The input image is unavailable.")
        try:
            with Image.open(request.input_image) as image:
                image.verify()
        except (OSError, ValueError) as exc:
            raise ProviderError("The input image is invalid.") from exc

        staged_name = self._upload_image(normalized_url, request.input_image)
        client_id = uuid.uuid4().hex
        payload = build_prompt_payload(template, request, staged_name, client_id)
        try:
            response = self._session.post(
                f"{normalized_url}/prompt", json=payload, timeout=30.0, allow_redirects=False
            )
            submission = _json_object(_safe_json(response))
        except ProviderError:
            raise
        except requests.RequestException as exc:
            raise ProviderError("The scene could not be submitted to local ComfyUI.") from exc
        prompt_id = submission.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ProviderError("Local ComfyUI did not return a prompt ID.")

        deadline = time.monotonic() + timeout_seconds
        source_output: Path | None = None
        while time.monotonic() < deadline:
            try:
                history_response = self._session.get(
                    f"{normalized_url}/history/{quote(prompt_id, safe='')}",
                    timeout=30.0,
                    allow_redirects=False,
                )
                source_output = discover_output(_safe_json(history_response), prompt_id, self._output_root)
            except ProviderError:
                raise
            except requests.RequestException as exc:
                raise ProviderError("Local ComfyUI history is unavailable.") from exc
            if source_output is not None:
                break
            self._sleep(poll_interval_seconds)
        if source_output is None:
            raise ProviderError("The local ComfyUI render timed out.")

        video = probe_video(self._ffprobe_path, source_output)
        version_dir, output, metadata = create_immutable_render_version(
            self._render_root, source_output, prompt_id, request, video
        )
        return RenderResult(prompt_id, source_output, version_dir, output, metadata, video)

    def _upload_image(self, base_url: str, image_path: Path) -> str:
        try:
            with image_path.open("rb") as stream:
                response = self._session.post(
                    f"{base_url}/upload/image",
                    files={"image": (image_path.name, stream, "application/octet-stream")},
                    data={"type": "input", "overwrite": "false"},
                    timeout=60.0,
                    allow_redirects=False,
                )
                payload = _json_object(_safe_json(response))
        except ProviderError:
            raise
        except (OSError, requests.RequestException) as exc:
            raise ProviderError("The input image could not be staged in local ComfyUI.") from exc
        name = payload.get("name")
        subfolder = payload.get("subfolder", "")
        if not isinstance(name, str) or not isinstance(subfolder, str):
            raise ProviderError("Local ComfyUI returned an invalid staged image response.")
        staged = str(Path(subfolder) / name) if subfolder else name
        if Path(staged).is_absolute() or ".." in Path(staged).parts:
            raise ProviderError("Local ComfyUI returned an unsafe staged image name.")
        return staged
