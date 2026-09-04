param(
    [string]$Version = "",
    [string]$SigningThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) { $Version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION.txt") -Raw).Trim() }
$scriptPath = Join-Path $projectRoot "installer\AnimusModManager.iss"
$generatedScriptPath = Join-Path $projectRoot "installer\AnimusModManager.generated.iss"
$releaseRoot = Join-Path $projectRoot "release"
$portableRoot = Join-Path $releaseRoot "Animus-Mod-Manager-$Version-win-x64"
$displayVersion = if ($Version -match '-beta$') { $Version -replace '-beta$', '-Beta' } else { $Version }
$versionParts = [regex]::Matches($Version, '\d+') | Select-Object -First 3 | ForEach-Object Value
while ($versionParts.Count -lt 3) { $versionParts += '0' }
$numericVersion = ($versionParts -join '.') + '.0'
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

# Generate the installer metadata from VERSION.txt/the -Version argument so a
# release number can never drift away from the UI footer or package name.
$installerSource = [IO.File]::ReadAllText($scriptPath)

# The AppId and install directory are deliberately permanent. Every release
# must upgrade the existing installation in place instead of creating a second
# application entry or a side-by-side program folder.
$stableAppId = 'AppId={{C23FBEF0-088A-4500-9259-663C0D0ECA59}'
$stableInstallDir = 'DefaultDirName={localappdata}\Programs\Animus Mod Manager'
if (-not $installerSource.Contains($stableAppId)) {
    throw "Installer AppId changed. Keep the stable AppId so updates overwrite the existing installation."
}
if (-not $installerSource.Contains($stableInstallDir)) {
    throw "Installer directory changed. Keep the stable directory so updates overwrite the existing installation."
}

$installerSource = [regex]::Replace($installerSource, '#define MyAppVersion ".*?"', "#define MyAppVersion `"$Version`"")
$installerSource = [regex]::Replace($installerSource, '#define MySourceDir ".*?"', "#define MySourceDir `"..\release\Animus-Mod-Manager-$Version-win-x64`"")
$installerSource = [regex]::Replace($installerSource, 'VersionInfoVersion=.*', "VersionInfoVersion=$numericVersion")
$installerSource = [regex]::Replace($installerSource, 'VersionInfoProductVersion=.*', "VersionInfoProductVersion=$numericVersion")
$installerSource = [regex]::Replace($installerSource, 'OutputBaseFilename=.*', "OutputBaseFilename=Animus-Mod-Manager-$displayVersion-Setup")
[IO.File]::WriteAllText($generatedScriptPath, $installerSource, [Text.UTF8Encoding]::new($false))

if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
try {
    # Inno prints one line per bundled runtime file (thousands of lines). Keep
    # release automation responsive when this script is called by the main
    # public-build workflow.
    & $compiler --quiet-progress $generatedScriptPath
    if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed with exit code $LASTEXITCODE." }
}
finally {
    if (Test-Path -LiteralPath $generatedScriptPath) { Remove-Item -LiteralPath $generatedScriptPath -Force }
}
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
