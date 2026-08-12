"""Declarative, local-only workflow profile validation and registry."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class WorkflowProfileError(ValueError): pass

_ALLOWED = {"profile.json", "workflow_api.json", "workflow_ui.json", "model-manifest.json", "README.md"}
_REQUIRED = {"id", "display_name", "provider_family", "version", "profile_schema_version", "modes", "workflow"}

def validate_profile_package(folder: Path) -> dict[str, Any]:
    folder = folder.resolve()
    profile_file = folder / "profile.json"
    if not profile_file.is_file(): raise WorkflowProfileError("Profile package requires profile.json.")
    try: payload = json.loads(profile_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise WorkflowProfileError("Profile manifest is invalid JSON.") from exc
    if not isinstance(payload, dict) or _REQUIRED - payload.keys(): raise WorkflowProfileError("Profile manifest has missing required fields.")
    if payload.get("profile_schema_version") != 1: raise WorkflowProfileError("Unsupported profile schema version.")
    if not isinstance(payload.get("id"), str) or not payload["id"].replace("_", "").isalnum(): raise WorkflowProfileError("Profile ID is invalid.")
    workflow = payload.get("workflow")
    if not isinstance(workflow, dict) or workflow.get("api") != "workflow_api.json": raise WorkflowProfileError("Profile workflow must use local workflow_api.json.")
    if not (folder / "workflow_api.json").is_file(): raise WorkflowProfileError("Profile API workflow is missing.")
    modes = payload.get("modes")
    if not isinstance(modes, list) or not modes or any(not isinstance(mode, dict) or mode.get("id") not in {"image_to_video", "text_to_video", "video_to_video", "continue_extend", "multi_shot"} for mode in modes): raise WorkflowProfileError("Profile capabilities are invalid.")
    for item in folder.iterdir():
        if item.name not in _ALLOWED or item.is_dir() or item.suffix.lower() in {".py", ".js", ".exe", ".bat", ".cmd", ".ps1"}: raise WorkflowProfileError("Profiles may contain only approved declarative files.")
    try: json.loads((folder / "workflow_api.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise WorkflowProfileError("Profile API workflow is invalid JSON.") from exc
    manifest = folder / "model-manifest.json"
    if manifest.exists():
        try: models = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise WorkflowProfileError("Model manifest is invalid JSON.") from exc
        if not isinstance(models, dict) or not isinstance(models.get("models"), list): raise WorkflowProfileError("Model manifest is invalid.")
    return payload

class WorkflowProfileRegistry:
    def __init__(self, managed_root: Path) -> None: self.managed_root = managed_root.resolve()
    def install(self, source: Path) -> Path:
        profile = validate_profile_package(source)
        destination = self.managed_root / profile["id"] / str(profile["version"])
        if destination.exists(): raise WorkflowProfileError("A profile with this ID and version is already installed.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source.resolve(), destination)
        return destination
    def list_installed(self) -> list[dict[str, Any]]:
        if not self.managed_root.exists(): return []
        result = []
        for path in self.managed_root.glob("*/*"):
            if path.is_dir():
                try: result.append(validate_profile_package(path))
                except WorkflowProfileError: continue
        return result
