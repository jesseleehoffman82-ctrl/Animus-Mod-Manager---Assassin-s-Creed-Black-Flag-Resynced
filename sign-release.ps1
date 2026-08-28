param(
    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,

    [Parameter(Mandatory = $true)]
    [string[]]$Files,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$thumbprint = ($CertificateThumbprint -replace "\s", "").ToUpperInvariant()
$certificate = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Thumbprint -eq $thumbprint -and $_.NotAfter -gt (Get-Date) } |
    Select-Object -First 1
if (-not $certificate -or -not $certificate.HasPrivateKey) {
    throw "A valid CurrentUser code-signing certificate with private key was not found for thumbprint $thumbprint."
}
if ($certificate.Subject -eq $certificate.Issuer) {
    throw "Self-signed certificates are not accepted for public releases. Use a publicly trusted code-signing certificate."
}

$signToolCandidates = @(
    Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" `
        -Recurse -File -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
        Sort-Object FullName -Descending |
        Select-Object -ExpandProperty FullName
)
$signTool = $signToolCandidates | Select-Object -First 1
if (-not $signTool) {
    throw "Windows SDK SignTool was not found."
}

foreach ($file in $Files) {
    $resolved = [IO.Path]::GetFullPath($file)
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Signing target does not exist: $resolved"
    }
    & $signTool sign /sha1 $thumbprint /s My /fd SHA256 /tr $TimestampUrl /td SHA256 /v $resolved
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $resolved (exit code $LASTEXITCODE)."
    }
    & $signTool verify /pa /v $resolved
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed for $resolved (exit code $LASTEXITCODE)."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $resolved
    if ($signature.Status -ne "Valid") {
        throw "Windows does not trust the completed signature for ${resolved}: $($signature.StatusMessage)"
    }
}

Write-Host "Signed and verified $($Files.Count) release file(s)."
