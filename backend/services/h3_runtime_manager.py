"""Safe, local ComfyUI maintenance transactions.

The Electron lifecycle layer remains the sole process owner.  This service only
operates on an explicitly configured, H3-owned runtime directory and is designed
to be driven through injected stop/start/probe callbacks.
"""
from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

class RuntimeManagerError(ValueError): pass
_EXCLUDED = {"models", "output", "input", ".git", "__pycache__"}

def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding='utf-8'); os.replace(tmp,path)
def _run(args: list[str], cwd: Path) -> str | None:
    try:
        result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=20,check=False)
        return result.stdout.strip() if result.returncode==0 else None
    except (OSError, subprocess.TimeoutExpired): return None
def _read_version(root: Path) -> str | None:
    for candidate in (root/'comfyui_version.py',root/'version.py'):
        if candidate.is_file():
            for line in candidate.read_text(encoding='utf-8',errors='ignore').splitlines():
                if '__version__' in line and '=' in line:return line.split('=',1)[1].strip().strip('"\'')
    return None
def inventory_custom_nodes(root: Path) -> list[dict[str, Any]]:
    result=[]; directory=root/'custom_nodes'
    if not directory.is_dir(): return result
    for item in sorted(directory.iterdir()):
        if not item.is_dir() or item.name.startswith('.'): continue
        result.append({'name':item.name,'path':str(item),'git_revision':_run(['git','rev-parse','HEAD'],item),'dirty':bool(_run(['git','status','--porcelain'],item)),'repository':_run(['git','config','--get','remote.origin.url'],item)})
    return result
def detect_runtime(root: Path, python: Path, endpoint: str, shared_model_config: str | None=None) -> dict[str, Any]:
    root=root.resolve(); python=python.resolve(); revision=_run(['git','rev-parse','HEAD'],root); dirty=bool(_run(['git','status','--porcelain'],root))
    return {'root':str(root),'python':str(python),'endpoint':endpoint,'main_py':(root/'main.py').is_file(),'python_exists':python.is_file(),'shared_model_config':shared_model_config,'version':_read_version(root),'git_revision':revision,'git_backed':revision is not None,'dirty':dirty,'custom_nodes':inventory_custom_nodes(root),'managed_only':True}
def check_update(runtime: dict[str, Any]) -> dict[str, Any]:
    root=Path(str(runtime['root']))
    if not runtime.get('git_backed'): return {'status':'manual_update_required','current_revision':runtime.get('git_revision'),'available_revision':None,'message':'This runtime is not git-backed; no supported official update mechanism was detected.'}
    remote=_run(['git','ls-remote','origin','HEAD'],root)
    target=remote.split()[0] if remote else None
    return {'status':'update_available' if target and target!=runtime.get('git_revision') else 'up_to_date' if target else 'check_failed','current_revision':runtime.get('git_revision'),'available_revision':target,'source':'origin/HEAD (configured official runtime remote)','compatibility':'Compatibility requires validation'}
def _copy_runtime(source: Path, destination: Path) -> None:
    if destination.exists(): raise RuntimeManagerError('Snapshot destination already exists.')
    def ignore(directory: str, names: list[str]) -> set[str]: return {n for n in names if n in _EXCLUDED}
    shutil.copytree(source,destination,ignore=ignore,copy_function=shutil.copy2)
def create_snapshot(runtime: dict[str, Any], backup_root: Path) -> dict[str, Any]:
    root=Path(str(runtime['root'])).resolve()
    if not root.is_dir() or not (root/'main.py').is_file(): raise RuntimeManagerError('Configured managed ComfyUI runtime is invalid.')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); target=backup_root.resolve()/stamp; staging=backup_root.resolve()/(stamp+'.partial')
    if staging.exists(): shutil.rmtree(staging)
    try:
        _copy_runtime(root, staging/'runtime')
        manifest={'schema_version':2,'id':stamp,'created_at':stamp,'status':'complete','runtime':runtime,'runtime_copy':str(target/'runtime'),'shared_models_included':False,'excluded_directories':sorted(_EXCLUDED)}
        (staging/'runtime').parent.mkdir(parents=True,exist_ok=True); shutil.move(str(staging),str(target)); _write(target/'manifest.json',manifest)
        return manifest | {'manifest_path':str(target/'manifest.json'),'size_bytes':sum(p.stat().st_size for p in target.rglob('*') if p.is_file())}
    except Exception as exc:
        if staging.exists(): shutil.rmtree(staging)
        raise RuntimeManagerError(f'Rollback snapshot failed; update was not started: {exc}') from exc
