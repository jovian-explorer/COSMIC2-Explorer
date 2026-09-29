# Update Desktop Shortcuts for COSMIC-2 Explorer
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$TargetExe = "C:\Users\kesha\Desktop\COSMIC2-Explorer\dist\COSMIC2-Explorer.exe"
$IconFile = "C:\Users\kesha\Desktop\COSMIC2-Explorer\dist\cosmic2.ico"
$WorkingDir = "C:\Users\kesha\Desktop\COSMIC2-Explorer\dist"

$ShortcutNames = @(
    "COSMIC-2 Explorer.lnk",
    "COSMIC2-Explorer - Shortcut.lnk"
)

foreach ($Name in $ShortcutNames) {
    $ShortcutPath = Join-Path $DesktopPath $Name
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetExe
    $Shortcut.WorkingDirectory = $WorkingDir
    $Shortcut.IconLocation = "$IconFile,0"
    $Shortcut.Description = "COSMIC-2 Explorer: Atmospheric Radio Occultation Analysis"
    $Shortcut.Save()
    Write-Host "[SHORTCUT] Updated: $ShortcutPath"
}
