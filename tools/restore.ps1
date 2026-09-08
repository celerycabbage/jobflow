param([Parameter(Mandatory = $true)][string]$BackupDirectory)

$resolvedBackup = (Resolve-Path -LiteralPath $BackupDirectory).Path
$databaseFile = Join-Path $resolvedBackup "jobflow.sql"
$uploadDirectory = Join-Path $resolvedBackup "uploads"
if (-not (Test-Path -LiteralPath $databaseFile)) { throw "Missing $databaseFile" }

Get-Content -Raw -LiteralPath $databaseFile |
    docker compose exec -T mysql mysql -u root -plocal-root-password jobflow
if ($LASTEXITCODE -ne 0) { throw "MySQL restore failed" }

if (Test-Path -LiteralPath $uploadDirectory) {
    docker compose exec -T api sh -c "rm -rf /app/uploads/*"
    docker compose cp "$uploadDirectory\." api:/app/uploads
    if ($LASTEXITCODE -ne 0) { throw "Upload restore failed" }
}

Write-Host "Restore completed from $resolvedBackup"
