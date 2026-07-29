$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
}

& ".\.venv\Scripts\python.exe" app.py
