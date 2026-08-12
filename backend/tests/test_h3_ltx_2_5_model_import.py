from pathlib import Path

import pytest

from services.h3_ltx_2_5_model_import import (
    LTX_2_5_ASSETS,
    Ltx25ModelImportError,
    import_ltx25_assets,
    inspect_ltx25_assets,
    resolve_shared_model_root,
)


def config(tmp_path: Path, root: Path) -> Path:
    path = tmp_path / "shared_model_paths.yaml"
    path.write_text(f"comfy.desktop:\n  base_path: '{root.as_posix()}'\n", encoding="utf-8")
    return path


def test_manifest_has_exact_verified_required_assets() -> None:
    assert [asset.filename for asset in LTX_2_5_ASSETS[:5]] == [
        "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
        "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
        "gemma4_e2b_it_bf16.safetensors",
        "ltx-2.5-video-vae-bf16.safetensors",
        "ltx-2.5-audio-vae-bf16.safetensors",
    ]
    assert all(asset.required for asset in LTX_2_5_ASSETS[:5])
    assert LTX_2_5_ASSETS[-1].required


def test_import_copies_exact_file_to_configured_category_and_preserves_source(tmp_path: Path) -> None:
    root = tmp_path / "models"; source = tmp_path / LTX_2_5_ASSETS[0].filename
    source.write_bytes(b"official-download")
    result, imported = import_ltx25_assets(resolve_shared_model_root(str(config(tmp_path, root))), [str(source)])
    destination = root / "diffusion_models" / source.name
    assert imported == 1 and source.read_bytes() == b"official-download" and destination.read_bytes() == b"official-download"
    assert next(item for item in result if item["filename"] == source.name)["state"] == "found"


def test_duplicate_unknown_and_executable_never_overwrite_or_import(tmp_path: Path) -> None:
    root = tmp_path / "models"; source = tmp_path / LTX_2_5_ASSETS[0].filename; source.write_bytes(b"source")
    destination = root / "diffusion_models" / source.name; destination.parent.mkdir(parents=True); destination.write_bytes(b"existing")
    executable = tmp_path / "untrusted.exe"; executable.write_bytes(b"no")
    result, imported = import_ltx25_assets(root, [str(source), str(executable)])
    assert imported == 0 and destination.read_bytes() == b"existing"
    assert next(item for item in result if item["filename"] == source.name)["state"] == "duplicate"
    assert next(item for item in result if item["filename"] == executable.name)["state"] == "unknown"


def test_invalid_shared_model_path_config_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"; config_path.write_text("no_root: true", encoding="utf-8")
    with pytest.raises(Ltx25ModelImportError):
        resolve_shared_model_root(str(config_path))


def test_missing_assets_reported_without_creating_directories(tmp_path: Path) -> None:
    root = tmp_path / "models"
    result = inspect_ltx25_assets(root)
    assert all(item["state"] == "missing" for item in result if item["required"])
    assert not root.exists()


def test_wrong_destination_and_wrong_filename_are_explicit(tmp_path: Path) -> None:
    root = tmp_path / "models"; asset = LTX_2_5_ASSETS[0]
    misplaced = root / "vae" / asset.filename; misplaced.parent.mkdir(parents=True); misplaced.write_bytes(b"x")
    malformed = tmp_path / "ltx-2.5-unverified.exe"; malformed.write_bytes(b"x")
    result = inspect_ltx25_assets(root, [str(malformed)])
    assert next(item for item in result if item["filename"] == asset.filename)["state"] == "wrong_destination"
    assert next(item for item in result if item["filename"] == malformed.name)["state"] == "wrong_filename"
