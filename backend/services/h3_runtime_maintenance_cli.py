"""Internal Electron-only bridge to the tested runtime maintenance service.

This CLI is never exposed by the HTTP API. Electron supplies the persisted managed
runtime configuration after verifying process ownership.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from h3_runtime_manager import check_update, create_snapshot, detect_runtime, list_snapshots, perform_official_git_update, restore_snapshot

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=('inspect','snapshot','update','restore')); parser.add_argument('--root',required=True); parser.add_argument('--python',required=True); parser.add_argument('--endpoint',required=True); parser.add_argument('--backup-root',required=True); parser.add_argument('--shared-model-config'); parser.add_argument('--snapshot-id')
    args=parser.parse_args(); runtime=detect_runtime(Path(args.root),Path(args.python),args.endpoint,args.shared_model_config); backups=Path(args.backup_root)
    if args.action=='inspect': result={'runtime':runtime,'update':check_update(runtime),'snapshots':list_snapshots(backups)}
    elif args.action=='snapshot': result=create_snapshot(runtime,backups)
    elif args.action=='update': result=perform_official_git_update(runtime,True)
    else:
        if not args.snapshot_id or '/' in args.snapshot_id or '\\' in args.snapshot_id: raise ValueError('Invalid snapshot selection.')
        result=restore_snapshot(runtime,backups/args.snapshot_id/'manifest.json',True)
    print(json.dumps(result))
if __name__=='__main__': main()
