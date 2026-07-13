#!/usr/bin/env python3
"""Stop hook: writes session summary to today_context.txt for AI diary memory."""
import sys, json, os
from datetime import datetime

CONTEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "today_context.txt")

try:
    raw = sys.stdin.read().strip()
    data = json.loads(raw) if raw else {}
    session_id = data.get("session_id", "")[:12]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = ""
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            existing = f.read().strip()

    # Mark session end - the real content is written by Claude during the session
    entry = (
        f"\n\n[会话结束 {ts}]\n"
        f"威威刚才结束了一段 Claude Code 工作会话。\n"
        f"请结合上面记录的文件变更和对话内容，用你的视角感受威威今天在做什么。"
    )

    # Only append if not already at end
    if not existing.endswith(entry.strip()):
        with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
            f.write(entry)

    print(json.dumps({"systemMessage": f"日记记忆已更新 ({ts})"}))
except Exception as e:
    print(json.dumps({"systemMessage": f"hook ok: {e}"}))
