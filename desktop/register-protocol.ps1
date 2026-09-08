[CmdletBinding(SupportsShouldProcess)]
param([string]$ExecutablePath = "")

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
    $packagedExecutable = Join-Path $PSScriptRoot "JobFlow.Desktop.exe"
    $buildExecutable = Join-Path $PSScriptRoot "JobFlow.Desktop\bin\Release\net8.0-windows7.0\win-x64\publish\JobFlow.Desktop.exe"
    $ExecutablePath = if (Test-Path -LiteralPath $packagedExecutable) {
        $packagedExecutable
    } else {
        $buildExecutable
    }
}

$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
if (-not $PSCmdlet.ShouldProcess($resolvedExecutable, "Register jobflow:// protocol")) {
    return
}

$protocolRoot = "HKCU:\Software\Classes\jobflow"
New-Item -Path $protocolRoot -Force | Out-Null
Set-ItemProperty -Path $protocolRoot -Name "(default)" -Value "URL:JobFlow Protocol"
Set-ItemProperty -Path $protocolRoot -Name "URL Protocol" -Value ""
$commandKey = New-Item -Path "$protocolRoot\shell\open\command" -Force
Set-ItemProperty -Path $commandKey.PSPath -Name "(default)" -Value "`"$resolvedExecutable`" `"%1`""
Write-Host "Registered jobflow:// for $resolvedExecutable"
