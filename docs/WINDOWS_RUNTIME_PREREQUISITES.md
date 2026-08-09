# Windows runtime prerequisites

## FFmpeg and ffprobe

Windows builds do not rely on `PATH`. `scripts/prepare-media-tools.ps1` downloads the pinned Gyan essentials archive for FFmpeg 9.0, verifies its published SHA-256 (`ffb866303866995734849995027533b9756971215e8c55ef408073628cdc27a2`) before extraction, and installs `ffmpeg.exe` and `ffprobe.exe` together under `imageio_ffmpeg/binaries`. `scripts/prepare-python.ps1` invokes this provisioning step for the packaged Python environment. Development environments can invoke it with `-DestinationRoot backend\.venv`.

Gyan's Windows download is linked from FFmpeg's download page. The selected static essentials build is GPLv3, so distribution must retain the applicable GPL notices and corresponding-source offer/source availability. The project must review `LICENSE.txt` and `NOTICES.md` before shipping this bundle; the repository's Apache-2.0 license does not replace the binary's GPL obligations.

At Electron startup, both executables are resolved from the local bundle and checked with `-version`. A missing or non-runnable executable is logged as an explicit media capability blocker.

## Microsoft Visual C++ Redistributable

`resources/installer.nsh` makes `resources/vc_redist.x64.exe` a compile-time input for the full Windows NSIS installer. It checks the merged v14 x64 runtime registry key and silently runs the bundled installer with `/install /quiet /norestart` when the runtime is absent or its build is below 31000. Therefore the full NSIS build is intentionally blocked while that file is absent; `pnpm build:fast` remains usable because it creates an unpacked app without compiling the NSIS installer.

The only accepted upstream source is Microsoft's current x64 v14 Redistributable permalink: `https://aka.ms/vc14/vc_redist.x64.exe`. That permalink changes over time, so release preparation must:

1. download it from Microsoft over TLS;
2. record the exact file/product version;
3. verify a valid Microsoft Authenticode signature;
4. compute and record SHA-256 in release provenance;
5. pin that version and hash for reproducible release builds;
6. confirm redistribution rights under the Visual Studio license used by the release producer.

Microsoft states that redistribution is limited to licensed Visual Studio users and governed by the applicable Microsoft Software License Terms. Until those release-owner licensing and provenance checks are completed, no `vc_redist.x64.exe` is added to Git and the full NSIS build remains blocked.
