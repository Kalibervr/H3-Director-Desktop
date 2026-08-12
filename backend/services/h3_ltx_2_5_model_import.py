"""Safe, manual-only import and layout validation for official gated LTX-2.5 files."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


@dataclass(frozen=True)
class Ltx25Asset:
    filename: str
    destination_category: str
    required: bool


LTX_2_5_ASSETS: tuple[Ltx25Asset, ...] = (
    Ltx25Asset("ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", "diffusion_models", True),
    Ltx25Asset("gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "text_encoders", True),
    Ltx25Asset("gemma4_e2b_it_bf16.safetensors", "text_encoders", True),
    Ltx25Asset("ltx-2.5-video-vae-bf16.safetensors", "vae", True),
    Ltx25Asset("ltx-2.5-audio-vae-bf16.safetensors", "vae", True),
    Ltx25Asset("ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", "latent_upscale_models", True),
)
_BY_NAME = {asset.filename: asset for asset in LTX_2_5_ASSETS}


class Ltx25ModelImportError(ValueError):
    pass


def resolve_shared_model_root(config_path: str) -> Path:
    path = Path(config_path).expanduser()
    if path.suffix.lower() not in {".yaml", ".yml"} or not path.is_file():
        raise Ltx25ModelImportError("The configured shared model-path file is unavailable.")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise Ltx25ModelImportError("The shared model-path configuration is invalid.") from exc
    if not isinstance(payload, dict):
        raise Ltx25ModelImportError("The shared model-path configuration has no model root.")
    roots = [entry.get("base_path") for entry in payload.values() if isinstance(entry, dict) and isinstance(entry.get("base_path"), str)]
    if not roots:
        raise Ltx25ModelImportError("The shared model-path configuration has no model root.")
    root = Path(roots[0]).expanduser()
    if not root.is_absolute():
        raise Ltx25ModelImportError("The shared model-path configuration must use an absolute model root.")
    return root


def _status(asset: Ltx25Asset, state: str, *, size: int | None = None, message: str) -> dict[str, object]:
    return {"filename": asset.filename, "destination_category": asset.destination_category, "required": asset.required, "state": state, "file_size_bytes": size, "message": message}


def inspect_ltx25_assets(model_root: Path, selected_paths: Iterable[str] = ()) -> list[dict[str, object]]:
    selected = [Path(value).expanduser() for value in selected_paths]
    by_name: dict[str, list[Path]] = {}
    unknown: list[Path] = []
    for item in selected:
        if item.name in _BY_NAME:
            by_name.setdefault(item.name, []).append(item)
        else:
            unknown.append(item)
    results: list[dict[str, object]] = []
    for asset in LTX_2_5_ASSETS:
        destination = model_root / asset.destination_category / asset.filename
        matches = by_name.get(asset.filename, [])
        wrong_locations = [item for item in model_root.rglob(asset.filename) if item != destination] if model_root.is_dir() else []
        if wrong_locations:
            results.append(_status(asset, "wrong_destination", size=wrong_locations[0].stat().st_size, message="Found under the configured model root, but not in the required destination category."))
        elif len(matches) > 1 or destination.is_file() and matches:
            results.append(_status(asset, "duplicate", size=destination.stat().st_size if destination.is_file() else None, message="A destination file already exists or was selected more than once; nothing will be overwritten."))
        elif destination.is_file():
            results.append(_status(asset, "found", size=destination.stat().st_size, message="Found in the configured shared model path."))
        elif matches:
            source = matches[0]
            if not source.is_file() or source.suffix.lower() != ".safetensors":
                results.append(_status(asset, "wrong_filename", message="Only the exact official .safetensors filename can be imported."))
            else:
                results.append(_status(asset, "missing", size=source.stat().st_size, message="Selected for manual import into the required destination category."))
        else:
            results.append(_status(asset, "missing", message="Missing from the configured shared model path."))
    for item in unknown:
        likely_ltx = item.name.lower().startswith("ltx-2.5") or item.name.lower().startswith("gemma4")
        results.append({"filename": item.name, "destination_category": None, "required": False, "state": "wrong_filename" if likely_ltx else "unknown", "file_size_bytes": item.stat().st_size if item.is_file() else None, "message": "The filename is not in the verified LTX 2.5 manifest." if likely_ltx else "Unknown or unverified files are not imported."})
    return results


def import_ltx25_assets(model_root: Path, selected_paths: Iterable[str]) -> tuple[list[dict[str, object]], int]:
    selected = [Path(value).expanduser() for value in selected_paths]
    statuses = inspect_ltx25_assets(model_root, (str(item) for item in selected))
    imported = 0
    for source in selected:
        asset = _BY_NAME.get(source.name)
        if asset is None or not source.is_file() or source.suffix.lower() != ".safetensors":
            continue
        destination = model_root / asset.destination_category / asset.filename
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        imported += 1
    post_import = inspect_ltx25_assets(model_root)
    protected = {str(item["filename"]): item for item in statuses if item["state"] in {"duplicate", "unknown", "wrong_filename", "wrong_destination"}}
    return [protected.get(str(item["filename"]), item) for item in post_import] + [item for item in statuses if item["state"] == "unknown"], imported
