param(
    [string]$Version = "",
    [switch]$NoRestore,
    [switch]$PortableOnly,
    [string]$SigningThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) { $Version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION.txt") -Raw).Trim() }
$versionParts = [regex]::Matches($Version, '\d+') | Select-Object -First 3 | ForEach-Object Value
while ($versionParts.Count -lt 3) { $versionParts += '0' }
$numericVersion = ($versionParts -join '.') + '.0'
$env:DOTNET_CLI_HOME = Join-Path $projectRoot ".dotnet-cli"
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = "1"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$releaseRoot = Join-Path $projectRoot "release"
$releaseName = "Animus-Mod-Manager-$Version-win-x64"
$stage = Join-Path $releaseRoot $releaseName
$archive = Join-Path $releaseRoot "$releaseName.zip"
$cache = Join-Path $projectRoot ".release-cache"
$pythonArchive = Join-Path $cache "python-3.14.7-embed-amd64.zip"
$pythonUrl = "https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip"
$pythonSha256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"
$restoreOption = if ($NoRestore) { @("--no-restore") } else { @() }
New-Item -ItemType Directory -Force -Path $releaseRoot, $cache | Out-Null

$resolvedRelease = [IO.Path]::GetFullPath($releaseRoot)
$resolvedStage = [IO.Path]::GetFullPath($stage)
if (-not $resolvedStage.StartsWith($resolvedRelease + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe release staging path: $resolvedStage"
}
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

if (-not (Test-Path -LiteralPath $pythonArchive)) {
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonArchive
}
$actualPythonHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $pythonArchive).Hash.ToLowerInvariant()
if ($actualPythonHash -ne $pythonSha256) {
    throw "Python runtime checksum mismatch. Expected $pythonSha256, got $actualPythonHash."
}

$appOutput = $stage
dotnet publish (Join-Path $projectRoot "desktop\AnimusModManager.csproj") `
    -c Release -r win-x64 --self-contained false --nologo `
    $restoreOption `
    -p:Version=$Version -p:AssemblyVersion=$numericVersion -p:FileVersion=$numericVersion `
    -p:PublishSingleFile=false -p:DebugType=None -p:DebugSymbols=false `
    -o $appOutput
if ($LASTEXITCODE -ne 0) { throw "Animus manager publish failed with exit code $LASTEXITCODE." }

if ($SigningThumbprint) {
    & (Join-Path $projectRoot "sign-release.ps1") `
        -CertificateThumbprint $SigningThumbprint `
        -TimestampUrl $TimestampUrl `
        -Files @(
            (Join-Path $stage "AnimusModManager.exe")
        )
    if ($LASTEXITCODE -ne 0) { throw "Release executable signing failed." }
}

New-Item -ItemType Directory -Force -Path (Join-Path $stage "tools") | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "tools\Animus_loader") `
    -Destination (Join-Path $stage "tools\Animus_loader") -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot "tools\third_party") `
    -Destination (Join-Path $stage "tools\third_party") -Recurse
Get-ChildItem -LiteralPath (Join-Path $stage "tools") -Directory -Recurse -Force |
    Where-Object Name -eq "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $stage "tools") -File -Recurse -Filter "*.pyc" |
    Remove-Item -Force

$pythonRoot = Join-Path $stage "runtime\python"
New-Item -ItemType Directory -Force -Path $pythonRoot | Out-Null
Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonRoot -Force
$pythonStdlibArchive = Join-Path $pythonRoot "python314.zip"
$pythonStdlib = Join-Path $pythonRoot "Lib"
New-Item -ItemType Directory -Force -Path $pythonStdlib | Out-Null
Expand-Archive -LiteralPath $pythonStdlibArchive -DestinationPath $pythonStdlib -Force
Remove-Item -LiteralPath $pythonStdlibArchive -Force
$pth = Join-Path $pythonRoot "python314._pth"
@("Lib", "Lib\site-packages", ".", "..\..\tools") | Set-Content -LiteralPath $pth -Encoding ascii

# The embeddable Python archive contains only the standard library.  Outfit
# Workshop exports use PNG source textures, so the public build must also ship
# the native NumPy/Pillow encoder dependencies.  Archive support keeps py7zr as
# a fallback when the bundled 7-Zip executable cannot handle a file.
$dependencyPython = & py -3.14 -c "import sys; print(sys.executable)"
if ($LASTEXITCODE -ne 0 -or -not $dependencyPython) {
    throw "Python 3.14 with the packages in tools\requirements.txt is required to build the public runtime."
}
$dependencyPython = $dependencyPython.Trim()
$dependencySite = & $dependencyPython -c "import pathlib, site; print(next(p for p in site.getsitepackages() if (pathlib.Path(p) / 'numpy').is_dir()))"
if ($LASTEXITCODE -ne 0 -or -not $dependencySite) {
    throw "Could not locate the Python 3.14 site-packages directory."
}
$dependencySite = $dependencySite.Trim()
& $dependencyPython -c "import numpy, PIL, py7zr"
if ($LASTEXITCODE -ne 0) {
    throw "Missing public runtime dependencies. Run: py -3.14 -m pip install -r tools\requirements.txt"
}

