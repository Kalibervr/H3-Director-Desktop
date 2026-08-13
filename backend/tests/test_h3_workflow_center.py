import json
from pathlib import Path
import pytest
from services.h3_workflow_center import WorkflowCenter, WorkflowCenterError, detect_format

def api(): return {"1": {"class_type": "KSampler", "inputs": {"seed": 1, "width": 640, "model_name": "model.safetensors"}}, "2": {"class_type": "CreateVideo", "inputs": {"images": ["1", 0]}}}

def test_import_api_and_validate(tmp_path: Path):
    source=tmp_path/'workflow.json'; source.write_text(json.dumps(api()), encoding='utf-8')
    center=WorkflowCenter(tmp_path/'managed'); entry=center.import_json(source)
    assert entry['status']=='imported' and Path(entry['source_workflow']).is_file()
    root=tmp_path/'models'; root.mkdir(); (root/'model.safetensors').write_bytes(b'x')
    result=center.validate(entry['id'], {'KSampler': {}, 'CreateVideo': {}}, [root])
    assert result['status']=='contract_verified' and result['runtime_verified'] is False

def test_ui_requires_api_export(tmp_path: Path):
    source=tmp_path/'ui.json'; source.write_text(json.dumps({'nodes': []}), encoding='utf-8')
    assert WorkflowCenter(tmp_path/'managed').import_json(source)['status']=='api_export_required'

def test_invalid_and_size_guard(tmp_path: Path):
    source=tmp_path/'bad.json'; source.write_text('[]', encoding='utf-8')
    with pytest.raises(WorkflowCenterError): WorkflowCenter(tmp_path/'managed').import_json(source)
    assert detect_format({'nodes': []})=='ui'
