# Builds dist\HomeFlix-Setup.exe : a fully offline installer that bundles Python + dependencies.
# Requires: Inno Setup 6 (winget install JRSoftware.InnoSetup), and installer\embed.zip
# (python-X.Y.Z-embed-amd64.zip from python.org, matching the version in .venv).
$ErrorActionPreference = "Stop"
$root  = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $PSScriptRoot "stage"
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory "$stage\python" | Out-Null

# 1. Embedded Python runtime (official, signed python.org binaries)
Expand-Archive (Join-Path $PSScriptRoot "embed.zip") "$stage\python"
$pth = Get-ChildItem "$stage\python\python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem "$stage\python\python*.zip" | Select-Object -First 1).Name
Set-Content $pth.FullName "$zipName`n.`nLib\site-packages`n..`nimport site"

# 2. Dependencies, installed into the embedded runtime
& $venvPy -m pip install --quiet --target "$stage\python\Lib\site-packages" -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE) { throw "pip failed" }

# 3. The app itself
Copy-Item (Join-Path $root "main.py"), (Join-Path $root "config.py") $stage
Copy-Item (Join-Path $root "static") "$stage\static" -Recurse

# 3b. ffmpeg for thumbnails (kept in installer\ffmpeg_src; the app looks in <app>\ffmpeg\)
$ffSrc = Join-Path $PSScriptRoot "ffmpeg_src"
if (-not (Test-Path "$ffSrc\ffmpeg.exe")) { throw "installer\ffmpeg_src\ffmpeg.exe missing (copy it from an ffmpeg build, e.g. winget install Gyan.FFmpeg)" }
Copy-Item $ffSrc "$stage\ffmpeg" -Recurse

# 4. Compile the installer
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Run: winget install JRSoftware.InnoSetup" }
& $iscc (Join-Path $PSScriptRoot "HomeFlix.iss")
if ($LASTEXITCODE) { throw "ISCC failed" }
Write-Host "`nBuilt: $root\dist\HomeFlix-Setup.exe" -ForegroundColor Green
