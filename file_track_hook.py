#!/usr/bin/env python3
"""PostToolUse hook: records file writes/edits for AI diary memory.

Reads hook JSON from stdin; extracts file_path; appends to today_context.txt.
"""
import sys, json, os
from datetime import datetime

CONTEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "today_context.txt")
MAX_LINES = 200  # keep file manageable

def classify(fp):
    """Return a simple category for a file path."""
    fp = fp.replace("\\", "/").lower()
    if "/projects/" in fp:
        # Extract project name
        parts = fp.split("/projects/")
        if len(parts) > 1:
            proj = parts[1].split("/")[0]
            return f"项目 {proj}"
    if fp.endswith(".py"): return "Python 代码"
    if fp.endswith((".md", ".mdx")): return "文档"
    if fp.endswith((".ts", ".tsx", ".js", ".jsx")): return "TypeScript/JS 代码"
    if fp.endswith((".html", ".css")): return "网页"
    if fp.endswith(".txt"): return "文本"
    return os.path.splitext(fp)[1] or "文件"

try:
    raw = sys.stdin.read().strip()
    data = json.loads(raw) if raw else {}
    fp = data.get("tool_input", {}).get("file_path", "")
    tool = data.get("tool_name", "")
    if data.get("tool_response", {}).get("success") is False:
        sys.exit(0)

    ts = datetime.now().strftime("%H:%M")

    # Only meaningful files
    skip_exts = {".pyc", ".pyo", ".log", ".lock", ".json", ".db", ".tmp"}
    ext = os.path.splitext(fp)[1].lower()
    if ext in skip_exts or not fp:
        sys.exit(0)

    cat = classify(fp)
    fname = os.path.basename(fp)

    # Read existing
    existing = ""
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            existing = f.read().strip()

    # Deduplicate - skip if same file already recorded recently
    if fname in existing:
        sys.exit(0)

    # Get the file's last modified time to check if today
    try:
        mtime = os.path.getmtime(fp)
        ft = datetime.fromtimestamp(mtime)
        now = datetime.now()
        if ft.date() != now.date():
            sys.exit(0)  # skip files not modified today (possible hook replay)
    except:
        pass

    entry = f"[{ts}] {tool}: {cat}/{fname}"

    lines = existing.split("\n") if existing else []
    lines.append(entry)
    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]

    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    sys.exit(0)

except Exception as e:
    # Never block user flow
    sys.exit(0)
