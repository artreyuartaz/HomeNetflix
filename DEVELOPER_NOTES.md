# Home Flix - Developer Notes

Local Netflix-style launcher for home videos. FastAPI backend + one-page Tailwind UI. Videos open in **VLC** (never in the browser). Watch state is stored in `history.json`.

## File map

| File | Purpose |
|---|---|
| `main.py` | FastAPI app: scanner, history read/write, VLC launcher, API endpoints, startup (single-instance check, opens browser) |
| `config.py` | All settings, loaded from `.env`. Relative paths resolve against the project folder |
| `static/index.html` | The UI: grouped grid, search, watched filter, parent/subfolder dropdowns, Rescan, Quit |
| `static/tailwind.js` | Tailwind v3.4.17 bundled locally so the UI works offline |
| `.env` / `.env.example` | User settings (see below) |
| `history.json` | Created automatically; watch data |
| `run.bat` | Dev launcher: finds Python, builds `.venv`, starts the app |
| `create_shortcut.ps1` | Dev desktop shortcut (silent start); `-Startup` also adds it to Windows startup |
| `installer/HomeFlix.iss` | Inno Setup script for the installer |
| `installer/build_installer.ps1` | Builds `dist\HomeFlix-Setup.exe` |
| `installer/embed.zip` | python.org embeddable Python (must match the `.venv` version) |

## Settings (`.env`)

`VIDEOS_DIR` (drive/folder, absolute or relative), `VLC_PATH` (blank = auto-detect), `VLC_FULLSCREEN` (default true), `OPEN_BROWSER` (default true), `HISTORY_FILE`, `HOST` (default 127.0.0.1), `PORT` (default 8000), `ROOT_GROUP_NAME` (label for loose files, default "Movies").
Changes need an app restart.

## Thumbnails (ffmpeg)

- `GET /api/thumb?id=<video id>` returns a 480px-wide JPEG, generated on first request and cached in `thumbs/` (key = hash of id + file size + mtime, so edited files regenerate). Frame is taken at `THUMB_SECONDS` (default 5s), falling back to the first frame for very short clips. A failed file leaves a `.none` marker so it isn't retried on every page load. At most 2 ffmpeg processes run at once.
- `/api/library` returns `thumbnails: true/false`; the UI only requests images when ffmpeg was found, and falls back to the gradient card if an image fails.
- ffmpeg lookup order: `FFMPEG_PATH` in `.env`, `<app>\ffmpeg\ffmpeg.exe`, PATH, then the WinGet packages folder. Settings: `FFMPEG_PATH`, `THUMBNAILS`, `THUMBS_DIR`, `THUMB_SECONDS`.
- The installer **bundles ffmpeg** (installer is ~74 MB). Source copy lives in `installer\ffmpeg_src\` (ffmpeg.exe from the Gyan full build 9.0.2 plus its LICENSE); `build_installer.ps1` copies it to `<app>\ffmpeg\`, which `find_ffmpeg()` checks before PATH. To update ffmpeg, replace the files in `ffmpeg_src`. Dev runs (no bundled copy) use PATH / WinGet.

## Data model

- Video ID = path relative to the videos folder, forward slashes (`Show/S1/ep1.mp4`). Moving a file changes its ID and loses its history.
- `history.json` entry per ID: `title`, `watched`, `date_watched` (ISO), `play_count`, `size_mb`.
- `/api/library` adds `group`, `parent` (first folder level, or "Movies" for loose files) and `child` (remaining subfolders) to each video.

## API

- `GET /api/library` - scan and return videos
- `POST /api/play {id}` - mark watched (written before VLC starts), then launch VLC
- `POST /api/watched {id, watched}` - manual toggle
- `POST /api/shutdown` - stop the server; localhost only

`resolve_video()` rejects any ID that resolves outside the videos folder. VLC is started with an argument list (no shell), so spaces in paths are safe.

## Run / test

- Dev: `run.bat`, or `.venv\Scripts\python.exe main.py`
- Backend test: use `fastapi.testclient.TestClient` with `main.launch_vlc` replaced by a stub, a temp `VIDEOS_DIR` and `HISTORY_FILE`, and `PYTHONPATH` set to the project folder. Use a non-default `PORT` for live tests so you don't clash with a running copy.

## Build the installer

1. Need Inno Setup 6 (`winget install JRSoftware.InnoSetup`) and `installer\embed.zip`.
2. Run `powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1`.
3. Output: `dist\HomeFlix-Setup.exe`. `installer\stage` is a temporary folder and can be deleted.

How the installer works:
- It bundles the embeddable Python plus dependencies installed into `python\Lib\site-packages`. Shortcuts run `{app}\python\pythonw.exe main.py` with the app folder as working directory.
- The `._pth` file must list `.`, `Lib\site-packages`, `..` and `import site`, or the embedded Python won't find the app or its packages.
- It installs per user (`%LOCALAPPDATA%\Programs\Home Flix`) so `.env` and `history.json` stay editable without admin rights. Neither file is in `[Files]`, so upgrades and uninstalls keep them.
- The wizard asks for the video folder and writes `.env` (first install only).
- Silent test: `HomeFlix-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR=<temp> /TASKS=`, then `<temp>\unins000.exe /VERYSILENT`.

## Gotchas

- **Do not package with PyInstaller.** Windows Defender quarantined the exe as `Trojan:Win32/Bearfoos.A!ml` (a false positive for unsigned PyInstaller builds). The embeddable-Python approach avoids it.
- Never copy `.venv` between PCs; `run.bat` recreates it.
- The Microsoft Store `python` stub is not a real Python; `run.bat` detects this.
- Restarting: the shortcut only opens the browser if the server is already running. Use the Quit button, or `Stop-Process -Name pythonw`.
- Under `pythonw` there is no console; output goes to `homeflix.log` in the app folder.
- `config.py` contains a frozen-exe branch (`RESOURCE_DIR`) left from the abandoned PyInstaller attempt. It is harmless.
- The installed app needs VLC installed separately.

## Not yet tested manually

Installer wizard click-through, desktop/startup shortcut tasks, real VLC playback from an installed copy, and the parent/subfolder dropdowns in a browser.

## Ideas for later

Resume position, sorting options, "continue watching" row, TV-style next-episode launch.