def list_snapshots(backup_root: Path) -> list[dict[str, Any]]:
    result=[]
    for file in sorted(backup_root.glob('*/manifest.json'),reverse=True):
        try:
            value=json.loads(file.read_text(encoding='utf-8')); value['manifest_path']=str(file); value['size_bytes']=sum(p.stat().st_size for p in file.parent.rglob('*') if p.is_file()); result.append(value)
        except (OSError,json.JSONDecodeError): continue
    return result
def update_plan(runtime: dict[str, Any], owned: bool) -> dict[str, Any]:
    if not owned: raise RuntimeManagerError('Only an H3-managed ComfyUI runtime can be updated.')
    if runtime.get('dirty'): raise RuntimeManagerError('Local modifications detected in the managed runtime. Update is blocked by default.')
    return {'dry_run':False,'steps':['verify no active render','stop owned runtime','create complete rollback snapshot','git fetch/pull configured official remote','reconcile only required dependencies','restart','query object_info','validate built-in profiles'],'shared_models_modified':False}
def perform_official_git_update(runtime: dict[str, Any], owned: bool) -> dict[str, Any]:
    """Run only a fast-forward update of the configured runtime origin after shutdown."""
    update_plan(runtime, owned)
    root=Path(str(runtime['root']))
    if not runtime.get('git_backed'): raise RuntimeManagerError('No supported official git updater is available for this runtime.')
    if _run(['git','fetch','origin'],root) is None: raise RuntimeManagerError('Official runtime update fetch failed; rollback snapshot remains available.')
    old=runtime.get('git_revision')
    if _run(['git','merge','--ff-only','FETCH_HEAD'],root) is None: raise RuntimeManagerError('Official runtime update could not fast-forward; local runtime was not overwritten.')
    return {'status':'updated_pending_restart','old_revision':old,'new_revision':_run(['git','rev-parse','HEAD'],root),'source':'origin/HEAD','dependencies_changed':False}
def rollback_plan(snapshot: Path, owned: bool) -> dict[str, Any]:
    if not owned: raise RuntimeManagerError('Only an H3-managed ComfyUI runtime can be rolled back.')
    if not snapshot.is_file(): raise RuntimeManagerError('Selected rollback manifest does not exist.')
    return {'dry_run':False,'snapshot':str(snapshot.resolve()),'steps':['verify no active render','stop owned runtime','stage restored runtime','atomic runtime swap','restart','validate profiles'],'shared_models_modified':False}
def restore_snapshot(runtime: dict[str, Any], manifest_path: Path, owned: bool) -> dict[str, Any]:
    rollback_plan(manifest_path,owned); manifest=json.loads(manifest_path.read_text(encoding='utf-8')); source=Path(manifest['runtime_copy'])
    root=Path(str(runtime['root'])).resolve(); staged=root.with_name(root.name+'.restore.partial'); prior=root.with_name(root.name+'.before-restore')
    if not source.is_dir() or not (source/'main.py').is_file(): raise RuntimeManagerError('Snapshot runtime copy is incomplete.')
    if staged.exists(): shutil.rmtree(staged)
    _copy_runtime(source,staged)
    try:
        if prior.exists(): raise RuntimeManagerError('A prior runtime preservation directory exists; manual review is required.')
        root.rename(prior); staged.rename(root)
        # Snapshot intentionally excludes shared/heavy model and I/O directories. Preserve
        # those live directories by moving them back into the restored runtime unchanged.
        for name in _EXCLUDED - {'.git', '__pycache__'}:
            old = prior / name
            if old.exists() and not (root / name).exists(): shutil.move(str(old), str(root / name))
    except Exception as exc:
        if not root.exists() and prior.exists(): prior.rename(root)
        raise RuntimeManagerError(f'Runtime restore failed safely: {exc}') from exc
    return {'status':'restored_pending_start','previous_runtime':str(prior),'restored_runtime':str(root),'shared_models_modified':False}
