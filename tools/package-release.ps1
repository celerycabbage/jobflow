param(
    [string]$OutputDirectory = "$PSScriptRoot\..\artifacts",
    [string]$ApiImage = "jobflow-api:latest",
    [string]$Version = "0.3.0"
)

$resolvedRoot = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$extensionFiles = @(
    "manifest.json", "background.js", "popup.html", "popup.css", "popup.js"
) | ForEach-Object { Join-Path "$resolvedRoot\extension" $_ }
$extensionArchive = Join-Path $OutputDirectory "jobflow-extension.zip"
Compress-Archive -LiteralPath $extensionFiles -DestinationPath $extensionArchive -Force

$pythonCandidates = @(
    (Join-Path $resolvedRoot "backend\.venv\Scripts\python.exe"),
    (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$python = $pythonCandidates | Select-Object -First 1
if (-not $python) { throw "Python 3.12 with the backend dev dependencies is required to build the embedded server." }
$serverBuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jobflow-server-build-" + [guid]::NewGuid().ToString("N"))
& $python -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $serverBuildRoot "dist") `
    --workpath (Join-Path $serverBuildRoot "work") `
    "$resolvedRoot\backend\desktop-server.spec"
if ($LASTEXITCODE -ne 0) { throw "Embedded server build failed" }
$serverPublish = Join-Path $serverBuildRoot "dist\JobFlow.Server"
if (-not (Test-Path -LiteralPath (Join-Path $serverPublish "JobFlow.Server.exe"))) {
    throw "Embedded server executable was not created"
}

dotnet restore "$resolvedRoot\desktop\JobFlow.Desktop\JobFlow.Desktop.csproj" `
    --runtime win-x64 --configfile "$resolvedRoot\desktop\NuGet.Config"
if ($LASTEXITCODE -ne 0) { throw "Desktop restore failed" }
dotnet publish "$resolvedRoot\desktop\JobFlow.Desktop\JobFlow.Desktop.csproj" `
    --configuration Release --runtime win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:DebugType=None -p:DebugSymbols=false --no-restore
if ($LASTEXITCODE -ne 0) { throw "Desktop publish failed" }
$desktopPublish = "$resolvedRoot\desktop\JobFlow.Desktop\bin\Release\net8.0-windows7.0\win-x64\publish"
$desktopFiles = @(
    (Join-Path $desktopPublish "JobFlow.Desktop.exe"),
    (Join-Path "$resolvedRoot\desktop" "README.md"),
    (Join-Path "$resolvedRoot\desktop" "register-protocol.ps1")
)
$runtimeCompose = Get-Content -LiteralPath "$resolvedRoot\desktop\runtime\docker-compose.yml" -Raw
New-Item -ItemType Directory -Path (Join-Path $desktopPublish "runtime") -Force | Out-Null
$runtimeCompose.Replace("__JOBFLOW_API_IMAGE__", $ApiImage) |
    Set-Content -LiteralPath (Join-Path $desktopPublish "runtime\docker-compose.yml") -Encoding utf8
New-Item -ItemType Directory -Path (Join-Path $desktopPublish "server") -Force | Out-Null
Copy-Item -Path (Join-Path $serverPublish "*") -Destination (Join-Path $desktopPublish "server") -Recurse -Force

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $isccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $isccPath = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($isccPath) { $iscc = Get-Item -LiteralPath $isccPath }
}
if ($iscc) {
    $isccExecutable = if ($iscc.Source) { $iscc.Source } else { $iscc.FullName }
    $installerArgs = @("$resolvedRoot\desktop\installer.iss", "/DMyAppVersion=$Version", "/DPublishDir=$desktopPublish", "/DOutputDir=$OutputDirectory")
    if ($env:JOBFLOW_SIGN_COMMAND) {
        $installerArgs += "/DSignCommand=1"
        $installerArgs += "/Sjobflowsign=$env:JOBFLOW_SIGN_COMMAND"
    }
    & $isccExecutable @installerArgs
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
}

$releaseStage = Join-Path ([System.IO.Path]::GetTempPath()) ("jobflow-release-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path (Join-Path $releaseStage "runtime") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $releaseStage "server") -Force | Out-Null
Copy-Item -LiteralPath $desktopFiles -Destination $releaseStage
Copy-Item -LiteralPath (Join-Path $desktopPublish "runtime\docker-compose.yml") -Destination (Join-Path $releaseStage "runtime")
Copy-Item -Path (Join-Path $desktopPublish "server\*") -Destination (Join-Path $releaseStage "server") -Recurse -Force
Compress-Archive -Path (Join-Path $releaseStage "*") `
    -DestinationPath (Join-Path $OutputDirectory "jobflow-desktop-win-x64.zip") -Force

Get-ChildItem -LiteralPath $OutputDirectory | Where-Object {
    $_.Extension -eq ".zip" -or $_.Name -eq "jobflow-desktop-setup-win-x64.exe"
} | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)" | Set-Content -LiteralPath "$($_.FullName).sha256" -Encoding ascii
}

Get-ChildItem -LiteralPath $OutputDirectory | Select-Object Name, Length
