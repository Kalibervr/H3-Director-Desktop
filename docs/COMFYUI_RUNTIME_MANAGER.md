# ComfyUI Runtime Manager Foundation

The Runtime Manager is deliberately advisory in this milestone. It reports the
managed loopback runtime configuration and will later own version discovery, backup
manifests, update transactions, rollback, custom-node compatibility and profile
matrix checks. Updates and rollback must remain H3-owned-runtime-only, preserve shared
models, and use a confirmed snapshot; no live runtime update or rollback is performed
by this foundation.

Every post-update compatibility report is profile-specific. Static node/model checks
do not replace a real render verification and must not mark a profile runtime-verified.

## User flow

The Models & Workflows runtime tab can check current settings and show guarded update
or rollback plans. The intended sequence is Check Update → Backup → Update → Validate
Profiles → Accept or Rollback. In this release, Update and Rollback intentionally
remain dry-run only and cannot mutate the working ComfyUI installation.
