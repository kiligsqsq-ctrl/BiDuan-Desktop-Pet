$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

& ".\build_exe.ps1"
if ($LASTEXITCODE -ne 0) { throw "Application build failed." }

$candidates = @(
    "$PSScriptRoot\.tools\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $iscc) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $iscc = $command.Source }
}
if (-not $iscc) {
    throw "Inno Setup is required. Install Inno Setup 7, then run this script again."
}

& $iscc ".\installer\biduan.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

Write-Host ""
Write-Host "Release complete: release\BiDuan_Setup_0.4.2.exe"
