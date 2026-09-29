# COSMIC-2 Explorer - launch script
# Usage:
#   .\launch.ps1             # native window (pywebview)
#   .\launch.ps1 --browser   # force browser
#   .\launch.ps1 --no-window # server only

param(
    [switch]$browser,
    [switch]$nowindow,
    [int]$port = 0
)

$BackendDir = Join-Path $PSScriptRoot "backend"
$AppPy = Join-Path $BackendDir "app.py"

if (-not (Test-Path $AppPy)) {
    Write-Error "app.py not found at $AppPy"
    exit 1
}

# Build the argument list
$args = @()
if ($browser) { $args += "--browser" }
if ($nowindow) { $args += "--no-window" }
if ($port -ne 0) { $args += "--port", $port }

Write-Host "Starting COSMIC-2 Explorer..." -ForegroundColor Cyan
Write-Host "Backend: $BackendDir"

# Change to backend dir and launch
Set-Location $BackendDir
python app.py @args
