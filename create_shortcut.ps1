# Creates a "Home Flix" desktop shortcut that starts the app silently (no console window)
# and opens the browser. Run once:  right-click > Run with PowerShell
# Add -Startup to also start the server automatically when you log in to Windows.
param([switch]$Startup)

$root = $PSScriptRoot
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
    Write-Host "Run run.bat once first so the .venv is created." -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

function New-Shortcut($path, $args_) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
    $s.TargetPath = $pyw
    $s.Arguments = $args_
    $s.WorkingDirectory = $root
    $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"
    $s.Description = "Home Flix"
    $s.Save()
}

$desktop = [Environment]::GetFolderPath("Desktop")
New-Shortcut (Join-Path $desktop "Home Flix.lnk") "`"$root\main.py`""
Write-Host "Created shortcut on Desktop: Home Flix"

if ($Startup) {
    $startup = [Environment]::GetFolderPath("Startup")
    New-Shortcut (Join-Path $startup "Home Flix.lnk") "`"$root\main.py`""
    Write-Host "Added to Windows Startup"
}
Read-Host "Done. Press Enter to close"
