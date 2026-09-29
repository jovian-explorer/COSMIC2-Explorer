$ErrorActionPreference = "Stop"

# 1. Run from the project itself (ensuring we are in the correct directory)
$projectDir = $PSScriptRoot
Set-Location $projectDir

Write-Host "[BUILD] Starting"

# 4. Execute PyInstaller synchronously in the foreground
# 5. Wait for PyInstaller to completely exit
# 6. Capture the actual exit code
# 10. Never start PyInstaller through an Antigravity background task
# 11. Never use Start-Job, Start-ThreadJob, background jobs...
Write-Host "[BUILD] PyInstaller running"

# By using Start-Process -Wait -NoNewWindow -PassThru, we run synchronously and can get the exit code
$proc = Start-Process -FilePath "python" -ArgumentList "-m", "PyInstaller", "--clean", ".\build\app.spec", "--noconfirm" -Wait -NoNewWindow -PassThru
$exitCode = $proc.ExitCode

Write-Host "[BUILD] PyInstaller exit code: $exitCode"

# 7. Return a non-zero PowerShell exit code if packaging fails
if ($exitCode -ne 0) {
    exit $exitCode
}

# 9. Locate and report the resulting executable
$exePath = Join-Path $projectDir "dist\COSMIC2-Explorer.exe"
if (Test-Path $exePath) {
    Write-Host "[BUILD] Executable: $exePath"
    $exeSize = (Get-Item $exePath).Length
    $sizeMB = [math]::Round($exeSize / 1MB, 2)
    Write-Host "[BUILD] Size: ${sizeMB} MB"
} else {
    Write-Host "[BUILD] Executable not found at $exePath"
    exit 1
}

Write-Host "[BUILD] COMPLETE"
