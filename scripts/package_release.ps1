[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$version = "v0.1.0"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseDir = Join-Path $repoRoot "dist\release_v0.1.0"
$stagingDir = Join-Path $releaseDir ".portable-staging"
$installer = Join-Path $repoRoot "app\src-tauri\target\release\bundle\nsis\DocForge Desktop_0.1.0_x64-setup.exe"
$desktopExe = Join-Path $repoRoot "app\src-tauri\target\release\docforge-desktop.exe"
$sidecar = Join-Path $repoRoot "app\src-tauri\binaries\docforge-engine-x86_64-pc-windows-msvc.exe"
$portableZip = Join-Path $releaseDir "DocForge-v0.1.0-Windows-x64-Portable.zip"
$sumsFile = Join-Path $releaseDir "SHA256SUMS.txt"

foreach ($required in @($installer, $desktopExe, $sidecar)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "No se encontró el artefacto requerido: $required"
    }
}

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
if (Test-Path -LiteralPath $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $stagingDir "binaries") -Force | Out-Null

try {
    Copy-Item -LiteralPath $installer -Destination (Join-Path $releaseDir (Split-Path $installer -Leaf)) -Force
    Copy-Item -LiteralPath $desktopExe -Destination (Join-Path $stagingDir "docforge-desktop.exe") -Force
    Copy-Item -LiteralPath $sidecar -Destination (Join-Path $stagingDir "binaries\docforge-engine-x86_64-pc-windows-msvc.exe") -Force

    $releaseResources = Join-Path $repoRoot "app\src-tauri\target\release\resources"
    if (Test-Path -LiteralPath $releaseResources -PathType Container) {
        Copy-Item -LiteralPath $releaseResources -Destination (Join-Path $stagingDir "resources") -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\README_PORTABLE.txt") -Destination (Join-Path $stagingDir "README.txt") -Force

    if (Test-Path -LiteralPath $portableZip) {
        Remove-Item -LiteralPath $portableZip -Force
    }
    Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $portableZip -CompressionLevel Optimal -Force

    $installerName = Split-Path $installer -Leaf
    $sumLines = @(
        "{0} *{1}" -f ((Get-FileHash -LiteralPath (Join-Path $releaseDir $installerName) -Algorithm SHA256).Hash.ToLowerInvariant()), $installerName
        "{0} *{1}" -f ((Get-FileHash -LiteralPath $portableZip -Algorithm SHA256).Hash.ToLowerInvariant()), (Split-Path $portableZip -Leaf)
    )
    Set-Content -LiteralPath $sumsFile -Value $sumLines -Encoding ascii
    Write-Host "Release v0.1.0 generado en $releaseDir"
    Write-Host "  - $installerName"
    Write-Host "  - $(Split-Path $portableZip -Leaf)"
    Write-Host "  - SHA256SUMS.txt"
}
finally {
    if (Test-Path -LiteralPath $stagingDir) {
        Remove-Item -LiteralPath $stagingDir -Recurse -Force
    }
}
