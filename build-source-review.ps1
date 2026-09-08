param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) { $Version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION.txt") -Raw).Trim() }
$releaseRoot = Join-Path $projectRoot "release"
$publicVersion = if ($Version -match '-beta$') { $Version -replace '-beta$', '' } else { $Version }
$sourceName = "Animus-Mod-Manager-$publicVersion-Source"
$stage = Join-Path $releaseRoot $sourceName
$archive = Join-Path $releaseRoot "$sourceName.zip"

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
$resolvedRelease = [IO.Path]::GetFullPath($releaseRoot)
$resolvedStage = [IO.Path]::GetFullPath($stage)
if (-not $resolvedStage.StartsWith(
        $resolvedRelease + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe source staging path: $resolvedStage"
}

if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
if (Test-Path -LiteralPath "$archive.sha256") { Remove-Item -LiteralPath "$archive.sha256" -Force }

New-Item -ItemType Directory -Force -Path $stage | Out-Null

foreach ($directory in @(
    "desktop",
    "desktop\assets",
    "tools",
    "tools\Animus_loader",
    "tools\Animus_loader\web",
    "tools\Animus_loader\web\assets",
    "tools\Animus_loader\web\icons"
)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage $directory) | Out-Null
}

Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\AnimusModManager.csproj") -Destination (Join-Path $stage "desktop")
Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\Program.cs") -Destination (Join-Path $stage "desktop")
Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\StartupSplashForm.cs") -Destination (Join-Path $stage "desktop")
Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\assets\animus.ico") -Destination (Join-Path $stage "desktop\assets")

Get-ChildItem -LiteralPath (Join-Path $projectRoot "tools\Animus_loader") -File -Filter "*.py" |
    Copy-Item -Destination (Join-Path $stage "tools\Animus_loader")
Get-ChildItem -LiteralPath (Join-Path $projectRoot "tools\Animus_loader\web") -File |
    Copy-Item -Destination (Join-Path $stage "tools\Animus_loader\web")
Copy-Item -Path (Join-Path $projectRoot "tools\Animus_loader\web\assets\*") `
    -Destination (Join-Path $stage "tools\Animus_loader\web\assets")
Copy-Item -Path (Join-Path $projectRoot "tools\Animus_loader\web\icons\*") `
    -Destination (Join-Path $stage "tools\Animus_loader\web\icons")
Copy-Item -LiteralPath (Join-Path $projectRoot "tools\requirements.txt") -Destination (Join-Path $stage "tools")
Get-ChildItem -LiteralPath (Join-Path $projectRoot "tools") -File -Filter "test_*.py" |
    Copy-Item -Destination (Join-Path $stage "tools")

foreach ($document in @(
    "CHANGELOG.md",
    "build-public-beta.ps1",
    "build-nexus-clean.ps1",
    "build-source-review.ps1",
    "sign-release.ps1",
    "SOURCE-CODE.txt",
    "REVIEW-NOTES.md",
    "GAME-COMPATIBILITY.md",
    "PUBLIC-BETA-README.md",
    "NEXUS-PORTABLE-README.md",
    "NEXUS-SECURITY-NOTES.txt",
    "SOURCE-BUILD.md",
    "DEVELOPMENT-NOTES.txt",
    "THIRD-PARTY-NOTICES.md",
    "NEXUS-PAGE-DESCRIPTION.md"
)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $document) -Destination $stage
}
Copy-Item -LiteralPath (Join-Path $projectRoot "SOURCE-BUILD.md") `
    -Destination (Join-Path $stage "BUILD-INSTRUCTIONS.txt")
$Version | Set-Content -LiteralPath (Join-Path $stage "VERSION.txt") -Encoding ascii

$blocked = @(
    Get-ChildItem -LiteralPath $stage -File -Recurse -Force |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(
            ".exe", ".dll", ".pyd", ".pyc", ".zip", ".7z", ".rar", ".tar", ".gz",
            ".bat", ".cmd", ".vbs", ".hta"
        ) }
)
if ($blocked.Count) {
    throw "Source review package contains compiled files, scripts or nested archives: $($blocked.FullName -join ', ')"
}

Compress-Archive -LiteralPath $stage -DestinationPath $archive -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $(Split-Path -Leaf $archive)" |
    Set-Content -LiteralPath "$archive.sha256" -Encoding ascii

Write-Host "Source review package created: $archive"
Write-Host "SHA-256: $hash"
Write-Host "Compiled executables/DLLs: 0; nested archives: 0"
