"""Non-mutating ComfyUI runtime update/rollback planning primitives."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class RuntimeManagerError(ValueError): pass
def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(value, indent=2), encoding='utf-8'); os.replace(temp,path)
def detect_runtime(root: Path, python: Path, endpoint: str, shared_model_config: str | None = None) -> dict[str, Any]:
    root=root.resolve(); python=python.resolve()
    return {"root": str(root), "python": str(python), "endpoint": endpoint, "main_py": (root/'main.py').is_file(), "python_exists": python.is_file(), "shared_model_config": shared_model_config, "version": _read_version(root), "managed_only": True}
def _read_version(root: Path) -> str | None:
    for candidate in (root/'comfyui_version.py', root/'version.py'):
        if candidate.is_file():
            text=candidate.read_text(encoding='utf-8', errors='ignore')
            for line in text.splitlines():
                if '__version__' in line and '=' in line: return line.split('=',1)[1].strip().strip('"\'')
    return None
def backup_manifest(snapshot_dir: Path, runtime: dict[str, Any], custom_nodes: list[dict[str, str]] | None = None) -> Path:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); path=snapshot_dir/f'{stamp}.json'
    _write(path, {"schema_version": 1, "created_at": stamp, "runtime": runtime, "custom_nodes": custom_nodes or [], "shared_models_included": False})
    return path
def update_plan(runtime: dict[str, Any], owned: bool) -> dict[str, Any]:
    if not owned: raise RuntimeManagerError('Only an H3-managed ComfyUI runtime can be updated.')
    return {"dry_run": True, "steps": ["stop owned runtime", "create rollback manifest", "obtain explicitly approved trusted update", "restart", "inspect object_info", "validate profile compatibility", "offer rollback on incompatibility"], "shared_models_modified": False}
def rollback_plan(snapshot: Path, owned: bool) -> dict[str, Any]:
    if not owned: raise RuntimeManagerError('Only an H3-managed ComfyUI runtime can be rolled back.')
    if not snapshot.is_file(): raise RuntimeManagerError('Selected rollback manifest does not exist.')
    return {"dry_run": True, "snapshot": str(snapshot.resolve()), "steps": ["stop owned runtime", "restore approved runtime snapshot", "restart", "validate profiles"], "shared_models_modified": False}
