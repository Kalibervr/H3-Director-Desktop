import json
from pathlib import Path
import pytest
from services.h3_workflow_profiles import WorkflowProfileError, WorkflowProfileRegistry, validate_profile_package

def package(root: Path, ident: str = "safe_profile") -> Path:
    root.mkdir(); (root / "profile.json").write_text(json.dumps({"id": ident, "display_name": "Safe", "provider_family": "Local", "version": "1", "profile_schema_version": 1, "modes": [{"id": "image_to_video"}], "workflow": {"api": "workflow_api.json"}})); (root / "workflow_api.json").write_text("{}")
    return root

def test_valid_declarative_profile_installs_once(tmp_path: Path) -> None:
    source = package(tmp_path / "source"); registry = WorkflowProfileRegistry(tmp_path / "managed")
    assert registry.install(source).is_dir(); assert len(registry.list_installed()) == 1
    with pytest.raises(WorkflowProfileError): registry.install(source)

@pytest.mark.parametrize("name", ["run.py", "install.ps1"])
def test_rejects_executable_or_unsafe_profile_content(tmp_path: Path, name: str) -> None:
    source = package(tmp_path / "source"); (source / name).parent.mkdir(parents=True, exist_ok=True); (source / name).write_text("x")
    with pytest.raises(WorkflowProfileError): validate_profile_package(source)

def test_rejects_unknown_schema_and_missing_workflow(tmp_path: Path) -> None:
    source = package(tmp_path / "source"); data = json.loads((source / "profile.json").read_text()); data["profile_schema_version"] = 2; (source / "profile.json").write_text(json.dumps(data))
    with pytest.raises(WorkflowProfileError): validate_profile_package(source)

def test_rejects_workflow_path_traversal(tmp_path: Path) -> None:
    source = package(tmp_path / "source"); data = json.loads((source / "profile.json").read_text()); data["workflow"] = {"api": "../workflow_api.json"}; (source / "profile.json").write_text(json.dumps(data))
    with pytest.raises(WorkflowProfileError): validate_profile_package(source)
