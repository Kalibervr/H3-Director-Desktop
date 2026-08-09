# Provision a verified Windows FFmpeg/ffprobe pair into imageio_ffmpeg's local
# binaries directory. The archive is pinned and checked before any executable is
# extracted or run.

param(
    [string]$DestinationRoot = "backend\.venv"
)

$ErrorActionPreference = "Stop"
$FfmpegVersion = "9.0"
$ArchiveUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-$FfmpegVersion-essentials_build.7z"
$ExpectedSha256 = "ffb866303866995734849995027533b9756971215e8c55ef408073628cdc27a2"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$ResolvedDestinationRoot = if ([IO.Path]::IsPathRooted($DestinationRoot)) {
    $DestinationRoot
} else {
    Join-Path $ProjectDir $DestinationRoot
}
$Destination = Join-Path $ResolvedDestinationRoot "Lib\site-packages\imageio_ffmpeg\binaries"
$TempDir = Join-Path $env:TEMP "h3-director-ffmpeg-$FfmpegVersion"
$ArchivePath = Join-Path $TempDir "ffmpeg-essentials.7z"
$ExtractPath = Join-Path $TempDir "extracted"

try {
    if (Test-Path $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $TempDir | Out-Null

    Write-Host "Downloading pinned FFmpeg $FfmpegVersion essentials archive..."
    $CurlExe = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($CurlExe) {
        & $CurlExe.Source --fail --location --retry 3 --output $ArchivePath $ArchiveUrl
        if ($LASTEXITCODE -ne 0) { throw "FFmpeg archive download failed" }
    } else {
        Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing
    }
    $ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "FFmpeg archive SHA-256 mismatch. Expected $ExpectedSha256, got $ActualSha256"
    }

    New-Item -ItemType Directory -Path $ExtractPath | Out-Null
    & tar -xf $ArchivePath -C $ExtractPath
    if ($LASTEXITCODE -ne 0) { throw "Verified FFmpeg archive extraction failed" }
    $FfmpegSource = Get-ChildItem -Path $ExtractPath -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    $FfprobeSource = Get-ChildItem -Path $ExtractPath -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
    if (-not $FfmpegSource -or -not $FfprobeSource) {
        throw "Verified archive did not contain both ffmpeg.exe and ffprobe.exe"
    }

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Copy-Item -LiteralPath $FfmpegSource.FullName -Destination (Join-Path $Destination "ffmpeg.exe") -Force
    Copy-Item -LiteralPath $FfprobeSource.FullName -Destination (Join-Path $Destination "ffprobe.exe") -Force

    $FfmpegOutput = & (Join-Path $Destination "ffmpeg.exe") -version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Bundled ffmpeg capability check failed" }
    Write-Host ($FfmpegOutput | Select-Object -First 1)
    $FfprobeOutput = & (Join-Path $Destination "ffprobe.exe") -version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Bundled ffprobe capability check failed" }
    Write-Host ($FfprobeOutput | Select-Object -First 1)

    Write-Host "Verified media tools installed in: $Destination" -ForegroundColor Green
} finally {
    if (Test-Path $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
}
