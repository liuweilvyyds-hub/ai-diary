"""AI Diary - FastAPI main entry point."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import logging
import ctypes
try:
    from ctypes import wintypes
except ImportError:
    wintypes = None  # Linux doesn't have wintypes
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import ActivityLog

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="[AI Diary] %(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ai-diary")

# ---------- App ----------
app = FastAPI(title="AI Diary", version="0.4.0")

# ---------- Mount routers ----------
from routers.entries import router as entries_router
from routers.activity import router as activity_router
from routers.ai import router as ai_router
from routers.memories import router as memories_router
from routers.stats import router as stats_router

app.include_router(entries_router)
app.include_router(activity_router)
app.include_router(ai_router)
app.include_router(memories_router)
app.include_router(stats_router)

# ---------- Activity config (from shared module) ----------
from config import load_activity_config, save_activity_config, ACTIVITY_CONFIG_FILE, DEFAULT_ACTIVITY_CONFIG

# ---------- Foreground sync (Windows) ----------
_last_foreground_snapshot = {"app_name": "", "window_title": "", "seen_at": None}


def read_foreground_window():
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app_name = f"pid-{pid.value}" if pid.value else "unknown"
        if pid.value:
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    size = wintypes.DWORD(1024)
                    path_buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, path_buffer, ctypes.byref(size)):
                        app_name = os.path.basename(path_buffer.value) or app_name
                finally:
                    kernel32.CloseHandle(handle)
        return {"app_name": app_name, "window_title": title}
    except Exception as e:
        logger.warning("Foreground sync failed: %s", e)
        return None


def sanitize_activity_payload(app_name: str, window_title: str, config: dict):
    app = app_name or "unknown"
    if any(pattern.lower() in app.lower() for pattern in (config.get("excluded_apps") or [])):
        return None
    title = window_title or ""
    if not config.get("capture_window_titles", True):
        title = ""
    elif any(keyword.lower() in title.lower() for keyword in (config.get("title_redact_keywords") or [])):
        title = "[已脱敏]"
    return {"app_name": app[:200], "window_title": title}


def sync_current_activity(db, min_seconds: int = 15):
    config = load_activity_config()
    if not config.get("enabled", True):
        return None
    current = read_foreground_window()
    if not current:
        return None

    now = datetime.now()
    global _last_foreground_snapshot
    snapshot = _last_foreground_snapshot
    same = current["app_name"] == snapshot.get("app_name") and current["window_title"] == snapshot.get("window_title")
    seen_at = snapshot.get("seen_at") if same else None
    if not isinstance(seen_at, datetime):
        _last_foreground_snapshot = {**current, "seen_at": now}
        if min_seconds > 0:
            return None
        seen_at = now

    duration = int((now - seen_at).total_seconds())
    latest = db.query(ActivityLog).order_by(ActivityLog.ended_at.desc()).first()
    latest_age = int((now - latest.ended_at).total_seconds()) if latest else None
    if duration < min_seconds and latest_age is not None and latest_age <= 180:
        return None
    if latest and latest.app_name == current["app_name"] and latest.window_title == current["window_title"] and latest_age is not None and latest_age <= 120:
        return None

    sanitized = sanitize_activity_payload(current["app_name"], current["window_title"], config)
    _last_foreground_snapshot = {**current, "seen_at": now}
    if not sanitized:
        return None
    duration = max(duration, min_seconds)
    log = ActivityLog(
        app_name=sanitized["app_name"],
        window_title=sanitized["window_title"],
        started_at=now - timedelta(seconds=duration),
        ended_at=now,
        duration_seconds=duration,
        source="foreground",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# ---------- Static files ----------
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
