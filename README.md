# Home Flix

A local Netflix-style launcher for your home videos. Browse a poster grid in your browser; videos play in **VLC** or, if you choose, right in the browser. Watch status is stored in `history.json`. Works fully offline.

## Features

- Grid grouped by folder, with search, watched filter and parent/child folder dropdowns
- Thumbnails generated with ffmpeg and cached in `thumbs/`
- Watched marker with date; rewatched videos show a count ("2 watched")
- Dropdown choices (folder, subfolder, filter, play mode) are remembered in `prefs.json`
- "Play in browser" mode: MKV/MPG/AVI etc. are converted on the fly by ffmpeg; progress is saved so you can continue where you left off. A video counts as watched once 90% of it has actually been played (`WATCH_PERCENT` in `.env`)
- Windows installer (bundles its own Python and ffmpeg, no setup needed)

## Structure

```
├── main.py              # FastAPI backend (scanner, history, thumbnails, VLC launcher)
├── config.py            # Settings, read from .env
├── static/              # UI (index.html + locally bundled Tailwind)
├── installer/           # Inno Setup script + build_installer.ps1
├── run.bat              # Windows dev launcher
├── create_shortcut.ps1  # Desktop/startup shortcut (dev)
├── .env.example         # Copy to .env and edit
└── DEVELOPER_NOTES.md
```

## Run from source

1. Install [Python 3.10+](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/). For thumbnails, install ffmpeg (`winget install Gyan.FFmpeg`).
2. Copy `.env.example` to `.env` and set `VIDEOS_DIR` to your videos folder.
3. Double-click `run.bat` (or `pip install -r requirements.txt` then `python main.py`).
4. Open <http://127.0.0.1:8000> (it opens automatically).

Subfolders of the videos folder become rows; files directly in it appear under "Movies".

## Build the Windows installer

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php), the python.org *embeddable* Python zip saved as `installer/embed.zip`, and `ffmpeg.exe` (+ its LICENSE) placed in `installer/ffmpeg_src/`. These large files are not in the repo.

```
powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1
```

Output: `dist/HomeFlix-Setup.exe`.

## Moving to another PC

Install with the installer, or copy the folder. Copy `history.json` (and `prefs.json`) to keep watch history; its keys are paths relative to the videos folder, so they stay valid if the layout inside is unchanged. If VLC isn't auto-detected, set `VLC_PATH` in `.env`.

## Notes

- The server binds to `127.0.0.1` by default.
- Video formats are listed in `VIDEO_EXTENSIONS` in `config.py`.
