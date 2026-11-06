import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import config

app = FastAPI(title="Home Netflix")
STATIC_DIR = config.RESOURCE_DIR / "static"
_lock = threading.Lock()


# ---------- history.json ----------

def load_history() -> dict:
    try:
        with open(config.HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_history(data: dict) -> None:
    tmp = config.HISTORY_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, config.HISTORY_FILE)  # atomic: never leaves a half-written file


# ---------- scanning ----------

def scan_videos() -> list[dict]:
    root = config.VIDEOS_DIR
    if not root.is_dir():
        return []
    history = load_history()
    items = []
    for path in sorted(root.rglob("*"), key=lambda p: str(p).lower()):
        if not path.is_file() or path.suffix.lower() not in config.VIDEO_EXTENSIONS:
            continue
        rel = path.relative_to(root)
        vid = rel.as_posix()  # stable, portable ID (same on any PC)
        parent = rel.parent.as_posix()
        entry = history.get(vid, {})
        items.append({
            "id": vid,
            "title": path.stem,
            "group": config.ROOT_GROUP_NAME if parent == "." else parent,
            # first folder level = parent; everything below it = child (e.g. "Show/Season 1")
            "parent": config.ROOT_GROUP_NAME if parent == "." else rel.parts[0],
            "child": "/".join(rel.parts[1:-1]),
            "extension": path.suffix.lower().lstrip("."),
            "size_mb": round(path.stat().st_size / 1_048_576, 1),
            "watched": bool(entry.get("watched")),
            "date_watched": entry.get("date_watched"),
            "play_count": entry.get("play_count", 0),
            "position": entry.get("position", 0),  # resume point (seconds) for browser playback
            "duration": entry.get("duration", 0),
        })
    return items


def resolve_video(video_id: str) -> Path:
    """Map an ID back to a file, refusing anything outside the videos folder."""
    root = config.VIDEOS_DIR
    path = (root / video_id).resolve()
    if root not in path.parents or not path.is_file() or path.suffix.lower() not in config.VIDEO_EXTENSIONS:
        raise HTTPException(404, "Video not found")
    return path


# ---------- VLC ----------

def find_vlc() -> str | None:
    if config.VLC_PATH and Path(config.VLC_PATH).is_file():
        return config.VLC_PATH
    found = shutil.which("vlc")
    if found:
        return found
    candidates = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        "/Applications/VLC.app/Contents/MacOS/VLC",
        "/usr/bin/vlc",
        "/snap/bin/vlc",
    ]
    return next((c for c in candidates if Path(c).is_file()), None)


def launch_vlc(video: Path) -> None:
    vlc = find_vlc()
    if not vlc:
        raise HTTPException(500, "VLC not found. Install it or set VLC_PATH in .env")
    # Argument list (no shell) => spaces and special characters in paths are safe.
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    cmd = [vlc] + (["--fullscreen"] if config.VLC_FULLSCREEN else []) + [str(video)]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs,
    )


# ---------- thumbnails (ffmpeg) ----------

_thumb_slots = threading.BoundedSemaphore(2)  # at most 2 ffmpeg processes at once


def find_ffmpeg() -> str | None:
    """ffmpeg for thumbnails (honours THUMBNAILS=false)."""
    return locate_ffmpeg() if config.THUMBNAILS else None


def locate_ffmpeg() -> str | None:
    if config.FFMPEG_PATH and Path(config.FFMPEG_PATH).is_file():
        return config.FFMPEG_PATH
    bundled = config.PROJECT_ROOT / "ffmpeg" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    if sys.platform == "win32":  # winget installs may not be on PATH until a new login
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
        for pattern in ("Links/ffmpeg.exe", "Packages/*FFmpeg*/**/bin/ffmpeg.exe"):
            hit = next(winget.glob(pattern), None)
            if hit:
                return str(hit)
    return None


def _run_ffmpeg(ffmpeg: str, video: Path, out: Path, seek: float) -> bool:
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", str(seek), "-i", str(video),
           "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(out)]
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30, creationflags=flags)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return out.is_file() and out.stat().st_size > 0


