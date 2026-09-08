param([string]$Destination = "$PSScriptRoot\..\backups")

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDirectory = Join-Path $Destination $timestamp
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null

$databaseFile = Join-Path $backupDirectory "jobflow.sql"
docker compose exec -T mysql mysqldump -u root -plocal-root-password --single-transaction jobflow |
    Set-Content -LiteralPath $databaseFile -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "MySQL backup failed" }

$uploadDirectory = Join-Path $backupDirectory "uploads"
docker compose cp api:/app/uploads $uploadDirectory
if ($LASTEXITCODE -ne 0) { throw "Upload backup failed" }

Write-Host "Backup created at $backupDirectory"
