# Workflow Import & Validation Center

Imported ComfyUI workflows are untrusted declarative data. H3 Director copies the
original JSON unchanged into app-owned storage, records SHA-256, and creates a new
revision for changed content. A UI graph is never treated as executable: it remains
`api_export_required` until a genuine ComfyUI API export is supplied.

API imports are analyzed conservatively for node classes, literal/link inputs, model
filenames, output/audio/image capabilities and suggested control mappings. Suggestions
include confidence and are not semantic guarantees. Imported workflows are disabled;
static validation can reach `contract_verified`, never `runtime_verified`. Promotion
requires a future explicit validation render.

## User flow

**Models & Workflows** is separate from the Director workspace. Import a workflow,
resolve its API-export/model/node requirements, run static validation, then use a
future guarded validation render before enabling it. The current UI exposes analysis
and validation details but never promotes or executes an imported workflow.

Validation compares required class types with the configured loopback ComfyUI
`/object_info` response and looks for exact model filenames only in supplied shared
model roots. No custom node code, shell command, model executable, credential, or
network request is accepted from an imported workflow.
