param([string]$EnvironmentFile = "$PSScriptRoot\..\.env")

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path
$templatePath = Join-Path $resolvedRoot ".env.example"
$targetPath = [System.IO.Path]::GetFullPath($EnvironmentFile)

if (-not (Test-Path -LiteralPath $templatePath)) { throw "Missing .env.example" }
if (-not (Test-Path -LiteralPath $targetPath)) {
    Copy-Item -LiteralPath $templatePath -Destination $targetPath
}

$content = [System.IO.File]::ReadAllText($targetPath)
$match = [regex]::Match($content, "(?m)^JWT_SECRET=(.*)$")
if (-not $match.Success) { throw "JWT_SECRET is missing from $targetPath" }

$currentSecret = $match.Groups[1].Value.Trim()
if ([string]::IsNullOrWhiteSpace($currentSecret) -or $currentSecret -match "^(replace-|local-development-|change-me)") {
    $bytes = New-Object byte[] 32
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    $secret = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    $content = [regex]::Replace($content, "(?m)^JWT_SECRET=.*$", "JWT_SECRET=$secret")
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($targetPath, $content, $utf8)
    Write-Host "Created local configuration with a random JWT secret: $targetPath"
} else {
    Write-Host "Existing local configuration preserved: $targetPath"
}
