"""Helpers: formatting, humanization, and utility functions."""
from collections import defaultdict
from datetime import datetime, timedelta

# ---------- Duration formatting ----------
def format_duration(seconds: int) -> str:
    seconds = max(int(seconds or 0), 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    if minutes:
        return f"{minutes}分钟"
    return f"{seconds}秒"


# ---------- Text helpers ----------
def compact_title(title: str, max_len: int = 80) -> str:
    title = (title or "").strip()
    if len(title) <= max_len:
        return title
    return title[:max_len] + "..."


def title_similarity_key(title: str) -> str:
    title = (title or "").strip().lower()
    for sep in [" - ", " | ", " — ", " – ", " _ "]:
        if sep in title:
            title = title.split(sep)[0]
            break
    return title[:32]


def normalize_memory_text(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def markdown_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*").replace("_", "\\_").replace("#", "\\#")


# ---------- Activity range ----------
def activity_day_range(target):
    start = datetime(target.year, target.month, target.day)
    return start, start + timedelta(days=1)


# ---------- Clock / minute helpers ----------
def minutes_from_time(value: str | None) -> int | None:
    try:
        hour, minute = (value or "").split(":", 1)
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return None


def format_clock_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "--"
    minutes = max(0, min(int(minutes), 24 * 60 - 1))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def average_seconds(values: list[int]) -> int:
    clean = [int(value or 0) for value in values if int(value or 0) > 0]
    return int(sum(clean) / len(clean)) if clean else 0


# ---------- Humanization ----------
def humanize_app_name(app_name: str) -> str:
    app = (app_name or "").strip()
    lower = app.lower()
    if "codex" in lower:
        return "AI 编程助手"
    if "msedge" in lower or "chrome" in lower or "firefox" in lower:
        return "浏览器"
    if "weixin" in lower or "wechat" in lower:
        return "微信"
    if "sunlogin" in lower:
        return "远程连接工具"
    if "clash" in lower:
        return "网络代理工具"
    if "shellhost" in lower:
        return "系统界面"
    if "cockpit" in lower:
        return "工具面板"
    if "haojiao" in lower or "quality" in lower:
        return "质量分析工具"
    if lower.endswith(".exe"):
        return app[:-4]
    return app or "应用"


def humanize_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return ""
    if title == "[已脱敏]":
        return "一个已脱敏的窗口"
    lower = title.lower()
    if "codex" in lower:
        return "AI 日记和代码任务"
    if "ai 日记" in title or "ai-diary" in lower:
        return "AI 日记页面"
    if "号角公司管理平台" in title:
        return "质量管理页面"
    compact_digits = "".join(ch for ch in title if ch.isdigit())
    non_space = "".join(ch for ch in title if not ch.isspace())
    if compact_digits and len(compact_digits) >= 6 and len(compact_digits) >= max(1, int(len(non_space) * 0.7)):
        return "远程连接窗口"
    for suffix in [" - Microsoft\u200b Edge", " - Microsoft Edge", " - Google Chrome"]:
        title = title.replace(suffix, "")
    for marker in [" 和另外 "]:
        if marker in title:
            title = title.split(marker, 1)[0]
            break
    return compact_title(title, 42)


def humanize_context_text(text: str) -> str:
    text = str(text or "")
    replacements = {
        "Codex.exe": "AI 编程助手", "codex.exe": "AI 编程助手", "Codex": "AI 编程助手",
        "msedge.exe": "浏览器", "Microsoft\u200b Edge": "浏览器",
        "Microsoft Edge": "浏览器", "Google Chrome": "浏览器", "Chrome": "浏览器",
        "Weixin.exe": "微信", "微信.exe": "微信",
        "SunloginClient.exe": "远程连接工具", "SunloginClient": "远程连接工具",
        "clash-verge.exe": "网络代理工具", "clash-verge": "网络代理工具",
        "ShellHost.exe": "系统界面", "ShellHost": "系统界面",
        "cockpit-tools.exe": "工具面板", "cockpit-tools": "工具面板",
        "Haojiao_Quality_Analysis_v2.4.8.exe": "质量分析工具",
        "Haojiao_Quality_Analysis_v2.4.8": "质量分析工具",
    }
    for raw, friendly in replacements.items():
        text = text.replace(raw, friendly)
    return text


def humanize_event(event: dict) -> str:
    category = event.get("category") or "活动"
    titles = [humanize_title(t) for t in (event.get("titles") or [])]
    titles = [t for t in titles if t]
    topic = titles[0] if titles else ""
    duration = event.get("duration_text") or format_duration(event.get("duration_seconds") or 0)
    time_text = event.get("time") or ""
    if category == "写代码/项目开发":
        action = "在改项目、写代码和调功能"
    elif category == "查资料/网页浏览":
        action = "在浏览器里查资料、看页面"
    elif category == "沟通协作":
        action = "在处理聊天和沟通"
    elif category == "写作/文档整理":
        action = "在整理文字和文档"
    elif category == "手动补充":
        action = topic or "补充了一条当天动态"
    else:
        action = f"在处理{category}"
    if topic and category not in {"手动补充"}:
        action += f"，主题像是「{topic}」"
    return f"{time_text} {action}，大约{duration}。"


# ---------- Model-to-dict converters ----------
def entry_to_dict(e) -> dict:
    return {
        "id": e.id, "title": e.title, "content": e.content,
        "word_count": len(e.content or ""), "mood": e.mood,
        "mood_score": e.mood_score, "author": e.author or "user",
        "keywords": e.keywords or [], "summary": e.summary or "",
        "images": e.images or [], "evidence": e.evidence or {},
        "weather": e.weather or "",
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


def activity_to_dict(a) -> dict:
    redacted = (a.window_title or "").strip() == "[已脱敏]"
    return {
        "id": a.id, "app_name": a.app_name or "",
        "display_name": humanize_app_name(a.app_name),
        "window_title": a.window_title or "",
        "display_title": humanize_title(a.window_title or a.note or ""),
        "started_at": a.started_at.isoformat(),
        "ended_at": a.ended_at.isoformat(),
        "duration_seconds": a.duration_seconds or 0,
        "duration_text": format_duration(a.duration_seconds or 0),
        "redacted": redacted, "source": a.source or "window",
        "note": a.note or "",
    }


def memory_to_dict(m) -> dict:
    return {
        "id": m.id, "category": m.category or "general",
        "content": m.content, "source": m.source or "manual",
        "confidence": m.confidence or 0.0,
        "pinned": bool(m.pinned), "active": bool(m.active),
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
    }


def daily_summary_to_dict(s) -> dict:
    return {
        "id": s.id, "date": s.date,
        "summary": s.summary or "", "highlights": s.highlights or [],
        "categories": s.categories or [], "top_apps": s.top_apps or [],
        "events": s.events or [], "dayparts": s.dayparts or [],
        "total_seconds": s.total_seconds or 0,
        "total_text": format_duration(s.total_seconds or 0),
        "source": s.source or "activity",
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }
