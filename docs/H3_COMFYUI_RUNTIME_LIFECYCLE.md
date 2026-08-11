# Local ComfyUI runtime lifecycle

H3 Director stores only local runtime configuration in its app state: ComfyUI root,
Python executable, loopback port, and auto-launch choice. It does not search disks,
download ComfyUI, install Python/CUDA, or download models.

## Verified managed launch

For the verified local installation, H3 launches:

```text
<root>\\.venv\\Scripts\\python.exe -s main.py --listen 127.0.0.1 --port <configured-port> --feature-flag enable_telemetry=false --feature-flag show_signin_button=false --extra-model-paths-config <configured-shared-model-paths> --input-directory <configured-input> --output-directory <configured-output>
```

The working directory is `<root>`. The child has hidden Windows process creation
and captured stdout/stderr. The launcher does not open the ComfyUI browser UI.
It preserves the parent environment and sets `PYTHONIOENCODING=utf-8` and
`PYTHONUTF8=1`, preventing Windows console-codepage failures during startup.

The lifecycle core is pure Node (`electron/comfyui-runtime-core.ts`); the
Electron module is a thin persistence/backend-auth adapter. The verified local
installation uses the configured ComfyUI root and `.venv\\Scripts\\python.exe`
with the existing shared model-path configuration. It does not copy or modify models.

## Readiness and safety

The configured port is always represented as `http://127.0.0.1:<port>`. H3 checks
the configured files before launch, then waits for the existing MiniMax workflow
compatibility probe: loopback reachability, required workflow nodes, models, and
the production telemetry restriction. A process is not ready merely because it has
a PID.

An existing compatible process is reused as external. A reachable process that
enables telemetry is incompatible and is never adopted, killed, or restarted.

## Ownership and shutdown

Only the `ChildProcess` started by H3 is owned. Stop, Restart, unexpected-exit
status, and app-exit cleanup apply only to that process. External ComfyUI processes
remain untouched. Diagnostics expose only lifecycle phase, PID, readiness result,
exit code, and a short safe error; raw prompts, node graphs, model paths, and large
logs are not shown.

## Limitations

This milestone supports a configured local installation only. It does not bundle
ComfyUI, manage model downloads, recover an in-flight render after restart, or
retry crashes automatically.

`build:fast --skip-python` is not a full Torch backend runtime; packaged Python
distribution remains a separate installer/packaging milestone.
