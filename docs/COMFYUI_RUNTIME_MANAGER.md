# ComfyUI Runtime Manager

The Runtime Manager has a local transaction service for an explicitly configured,
H3-owned ComfyUI root. It inventories git/custom-node state, creates a transactional
snapshot, checks a git-backed runtime's configured `origin/HEAD`, and can stage a
restore. Electron remains the sole process owner: callers must stop/start/probe the
owned loopback runtime around these filesystem transactions.

Every post-update compatibility report is profile-specific. Static node/model checks
do not replace a real render verification and must not mark a profile runtime-verified.

## User flow

The intended sequence is Check Update → verify ownership/no active render → complete
backup → official update → start → `/object_info` → profile matrix → accept or
rollback. Snapshot copies exclude `models`, `input`, and `output`; restores preserve
those live directories. Dirty runtime or custom-node repositories block the default
update path. Custom nodes are inventoried but never bulk-updated.

## Controlled real-world status

Automated fixture coverage validates snapshot/restore safety and failure guards. No
real update, dependency reconciliation, rollback, or custom-node update has been run
against the working user runtime in this milestone. The UI therefore presents update
and rollback as guarded maintenance actions pending a controlled Electron-owned
transaction binding and real-world validation.
