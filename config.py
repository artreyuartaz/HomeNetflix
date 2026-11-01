"""Central configuration. Override any value in a .env file next to this file."""
import os
from pathlib import Path

from dotenv import load_dotenv

import sys

if getattr(sys, "frozen", False):  # packaged .exe
    # Editable files (.env, history.json) live next to the exe; bundled assets are unpacked elsewhere.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
    RESOURCE_DIR = PROJECT_ROOT
load_dotenv(PROJECT_ROOT / ".env")


def _resolve(value: str) -> Path:
    """Relative paths are resolved against the project folder, so the project is portable."""
    p = Path(value).expanduser()
    return (p if p.is_absolute() else PROJECT_ROOT / p).resolve()


# Folder containing your videos (relative to this project, or absolute e.g. D:\Movies)
VIDEOS_DIR = _resolve(os.getenv("VIDEOS_DIR", "videos"))

# Watch history database
HISTORY_FILE = _resolve(os.getenv("HISTORY_FILE", "history.json"))

# Full path to the VLC executable. Leave empty to auto-detect.
VLC_PATH = os.getenv("VLC_PATH", "").strip().strip('"')

# Thumbnails (needs ffmpeg). FFMPEG_PATH blank = auto-detect. Set THUMBNAILS=false to disable.
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "").strip().strip('"')
THUMBNAILS = os.getenv("THUMBNAILS", "true").lower() not in ("0", "false", "no")
THUMBS_DIR = _resolve(os.getenv("THUMBS_DIR", "thumbs"))
THUMB_SECONDS = float(os.getenv("THUMB_SECONDS", "5"))  # moment of the video to capture

# Start VLC in fullscreen (set VLC_FULLSCREEN=false to disable)
VLC_FULLSCREEN = os.getenv("VLC_FULLSCREEN", "true").lower() not in ("0", "false", "no")

# Open the browser automatically when the app starts
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "true").lower() not in ("0", "false", "no")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi"}

# 127.0.0.1 = only this PC. Use 0.0.0.0 to open it to your home network
# (note: VLC would still launch on the PC running the server).
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Label for videos placed directly in the videos folder (not in a subfolder)
ROOT_GROUP_NAME = os.getenv("ROOT_GROUP_NAME", "Movies")
