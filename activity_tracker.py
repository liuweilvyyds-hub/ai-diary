#!/usr/bin/env python3
"""Local Windows activity tracker for AI Diary.

Records active app/window title segments into diary.db. It only stores
metadata (app name, window title, time range, duration), not screenshots or
file contents.
"""
import argparse
import ctypes
import json
import logging
import os
import time
try:
    from ctypes import wintypes
except ImportError:
    wintypes = None  # Linux doesn't have wintypes
from datetime import datetime

from database import ActivityLog, SessionLocal

logger = logging.getLogger("activity-tracker")
logging.basicConfig(
    level=logging.INFO,
    format="[AI Diary] %(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIVITY_CONFIG_FILE = os.path.join(BASE_DIR, "activity_config.json")
DEFAULT_ACTIVITY_CONFIG = {
    "enabled": True,
    "capture_window_titles": True,
    "excluded_apps": [],
    "title_redact_keywords": ["password", "密码", "token", "secret", "key"],
    "retention_days": 30,
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


def get_window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def get_process_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "unknown"

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return f"pid-{pid.value}"
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        if not ok:
            return f"pid-{pid.value}"
        return os.path.basename(buffer.value) or f"pid-{pid.value}"
    finally:
        kernel32.CloseHandle(handle)


def get_active_window():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"app_name": "unknown", "window_title": ""}
    return {
        "app_name": get_process_name(hwnd),
        "window_title": get_window_title(hwnd),
    }


def load_activity_config():
    config = dict(DEFAULT_ACTIVITY_CONFIG)
    if os.path.exists(ACTIVITY_CONFIG_FILE):
        try:
            with open(ACTIVITY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update({k: data[k] for k in DEFAULT_ACTIVITY_CONFIG if k in data})
        except Exception:
            pass
    config["enabled"] = bool(config.get("enabled", True))
    config["capture_window_titles"] = bool(config.get("capture_window_titles", True))
    config["excluded_apps"] = [str(x).strip().lower() for x in (config.get("excluded_apps") or []) if str(x).strip()]
    config["title_redact_keywords"] = [str(x).strip().lower() for x in (config.get("title_redact_keywords") or []) if str(x).strip()]
    config["retention_days"] = max(1, min(int(config.get("retention_days") or 30), 365))
    return config


def sanitize_activity(app_name, window_title, config):
    app_lower = (app_name or "").lower()
    if any(pattern in app_lower for pattern in config["excluded_apps"]):
        return None
    title = window_title or ""
    if not config["capture_window_titles"]:
        title = ""
    elif any(keyword in title.lower() for keyword in config["title_redact_keywords"]):
        title = "[已脱敏]"
    return {"app_name": app_name or "unknown", "window_title": title}


def save_segment(app_name, window_title, started_at, ended_at, min_seconds):
    duration = int((ended_at - started_at).total_seconds())
    if duration < min_seconds:
        return False
    config = load_activity_config()
    if not config["enabled"]:
        return False
    sanitized = sanitize_activity(app_name, window_title, config)
    if not sanitized:
        return False
    db = SessionLocal()
    try:
        db.add(ActivityLog(
            app_name=sanitized["app_name"][:200],
            window_title=sanitized["window_title"],
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            source="window",
        ))
        db.commit()
        return True
    finally:
        db.close()


def run_tracker(poll_seconds, min_seconds, max_segment_seconds):
    current = get_active_window()
    started_at = datetime.now()
    logger.info("Activity tracker started. Press Ctrl+C to stop.")
    logger.info("Current: %s | %s", current['app_name'], current['window_title'])

    try:
        while True:
            time.sleep(poll_seconds)
            now = datetime.now()
            latest = get_active_window()
            changed = (
                latest["app_name"] != current["app_name"]
                or latest["window_title"] != current["window_title"]
            )
            too_long = (now - started_at).total_seconds() >= max_segment_seconds
            if changed or too_long:
                saved = save_segment(
                    current["app_name"],
                    current["window_title"],
                    started_at,
                    now,
                    min_seconds,
                )
                if saved:
                    logger.info("Saved: %s | %s", current['app_name'], current['window_title'])
                current = latest
                started_at = now
    except KeyboardInterrupt:
        ended_at = datetime.now()
        save_segment(current["app_name"], current["window_title"], started_at, ended_at, min_seconds)
        logger.info("Activity tracker stopped.")


def main():
    parser = argparse.ArgumentParser(description="Record active Windows app/window metadata for AI Diary.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--min-seconds", type=int, default=20)
    parser.add_argument("--max-segment-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true", help="Print the current active window and exit.")
    args = parser.parse_args()

    if args.once:
        active = get_active_window()
        print(f"{active['app_name']} | {active['window_title']}")
        return

    run_tracker(args.poll_seconds, args.min_seconds, args.max_segment_seconds)


if __name__ == "__main__":
    main()