$runtimeSite = Join-Path $pythonRoot "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $runtimeSite | Out-Null
$runtimeDependencyPatterns = @(
    "numpy", "numpy.libs", "numpy-*.dist-info",
    "PIL", "pillow-*.dist-info",
    "py7zr", "py7zr-*.dist-info",
    "brotli.py", "_brotli*.pyd", "brotli-*.dist-info",
    "inflate64", "inflate64-*.dist-info",
    "multivolumefile", "multivolumefile-*.dist-info",
    "psutil", "psutil-*.dist-info",
    "bcj", "pybcj-*.dist-info",
    "Cryptodome", "pycryptodomex-*.dist-info",
    "pyppmd", "pyppmd-*.dist-info",
    "texttable.py", "texttable-*.dist-info"
)
foreach ($pattern in $runtimeDependencyPatterns) {
    Get-ChildItem -LiteralPath $dependencySite -Filter $pattern -Force |
        Copy-Item -Destination $runtimeSite -Recurse -Force
}

# Runtime package test suites are not used by Animus.  NumPy's tests also ship
# compressed pickle fixtures; those become nested archives inside the public
# package and prevent Nexus from fully scanning it.
$dependencyTestDirectories = @(
    Get-ChildItem -LiteralPath $runtimeSite -Directory -Recurse -Force |
        Where-Object { $_.Name -in @("test", "tests") } |
        Sort-Object { $_.FullName.Length } -Descending
)
foreach ($testDirectory in $dependencyTestDirectories) {
    if (Test-Path -LiteralPath $testDirectory.FullName) {
        Remove-Item -LiteralPath $testDirectory.FullName -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $runtimeSite -File -Recurse -Force |
    Where-Object { $_.Extension -in @(".zip", ".7z", ".rar", ".tar", ".gz") } |
    Remove-Item -Force

# Validate imports using the exact embedded interpreter that will ship.
& (Join-Path $pythonRoot "python.exe") -c "import numpy, PIL, py7zr"
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Python runtime dependency validation failed."
}

foreach ($folder in @("mods\packages", "mods\installed", "mods\backups", "mods\textures\backups")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage $folder) | Out-Null
}

Copy-Item -LiteralPath (Join-Path $projectRoot "PUBLIC-BETA-README.md") `
    -Destination (Join-Path $stage "README.md")
Copy-Item -LiteralPath (Join-Path $projectRoot "CHANGELOG.md") -Destination $stage
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD-PARTY-NOTICES.md") -Destination $stage
Copy-Item -LiteralPath (Join-Path $projectRoot "NEXUS-SECURITY-NOTES.txt") -Destination $stage
$Version | Set-Content -LiteralPath (Join-Path $stage "VERSION.txt") -Encoding ascii

$hashLines = Get-ChildItem -LiteralPath $stage -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        # Windows PowerShell 5.1 runs on .NET Framework and does not provide
        # Path.GetRelativePath. The staging prefix is already validated above.
        $relative = ($_.FullName.Substring($resolvedStage.Length) -replace '^[\\/]+', '').Replace("\", "/")
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$hashLines | Set-Content -LiteralPath (Join-Path $stage "SHA256SUMS.txt") -Encoding ascii

Compress-Archive -LiteralPath $stage -DestinationPath $archive -CompressionLevel Optimal
$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
"$archiveHash  $(Split-Path -Leaf $archive)" |
    Set-Content -LiteralPath "$archive.sha256" -Encoding ascii

Write-Host "Public beta created: $archive"
Write-Host "SHA-256: $archiveHash"

# A numbered update is an installed-product upgrade by default. Always create
# the stable-AppId installer so existing-version detection and in-place data
# preservation cannot be accidentally omitted from a release.
if (-not $PortableOnly) {
    $installerArguments = @("-Version", $Version)
    if ($SigningThumbprint) {
        $installerArguments += @(
            "-SigningThumbprint", $SigningThumbprint,
            "-TimestampUrl", $TimestampUrl
        )
    }
    & (Join-Path $projectRoot "build-installer.ps1") @installerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Installer build failed with exit code $LASTEXITCODE."
    }
}
