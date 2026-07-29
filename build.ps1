$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\pyinstaller.exe" `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "MemoryLane" `
    --add-data "index.html;." `
    --add-data "app.js;." `
    --add-data "style.css;." `
    --collect-all imageio_ffmpeg `
    app.py

$portable = Join-Path $project "dist\MemoryLane-Portable"
New-Item -ItemType Directory -Force -Path $portable | Out-Null
Copy-Item ".\dist\MemoryLane.exe" $portable -Force
Copy-Item ".\LICENSE" $portable -Force
Copy-Item ".\README.md" $portable -Force
Compress-Archive -Path "$portable\*" -DestinationPath ".\dist\MemoryLane-Windows-Portable.zip" -Force

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "  dist\MemoryLane-Windows-Portable.zip"
