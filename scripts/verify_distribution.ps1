[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseDir = Join-Path $repoRoot "dist\release_v0.1.0"
$portableZip = Join-Path $releaseDir "DocForge-v0.1.0-Windows-x64-Portable.zip"
$sumsFile = Join-Path $releaseDir "SHA256SUMS.txt"
$verifyDir = Join-Path $releaseDir ".distribution-verify"

foreach ($required in @($portableZip, $sumsFile)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Falta un artefacto de distribución: $required"
    }
}

if (Test-Path -LiteralPath $verifyDir) {
    Remove-Item -LiteralPath $verifyDir -Recurse -Force
}
New-Item -ItemType Directory -Path $verifyDir -Force | Out-Null

try {
    Expand-Archive -LiteralPath $portableZip -DestinationPath $verifyDir -Force
    $mainExe = Join-Path $verifyDir "docforge-desktop.exe"
    $sidecarExe = Join-Path $verifyDir "binaries\docforge-engine-x86_64-pc-windows-msvc.exe"
    foreach ($required in @($mainExe, $sidecarExe)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "El ZIP no contiene el archivo esperado: $required"
        }
    }

    & $sidecarExe --help *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "El sidecar congelado devolvió exit code $LASTEXITCODE al ejecutar --help"
    }

    $sumEntries = Get-Content -LiteralPath $sumsFile
    if ($sumEntries.Count -lt 2) {
        throw "SHA256SUMS.txt no contiene los dos artefactos esperados"
    }
    $zipHash = (Get-FileHash -LiteralPath $portableZip -Algorithm SHA256).Hash.ToLowerInvariant()
    $zipName = Split-Path $portableZip -Leaf
    if (-not ($sumEntries | Where-Object { $_ -eq "$zipHash *$zipName" })) {
        throw "El checksum del ZIP no coincide con SHA256SUMS.txt"
    }
    Write-Host "Distribución verificada: ZIP íntegro y sidecar --help correcto."
}
finally {
    if (Test-Path -LiteralPath $verifyDir) {
        Remove-Item -LiteralPath $verifyDir -Recurse -Force
    }
}
