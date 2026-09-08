$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$destination = Join-Path $PSScriptRoot "..\desktop\JobFlow.Desktop\Assets\JobFlow.ico"
New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
$bitmap = [System.Drawing.Bitmap]::new(256, 256)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::FromArgb(22, 53, 47))
$white = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(247, 246, 242), 30)
$white.StartCap = $white.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
$graphics.DrawLines($white, [System.Drawing.Point[]]@(
    [System.Drawing.Point]::new(78, 70), [System.Drawing.Point]::new(160, 70),
    [System.Drawing.Point]::new(180, 90), [System.Drawing.Point]::new(180, 166),
    [System.Drawing.Point]::new(160, 186), [System.Drawing.Point]::new(98, 186),
    [System.Drawing.Point]::new(78, 166)
))
$gold = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(213, 169, 78))
$graphics.FillEllipse($gold, 69, 107, 36, 36)
$icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
$stream = [System.IO.File]::Create($destination)
$icon.Save($stream)
$stream.Dispose(); $icon.Dispose(); $gold.Dispose(); $white.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
Write-Host "Generated $destination"
