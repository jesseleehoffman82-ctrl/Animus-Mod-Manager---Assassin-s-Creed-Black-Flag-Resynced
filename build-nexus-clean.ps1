param(
    [string]$Version = "",
    [switch]$RequireTrustedSignature
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) { $Version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION.txt") -Raw).Trim() }
$releaseRoot = Join-Path $projectRoot "release"
$sourceName = "Animus-Mod-Manager-$Version-win-x64"
$source = Join-Path $releaseRoot $sourceName
$publicVersion = if ($Version -match '-beta$') { $Version -replace '-beta$', '' } else { $Version }
$cleanName = "Animus-Mod-Manager-$publicVersion"
$clean = Join-Path $releaseRoot $cleanName
$archive = Join-Path $releaseRoot "$cleanName.zip"

if (-not (Test-Path -LiteralPath $source)) {
    throw "Public release staging folder is missing: $source"
}

$resolvedRelease = [IO.Path]::GetFullPath($releaseRoot)
$resolvedClean = [IO.Path]::GetFullPath($clean)
if (-not $resolvedClean.StartsWith(
        $resolvedRelease + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe Nexus staging path: $resolvedClean"
}

if (Test-Path -LiteralPath $clean) {
    Remove-Item -LiteralPath $clean -Recurse -Force
}
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
if (Test-Path -LiteralPath "$archive.sha256") {
    Remove-Item -LiteralPath "$archive.sha256" -Force
}

Copy-Item -LiteralPath $source -Destination $clean -Recurse

# The Nexus package launches the native app directly. Remove optional wrappers,
# crash helpers, alternate interpreters, and retired Python/Tkinter frontends.
$removeRelative = @(
    "createdump.exe",
    "runtime\python\pythonw.exe",
    "tools\Animus_loader\api.py",
    "tools\Animus_loader\cli.py",
    "tools\Animus_loader\gui.py",
    "tools\Animus_loader\webapp.py",
    "tools\Animus_loader\native_dialog.ps1",
    "README.md",
    "NEXUS-SECURITY-NOTES.txt",
    "SHA256SUMS.txt"
)
foreach ($relative in $removeRelative) {
    $target = Join-Path $clean $relative
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

# Remove scripts and archives inherited from third-party runtime test/support
# folders. JavaScript under web/ is the actual local interface and is retained.
$blockedExtensions = @(".bat", ".cmd", ".ps1", ".vbs", ".hta")
Get-ChildItem -LiteralPath $clean -File -Recurse -Force |
    Where-Object { $_.Extension.ToLowerInvariant() -in $blockedExtensions } |
    Remove-Item -Force

$archiveExtensions = @(".zip", ".7z", ".rar", ".tar", ".gz")
Get-ChildItem -LiteralPath $clean -File -Recurse -Force |
    Where-Object { $_.Extension.ToLowerInvariant() -in $archiveExtensions } |
    Remove-Item -Force

Copy-Item -LiteralPath (Join-Path $projectRoot "NEXUS-PORTABLE-README.md") `
    -Destination (Join-Path $clean "README.md")
Copy-Item -LiteralPath (Join-Path $projectRoot "SOURCE-CODE.txt") `
    -Destination (Join-Path $clean "SOURCE-CODE.txt")

$allowedExecutables = @(
    "AnimusModManager.exe",
    "runtime\python\python.exe",
    "tools\third_party\7zip\7z.exe",
    "tools\third_party\directxtex\texconv.exe"
)
$actualExecutables = @(
    Get-ChildItem -LiteralPath $clean -File -Recurse -Filter "*.exe" |
        ForEach-Object { [IO.Path]::GetRelativePath($clean, $_.FullName) }
)
$unexpectedExecutables = @($actualExecutables | Where-Object { $_ -notin $allowedExecutables })
$missingExecutables = @($allowedExecutables | Where-Object { $_ -notin $actualExecutables })
if ($unexpectedExecutables.Count -or $missingExecutables.Count) {
    throw "Nexus executable allow-list failed. Unexpected: $($unexpectedExecutables -join ', '); Missing: $($missingExecutables -join ', ')"
}

$authoredExecutables = @(
    (Join-Path $clean "AnimusModManager.exe")
)
foreach ($authoredExecutable in $authoredExecutables) {
    $signature = Get-AuthenticodeSignature -LiteralPath $authoredExecutable
    if ($signature.Status -ne "Valid" -and $RequireTrustedSignature) {
        throw "A Nexus application executable is not trusted ($($signature.Status)): $authoredExecutable. Build the public release with -SigningThumbprint first."
    }
    if ($RequireTrustedSignature -and
        ($null -eq $signature.SignerCertificate -or
         $signature.SignerCertificate.Subject -eq $signature.SignerCertificate.Issuer)) {
        throw "Nexus application executables must use a publicly trusted certificate; self-signed signatures are rejected."
    }
}

$blockedFiles = @(
    Get-ChildItem -LiteralPath $clean -File -Recurse |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in ($blockedExtensions + $archiveExtensions)
        }
)
if ($blockedFiles.Count) {
    throw "Blocked scripts or nested archives remain in the Nexus package."
}

$userModFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $clean "mods") -File -Recurse -ErrorAction SilentlyContinue
)
if ($userModFiles.Count) {
    throw "Nexus package contains managed user files; refusing to publish."
}

# Nexus public applications must never ship a user's personal credentials or
# the retired authentication/download implementation. Keep this check close to
# packaging so a future regression cannot silently reach an upload archive.
$applicationSourceExtensions = @(".py", ".js", ".html", ".cs")
$legacyNexusPatterns = @(
    "NEXUS_API_KEY",
    "nexus_key.json",
    "sso.nexusmods.com",
    '"apikey"',
    "urlretrieve(",
    "latest_file("
)
$legacyNexusHits = @()
Get-ChildItem -LiteralPath $clean -File -Recurse -Force |
    Where-Object { $_.Extension.ToLowerInvariant() -in $applicationSourceExtensions } |
    ForEach-Object {
        $sourceFile = $_
        foreach ($pattern in $legacyNexusPatterns) {
            if (Select-String -LiteralPath $sourceFile.FullName -SimpleMatch -Pattern $pattern -Quiet) {
                $legacyNexusHits += "$([IO.Path]::GetRelativePath($clean, $sourceFile.FullName)): $pattern"
            }
        }
    }
if ($legacyNexusHits.Count) {
    throw "Legacy Nexus authentication/download code remains: $($legacyNexusHits -join '; ')"
}

$python = Join-Path $clean "runtime\python\python.exe"
& $python -c "import numpy, PIL, py7zr; import Animus_loader.desktop_rpc"
if ($LASTEXITCODE -ne 0) {
    throw "Clean packaged backend validation failed."
}

$hashLines = Get-ChildItem -LiteralPath $clean -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($clean, $_.FullName).Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$hashLines | Set-Content -LiteralPath (Join-Path $clean "SHA256SUMS.txt") -Encoding ascii

# Preserve one top-level application folder in the ZIP. This prevents users
# from accidentally scattering the self-contained runtime across Downloads or
# the Desktop when they extract the archive.
Compress-Archive -LiteralPath $clean -DestinationPath $archive -CompressionLevel Optimal
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$archiveHash  $(Split-Path -Leaf $archive)" |
    Set-Content -LiteralPath "$archive.sha256" -Encoding ascii

Write-Host "Nexus-clean package created: $archive"
Write-Host "SHA-256: $archiveHash"
Write-Host "Executables: $($actualExecutables.Count); scripts: 0; nested archives: 0; user mod files: 0"
