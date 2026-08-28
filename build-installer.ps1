param(
    [string]$Version = "0.1.2-beta",
    [string]$SigningThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $projectRoot "installer\AnimusModManager.iss"
$releaseRoot = Join-Path $projectRoot "release"
$portableRoot = Join-Path $releaseRoot "Animus-Mod-Manager-$Version-win-x64"
$displayVersion = if ($Version -match '-beta$') { $Version -replace '-beta$', '-Beta' } else { $Version }
$output = Join-Path $releaseRoot "Animus-Mod-Manager-$displayVersion-Setup.exe"
$localCompiler = Join-Path $projectRoot ".release-tools\Inno Setup 7\ISCC.exe"
$compilerCandidates = @(
    $localCompiler,
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

if (-not (Test-Path -LiteralPath $portableRoot)) {
    throw "Portable release not found: $portableRoot. Run build-public-beta.ps1 first."
}
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    throw "Inno Setup compiler was not found. Install Inno Setup 7 or place it under .release-tools."
}

if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
& $compiler $scriptPath
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $output)) { throw "Installer output was not created: $output" }

if ($SigningThumbprint) {
    & (Join-Path $projectRoot "sign-release.ps1") `
        -CertificateThumbprint $SigningThumbprint `
        -TimestampUrl $TimestampUrl `
        -Files @($output)
    if ($LASTEXITCODE -ne 0) { throw "Installer signing failed." }
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash.ToLowerInvariant()
"$hash  $(Split-Path -Leaf $output)" |
    Set-Content -LiteralPath "$output.sha256" -Encoding ascii
Write-Host "Installer created: $output"
Write-Host "SHA-256: $hash"
