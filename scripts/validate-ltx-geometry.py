"""Run one bounded H3-project LTX geometry validation.

Use this only for the explicitly approved validation presets.  The script
calls the normal project coordinator, records a durable result, and never
retries a failed render.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
# Match Electron's existing local app-data root when this supervised tool runs
# outside the Electron parent process. It does not create a separate project
# system; the coordinator still uses the normal H3 project store below it.
os.environ.setdefault("LTX_APP_DATA_DIR", str(Path(os.environ["LOCALAPPDATA"]) / "H3 Director Desktop"))

from api_types import H3ProjectCreateRequest, H3ProjectRenderRequest, H3SceneUpdateRequest
from ltx2_server import handler as app_handler
from services.ltx_2_5_geometry import resolve_ltx_geometry


def atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("ltx_2_5_text_to_video", "ltx_2_5_image_to_video"), required=True)
    parser.add_argument("--ratio", choices=("9:16 (Portrait Widescreen)", "1:1 (Square)"), required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.profile.endswith("image_to_video") and not args.reference:
        parser.error("--reference is required for LTX I2V")
    geometry = resolve_ltx_geometry(args.ratio, 0.9)
    mode = "text_to_video" if args.profile.endswith("text_to_video") else "image_to_video"
    result: dict[str, object] = {"started_at": datetime.now(UTC).isoformat(), "profile": args.profile, "mode": mode, "aspect_ratio": args.ratio, "megapixels": 0.9, "selector_dimensions": [geometry.selector_width, geometry.selector_height], "pre_latent_dimensions": [geometry.generation_width, geometry.generation_height], "latent_grid": list(geometry.latent_grid), "post_x2_latent_grid": list(geometry.post_x2_latent_grid), "predicted_final_dimensions": [geometry.final_width, geometry.final_height]}
    started = time.monotonic()
    try:
        # Use the normal application bootstrap, not a second coordinator.
        handler = app_handler.comfyui_minimax_h3
        project = handler.create_project(H3ProjectCreateRequest(name=f"LTX geometry validation {mode} {args.ratio[:4]}", workflow_profile_id=args.profile, workflow_mode=mode))
        scene = project.scenes[0]
        project = handler.update_scene(project.id, scene.id, H3SceneUpdateRequest(
            prompt="A calm cinematic night street with soft rain and distant city lights.",
            reference_image=str(args.reference) if args.reference else None,
            reference_fit="fill_crop", mode="new_shot", aspect_ratio=args.ratio,
            resolution_megapixels=0.9, width=geometry.final_width, height=geometry.final_height,
            fps=24, duration_seconds=5, frame_count=121, ltx_prompt_enhance=True,
        ))
        scene = project.scenes[0]
        completed = handler.render_project_scene(project.id, scene.id, H3ProjectRenderRequest(base_url="http://127.0.0.1:8190"))
        rendered = completed.scenes[0].render_versions[-1]
        result.update({"ok": True, "project_id": completed.id, "project_root": completed.project_root, "prompt_id": rendered.prompt_id, "render_version": rendered.id, "output_path": rendered.video_file, "metadata_path": rendered.metadata_file, "ffprobe": rendered.ffprobe.model_dump(), "elapsed_seconds": round(time.monotonic() - started, 3)})
    except Exception as exc:
        result.update({"ok": False, "error": str(exc), "elapsed_seconds": round(time.monotonic() - started, 3)})
    result["completed_at"] = datetime.now(UTC).isoformat()
    atomic_write(args.result, result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