def get_thumbnail(video: Path, video_id: str) -> Path | None:
    """Return a cached JPEG for the video, generating it on first request."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    st = video.stat()
    key = hashlib.sha1(f"{video_id}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20]
    jpg, miss = config.THUMBS_DIR / f"{key}.jpg", config.THUMBS_DIR / f"{key}.none"
    if jpg.is_file():
        return jpg
    if miss.is_file():  # ffmpeg already failed on this file; don't retry every page load
        return None
    config.THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    with _thumb_slots:
        if jpg.is_file():
            return jpg
        # Very short clips have nothing at the seek point, so fall back to the first frame.
        if _run_ffmpeg(ffmpeg, video, jpg, config.THUMB_SECONDS) or _run_ffmpeg(ffmpeg, video, jpg, 0):
            return jpg
    miss.touch()
    return None


# ---------- browser playback (direct play or on-the-fly ffmpeg conversion) ----------

_probe_cache: dict = {}
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def probe_video(video: Path) -> dict:
    """Read duration and codecs by parsing `ffmpeg -i` output (ffprobe is not bundled)."""
    st = video.stat()
    key = (str(video), st.st_size, st.st_mtime_ns)
    if key in _probe_cache:
        return _probe_cache[key]
    info = {"duration": 0.0, "vcodec": None, "vok": False, "acodec": None}
    ffmpeg = locate_ffmpeg()
    if ffmpeg:
        try:
            out = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(video)],
                                 stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                                 creationflags=_NO_WINDOW).stderr.decode("utf-8", "replace")
        except (subprocess.TimeoutExpired, OSError):
            out = ""
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
        if m:
            info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
        for line in out.splitlines():
            if "Video:" in line and "attached pic" not in line and not info["vcodec"]:
                info["vcodec"] = re.search(r"Video:\s*(\w+)", line)[1].lower()
                # 8-bit 4:2:0 H.264 is what every browser can decode
                info["vok"] = info["vcodec"] == "h264" and bool(re.search(r"yuv420p(?!\w)", line))
            elif "Audio:" in line and not info["acodec"]:
                info["acodec"] = re.search(r"Audio:\s*(\w+)", line)[1].lower()
    _probe_cache[key] = info
    return info


def can_direct_play(video: Path, info: dict) -> bool:
    return (video.suffix.lower() in (".mp4", ".m4v") and info["vok"]
            and info["acodec"] in (None, "aac", "mp3"))


def add_range(ranges: list, a: float, b: float) -> list:
    """Merge [a, b] into a sorted list of non-overlapping played ranges."""
    merged = []
    for x, y in sorted(ranges + [[a, b]]):
        if merged and x <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], y)
        else:
            merged.append([x, y])
    return merged


def covered_seconds(ranges: list, limit: float) -> float:
    return sum(max(0.0, min(b, limit) - a) for a, b in ranges if a < limit)


def transcode_cmd(ffmpeg: str, video: Path, info: dict, start: float) -> list[str]:
    cmd = [ffmpeg, "-nostdin", "-v", "error"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(video), "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn"]
    # Only convert what the browser cannot play: H.264/AAC are copied, which is very fast.
    if info["vok"]:
        cmd += ["-c:v", "copy"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if info["acodec"] == "aac":
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    cmd += ["-avoid_negative_ts", "make_zero", "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof", "pipe:1"]
    return cmd


# ---------- remembered dropdown selections ----------

PREF_KEYS = {"parent", "child", "filter", "mode"}


def load_prefs() -> dict:
    try:
        with open(config.PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: v for k, v in data.items() if k in PREF_KEYS and isinstance(v, str)}
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return {}


# ---------- API ----------

class VideoRef(BaseModel):
    id: str


class Progress(BaseModel):
    id: str
    position: float
    duration: float = 0
    range_start: float | None = None  # continuously played stretch since the last report


class WatchedFlag(BaseModel):
    id: str
    watched: bool


@app.get("/api/library")
def library():
    return {"videos": scan_videos(), "videos_dir": str(config.VIDEOS_DIR),
            "thumbnails": find_ffmpeg() is not None, "prefs": load_prefs()}


@app.post("/api/prefs")
def save_prefs(prefs: dict):
    clean = {k: v for k, v in prefs.items() if k in PREF_KEYS and isinstance(v, str)}
    with _lock:
        merged = {**load_prefs(), **clean}
        tmp = config.PREFS_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        os.replace(tmp, config.PREFS_FILE)
    return {"ok": True}


@app.get("/api/playinfo")
def playinfo(id: str, start: float | None = None):
    """How the browser should play this video, and where to resume."""
    video = resolve_video(id)
    info = probe_video(video)
    direct = can_direct_play(video, info)
    if not direct and not locate_ffmpeg():
        raise HTTPException(500, f"ffmpeg is needed to play .{video.suffix.lstrip('.')} files in the browser. "
                                 "Install it or set FFMPEG_PATH in .env, or play in VLC.")
    entry = load_history().get(id, {})
    quoted = quote(id)
    return {"mode": "direct" if direct else "transcode",
            "url": f"/api/file?id={quoted}" if direct else f"/api/transcode?id={quoted}",
            "duration": info["duration"] or entry.get("duration", 0),
            "position": entry.get("position", 0),
            "title": video.stem}


@app.get("/api/file")
def raw_file(id: str):
    # FileResponse handles HTTP Range requests, so seeking works in the browser.
    return FileResponse(resolve_video(id), media_type="video/mp4")


@app.get("/api/transcode")
async def transcode(id: str, start: float = 0):
    """Stream the video as fragmented MP4, converted by ffmpeg while it is being watched."""
    video = resolve_video(id)
    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise HTTPException(500, "ffmpeg not found")
    info = probe_video(video)
    proc = subprocess.Popen(transcode_cmd(ffmpeg, video, info, max(0.0, start)),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)

    async def body():
        try:
            while True:
                chunk = await run_in_threadpool(proc.stdout.read1, 65536)
                if not chunk:
                    break
                yield chunk
        finally:  # browser closed/seeked: stop converting
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.wait()

    return StreamingResponse(body(), media_type="video/mp4", headers={"Cache-Control": "no-store"})


@app.post("/api/progress")
def progress(p: Progress):
    """Browser playback progress: saves the resume point, and marks the video watched once
    it has actually been played for WATCH_PERCENT of its length."""
    video = resolve_video(p.id)
    with _lock:
        history = load_history()
        entry = history.setdefault(p.id, {"title": video.stem})
        duration = p.duration or entry.get("duration", 0)
        position = max(0.0, min(p.position, duration)) if duration else max(0.0, p.position)
        ranges = entry.get("played", [])
        if p.range_start is not None and 0 <= p.range_start < position:
            ranges = add_range(ranges, p.range_start, position)
        completed = bool(duration > 0 and covered_seconds(ranges, duration) >= duration * config.WATCH_PERCENT / 100)
        if completed:
            entry.update({
                "title": video.stem, "watched": True,
                "date_watched": datetime.now().isoformat(timespec="seconds"),
                "play_count": entry.get("play_count", 0) + 1,
                "size_mb": round(video.stat().st_size / 1_048_576, 1),
            })
            for k in ("position", "duration", "played"):
                entry.pop(k, None)
        else:
            entry.update({"position": round(position, 1), "duration": round(duration, 1), "played": ranges})
        save_history(history)
    return {"ok": True, "completed": completed, "play_count": entry.get("play_count", 0),
            "date_watched": entry.get("date_watched")}


@app.post("/api/clear-progress")
def clear_progress(ref: VideoRef):
    resolve_video(ref.id)
    with _lock:
        history = load_history()
        entry = history.get(ref.id)
        if entry:
            for k in ("position", "duration", "played"):
                entry.pop(k, None)
            save_history(history)
    return {"ok": True}


@app.get("/api/thumb")
def thumb(id: str):
    thumb_path = get_thumbnail(resolve_video(id), id)
    if not thumb_path:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(thumb_path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/play")
def play(ref: VideoRef):
    video = resolve_video(ref.id)
    with _lock:  # mark watched immediately, even if VLC fails to start
        history = load_history()
        entry = history.setdefault(ref.id, {})
        entry.update({
            "title": video.stem,
            "watched": True,
            "date_watched": datetime.now().isoformat(timespec="seconds"),
            "play_count": entry.get("play_count", 0) + 1,
            "size_mb": round(video.stat().st_size / 1_048_576, 1),
        })
        save_history(history)
    launch_vlc(video)
    return {"ok": True, "date_watched": entry["date_watched"], "play_count": entry["play_count"]}


@app.post("/api/watched")
def set_watched(flag: WatchedFlag):
    """Manually toggle the watched state (e.g. un-mark a video)."""
    video = resolve_video(flag.id)
    with _lock:
        history = load_history()
        entry = history.setdefault(flag.id, {"title": video.stem})
        entry["watched"] = flag.watched
        if flag.watched:
            entry["date_watched"] = datetime.now().isoformat(timespec="seconds")
        else:
            entry["date_watched"] = None
            for k in ("position", "duration", "played"):  # also forget any resume point
                entry.pop(k, None)
        save_history(history)
    return {"ok": True}


@app.post("/api/shutdown")
def shutdown(request: Request):
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Only allowed from this PC")
    threading.Timer(0.3, os._exit, args=(0,)).start()  # let the response go out first
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def _already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", config.PORT)) == 0


if __name__ == "__main__":
    url = f"http://127.0.0.1:{config.PORT}"
    if _already_running():  # shortcut clicked twice: just open the existing server
        webbrowser.open(url)
        sys.exit(0)

    log_config = uvicorn.config.LOGGING_CONFIG
    if sys.stdout is None:  # started via pythonw (no console): log to a file instead
        sys.stdout = sys.stderr = open(config.PROJECT_ROOT / "homeflix.log", "a", encoding="utf-8", buffering=1)
        log_config = None

    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Videos folder: {config.VIDEOS_DIR}")
    print(f"VLC: {find_vlc() or 'NOT FOUND (set VLC_PATH in .env)'}")
    print(f"ffmpeg: {find_ffmpeg() or 'not found (no thumbnails; set FFMPEG_PATH in .env)'}")
    print(f"Open {url}")
    if config.OPEN_BROWSER:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_config=log_config)
