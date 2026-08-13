from pathlib import Path
import pytest
from services.h3_runtime_manager import backup_manifest, detect_runtime, update_plan, rollback_plan, RuntimeManagerError
def test_runtime_plans_and_manifest(tmp_path: Path):
    root=tmp_path/'comfy'; root.mkdir(); (root/'main.py').write_text(''); python=root/'python.exe'; python.write_text('')
    runtime=detect_runtime(root, python, 'http://127.0.0.1:8190')
    manifest=backup_manifest(tmp_path/'snapshots', runtime)
    assert update_plan(runtime, True)['dry_run'] and rollback_plan(manifest, True)['shared_models_modified'] is False
    with pytest.raises(RuntimeManagerError): update_plan(runtime, False)
