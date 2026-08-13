from pathlib import Path
import pytest
from services.h3_runtime_manager import RuntimeManagerError, check_update, create_snapshot, detect_runtime, list_snapshots, restore_snapshot, rollback_plan, update_plan

def runtime_fixture(tmp_path: Path):
    root=tmp_path/'comfy'; root.mkdir(); (root/'main.py').write_text(''); (root/'version.py').write_text('__version__ = "test"'); (root/'models').mkdir(); (root/'models'/'large.bin').write_bytes(b'model'); (root/'custom_nodes').mkdir(); (root/'custom_nodes'/'node').mkdir()
    python=root/'python.exe'; python.write_text(''); return root, detect_runtime(root,python,'http://127.0.0.1:8190')

def test_snapshot_excludes_models_and_keeps_manifest(tmp_path: Path):
    root,runtime=runtime_fixture(tmp_path); snapshot=create_snapshot(runtime,tmp_path/'backups')
    manifest=Path(snapshot['manifest_path']); assert (manifest.parent/'runtime'/'main.py').is_file(); assert not (manifest.parent/'runtime'/'models').exists(); assert snapshot['shared_models_included'] is False; assert list_snapshots(tmp_path/'backups')[0]['id']==snapshot['id']

def test_external_and_dirty_are_rejected(tmp_path: Path):
    _,runtime=runtime_fixture(tmp_path)
    with pytest.raises(RuntimeManagerError): update_plan(runtime,False)
    runtime['dirty']=True
    with pytest.raises(RuntimeManagerError): update_plan(runtime,True)

def test_restore_preserves_current_runtime_and_models_untouched(tmp_path: Path):
    root,runtime=runtime_fixture(tmp_path); snapshot=create_snapshot(runtime,tmp_path/'backups'); (root/'main.py').write_text('new')
    result=restore_snapshot(runtime,Path(snapshot['manifest_path']),True)
    assert (root/'main.py').read_text()=='' and Path(result['previous_runtime']).is_dir(); assert (root/'models'/'large.bin').read_bytes()==b'model'

def test_update_check_and_snapshot_rejection(tmp_path: Path):
    _,runtime=runtime_fixture(tmp_path); assert check_update(runtime)['status']=='manual_update_required'
    with pytest.raises(RuntimeManagerError): rollback_plan(tmp_path/'nope.json',True)
