"""Local-only, declarative workflow import, analysis and validation foundation.

Imported JSON is data, never code: it is copied unchanged into H3-owned storage,
analysed conservatively, and remains disabled until a future explicit promotion.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

MAX_WORKFLOW_BYTES = 5 * 1024 * 1024
CONTROL_NAMES = frozenset({"prompt", "negative_prompt", "seed", "width", "height", "aspect_ratio", "megapixels", "fps", "frame_count", "duration", "reference_image", "first_frame", "last_frame", "prompt_enhance", "audio_guidance"})
MODEL_EXTENSIONS = frozenset({".safetensors", ".ckpt", ".pt", ".pth", ".onnx", ".bin", ".model"})
BUILTIN_IDS = frozenset({"minimax_h3_image_to_video", "minimax_h3_no_reference", "ltx_2_5_image_to_video", "ltx_2_5_text_to_video"})

class WorkflowCenterError(ValueError): pass

def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def detect_format(value: Any) -> str:
    if isinstance(value, dict) and value and all(isinstance(node, dict) and isinstance(node.get("class_type"), str) and isinstance(node.get("inputs"), dict) for node in value.values()): return "api"
    if isinstance(value, dict) and isinstance(value.get("nodes"), list): return "ui"
    return "invalid"

def analyze_api(workflow: dict[str, Any]) -> dict[str, Any]:
    nodes, models, mappings, caps = [], [], [], set()
    aliases = {"text": "prompt", "prompt": "prompt", "negative": "negative_prompt", "seed": "seed", "width": "width", "height": "height", "fps": "fps", "frame_rate": "fps", "frames": "frame_count", "num_frames": "frame_count", "duration": "duration", "image": "reference_image", "first_frame": "first_frame", "last_frame": "last_frame", "prompt_enhance": "prompt_enhance", "audio": "audio_guidance", "aspect_ratio": "aspect_ratio", "megapixels": "megapixels"}
    for node_id, node in workflow.items():
        if not isinstance(node, dict): continue
        klass, inputs = node.get("class_type", ""), node.get("inputs", {})
        nodes.append({"id": str(node_id), "class_type": klass, "inputs": sorted(inputs) if isinstance(inputs, dict) else []})
        lower = klass.lower()
        if "save" in lower or "createvideo" in lower: caps.add("video_output")
        if "audio" in lower: caps.add("audio")
        if "image" in lower: caps.add("image")
        if "sampler" in lower: caps.add("sampling")
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                canonical = aliases.get(key.lower())
                if canonical:
                    mappings.append({"control": canonical, "node_id": str(node_id), "input": key, "confidence": "high" if key.lower() in aliases else "low", "source": "auto"})
                if isinstance(value, str) and (key.lower().endswith("_name") or key.lower() in {"model", "filename", "checkpoint"}): models.append({"filename": value, "category": "unknown", "required": True})
    return {"nodes": nodes, "models": models, "capabilities": sorted(caps), "mappings": mappings, "unresolved_controls": sorted(CONTROL_NAMES - {m["control"] for m in mappings})}

class WorkflowCenter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(); self.registry_file = self.root / "registry.json"
    def _read(self) -> dict[str, Any]:
        if not self.registry_file.exists(): return {"schema_version": 1, "workflows": []}
        try: return json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise WorkflowCenterError("Workflow registry is unreadable.") from exc
    def list(self) -> list[dict[str, Any]]: return self._read()["workflows"]
    def import_json(self, source: Path) -> dict[str, Any]:
        source = source.resolve()
        if source.suffix.lower() != ".json" or not source.is_file(): raise WorkflowCenterError("Choose an existing JSON workflow file.")
        if source.stat().st_size > MAX_WORKFLOW_BYTES: raise WorkflowCenterError("Workflow JSON exceeds the 5 MiB safety limit.")
        try: payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise WorkflowCenterError("Workflow JSON is invalid.") from exc
        kind = detect_format(payload)
        if kind == "invalid": raise WorkflowCenterError("JSON is not a recognized ComfyUI UI or API workflow.")
        digest = _sha(source); stable_id = f"imported_{digest[:12]}"; revision = digest[:16]
        destination = self.root / "imports" / stable_id / revision / "source.json"
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, destination)
        entry = {"id": stable_id, "revision": revision, "display_name": source.stem, "built_in": False, "source_workflow": str(destination), "executable_api_workflow": str(destination) if kind == "api" else None, "sha256": digest, "format": kind, "status": "imported" if kind == "api" else "api_export_required", "runtime_verified": False, "enabled": False, "analysis": analyze_api(payload) if kind == "api" else {}, "manual_mappings": []}
        registry = self._read(); registry["workflows"] = [item for item in registry["workflows"] if not (item["id"] == stable_id and item["revision"] == revision)] + [entry]; _atomic_json(self.registry_file, registry)
        return entry
    def validate(self, workflow_id: str, object_info: dict[str, Any], model_roots: list[Path]) -> dict[str, Any]:
        entry = next((x for x in self.list() if x["id"] == workflow_id), None)
        if not entry: raise WorkflowCenterError("Imported workflow was not found.")
        if entry["format"] != "api": return {"status": "api_export_required", "nodes": {"available": 0, "required": 0}, "models": []}
        analysis = entry["analysis"]; missing_nodes = [n["class_type"] for n in analysis["nodes"] if n["class_type"] not in object_info]
        models=[]
        for requirement in analysis["models"]:
            found=[str(root / requirement["filename"]) for root in model_roots if (root / requirement["filename"]).is_file()]
            models.append({**requirement, "status": "found" if len(found)==1 else "duplicate" if len(found)>1 else "missing", "paths": found})
        status = "missing_nodes" if missing_nodes else "missing_models" if any(m["status"] == "missing" for m in models) else "contract_verified"
        entry["status"] = status; registry=self._read(); registry["workflows"]=[entry if x["id"]==workflow_id else x for x in registry["workflows"]]; _atomic_json(self.registry_file, registry)
        return {"status": status, "nodes": {"available": len(analysis["nodes"])-len(missing_nodes), "required": len(analysis["nodes"]), "missing": missing_nodes}, "models": models, "mappings": analysis["mappings"], "runtime_verified": False}
