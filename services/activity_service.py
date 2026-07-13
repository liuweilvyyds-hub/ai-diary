"""Activity service: classification, summarization, comparison, and context building."""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from database import ActivityLog, DailySummary, DiaryEntry, PersonalMemory
from services.helpers import (
    activity_day_range, average_seconds, compact_title, format_clock_minutes,
    format_duration, humanize_app_name, humanize_context_text, humanize_event,
    humanize_title, minutes_from_time, title_similarity_key,
)

logger = logging.getLogger("ai-diary")

# ---------- Activity classification ----------
ACTIVITY_CATEGORY_RULES = [
    ("写代码/项目开发", ["code.exe", "codex.exe", "pycharm", "webstorm", "idea", "cursor",
                         "devenv", "terminal", "powershell", "cmd.exe", "python.exe", "uvicorn", "git"]),
    ("查资料/网页浏览", ["chrome.exe", "msedge.exe", "firefox.exe", "browser", "docs",
                         "文档", "搜索", "google", "bing", "github", "stackoverflow"]),
    ("沟通协作", ["wechat", "weixin", "qq.exe", "dingtalk", "钉钉", "telegram",
                  "discord", "teams", "slack", "mail", "outlook"]),
    ("写作/文档整理", ["word", "wps", "notion", "obsidian", "typora", "onenote", ".md", "文档", "笔记"]),
    ("文件整理", ["explorer.exe", "everything", "winrar", "7zfm"]),
    ("影音娱乐", ["bilibili", "youtube", "spotify", "music", "potplayer", "vlc", "cloudmusic", "steam"]),
    ("系统工具", ["taskmgr", "settings", "control", "regedit", "services.msc"]),
]


def classify_activity(app_name: str, window_title: str) -> str:
    if (app_name or "") == "手动补充":
        return "手动补充"
    haystack = f"{app_name or ''} {window_title or ''}".lower()
    for category, needles in ACTIVITY_CATEGORY_RULES:
        if any(needle in haystack for needle in needles):
            return category
    return "其他活动"


# ---------- Privacy ----------
def summarize_privacy_logs(logs: list[ActivityLog]) -> dict:
    redacted_logs = [log for log in logs if (log.window_title or "").strip() == "[已脱敏]"]
    redacted_seconds = sum(int(log.duration_seconds or 0) for log in redacted_logs)
    by_app = defaultdict(int)
    for log in redacted_logs:
        by_app[log.app_name or "未知应用"] += int(log.duration_seconds or 0)
    apps = [
        {"app_name": app, "duration_seconds": seconds, "duration_text": format_duration(seconds)}
        for app, seconds in sorted(by_app.items(), key=lambda x: x[1], reverse=True)
    ]
    return {
        "redacted_count": len(redacted_logs),
        "redacted_seconds": redacted_seconds,
        "redacted_text": format_duration(redacted_seconds),
        "redacted_apps": apps[:5],
        "has_redacted": bool(redacted_logs),
    }


# ---------- Event building ----------
def event_daypart_label(start_time: str) -> tuple[str, str]:
    try:
        hour = int((start_time or "0").split(":", 1)[0])
    except (TypeError, ValueError):
        hour = 0
    if 5 <= hour < 12:
        return "morning", "上午"
    if 12 <= hour < 18:
        return "afternoon", "下午"
    if 18 <= hour < 24:
        return "evening", "晚上"
    return "late_night", "凌晨"


def build_activity_events(logs: list[ActivityLog], limit: int = 24) -> list[dict]:
    events = []
    current = None
    for log in logs:
        seconds = int(log.duration_seconds or 0)
        if seconds <= 0:
            continue
        app = log.app_name or "未知应用"
        category = classify_activity(log.app_name, log.window_title)
        display_title = (log.note or "").strip() if log.source == "manual" and log.note else log.window_title
        title = compact_title(display_title)
        title_key = title_similarity_key(title)

        should_merge = False
        if current:
            gap_seconds = int((log.started_at - current["ended_at_raw"]).total_seconds())
            same_flow = current["category"] == category and (
                current["app_name"] == app or (title_key and title_key == current.get("title_key"))
            )
            should_merge = same_flow and gap_seconds <= 300

        if not should_merge:
            if current:
                events.append(current)
            current = {
                "started_at_raw": log.started_at, "ended_at_raw": log.ended_at,
                "start_time": log.started_at.strftime("%H:%M"),
                "end_time": log.ended_at.strftime("%H:%M"),
                "time": f"{log.started_at.strftime('%H:%M')}-{log.ended_at.strftime('%H:%M')}",
                "app_name": app, "display_name": humanize_app_name(app),
                "category": category,
                "duration_seconds": seconds, "duration_text": format_duration(seconds),
                "titles": [title] if title else [], "title_key": title_key, "segments": 1,
            }
            continue

        current["ended_at_raw"] = max(current["ended_at_raw"], log.ended_at)
        current["end_time"] = current["ended_at_raw"].strftime("%H:%M")
        current["time"] = f"{current['start_time']}-{current['end_time']}"
        current["duration_seconds"] += seconds
        current["duration_text"] = format_duration(current["duration_seconds"])
        current["segments"] += 1
        if title and title not in current["titles"]:
            current["titles"].append(title)

    if current:
        events.append(current)

    clean_events = []
    for event in events[:limit]:
        titles = event["titles"][:3]
        title_text = "；".join(titles)
        sentence = (
            f"{event['time']} {event['category']}："
            f"{event.get('display_name') or event['app_name']}"
            f"{' / ' + title_text if title_text else ''}"
            f"（{event['duration_text']}，合并{event['segments']}段）"
        )
        clean_events.append({
            "time": event["time"], "start_time": event["start_time"],
            "end_time": event["end_time"], "app_name": event["app_name"],
            "display_name": event.get("display_name") or humanize_app_name(event["app_name"]),
            "category": event["category"],
            "duration_seconds": event["duration_seconds"],
            "duration_text": event["duration_text"],
            "titles": titles, "segments": event["segments"],
            "sentence": sentence,
            "natural_sentence": humanize_event({
                "time": event["time"], "app_name": event["app_name"],
                "category": event["category"],
                "duration_seconds": event["duration_seconds"],
                "duration_text": event["duration_text"], "titles": titles,
            }),
        })
    return clean_events


def build_dayparts(events: list[dict]) -> list[dict]:
    buckets = {}
    order = ["late_night", "morning", "afternoon", "evening"]
    for event in (events or []):
        key, label = event_daypart_label(event.get("start_time") or "")
        bucket = buckets.setdefault(key, {
            "key": key, "label": label, "duration_seconds": 0, "duration_text": "0秒",
            "event_count": 0, "top_categories": {}, "events": [], "summary": "",
        })
        seconds = int(event.get("duration_seconds") or 0)
        category = event.get("category") or "其他活动"
        bucket["duration_seconds"] += seconds
        bucket["duration_text"] = format_duration(bucket["duration_seconds"])
        bucket["event_count"] += 1
        bucket["top_categories"][category] = bucket["top_categories"].get(category, 0) + seconds
        if len(bucket["events"]) < 5:
            bucket["events"].append(event)

    result = []
    for key in order:
        bucket = buckets.get(key)
        if not bucket:
            continue
        categories = sorted(bucket["top_categories"].items(), key=lambda x: x[1], reverse=True)
        main_category = categories[0][0] if categories else "活动"
        sample_events = "；".join(
            (e.get("natural_sentence") or e.get("sentence") or "")
            for e in bucket["events"][:2]
            if e.get("natural_sentence") or e.get("sentence")
        )
        bucket["top_categories"] = [
            {"category": c, "duration_seconds": s, "duration_text": format_duration(s)}
            for c, s in categories[:4]
        ]
        bucket["summary"] = f"{bucket['label']}主要是{main_category}，约{bucket['duration_text']}。"
        if sample_events:
            bucket["summary"] += f" 大概是在：{sample_events}"
        result.append(bucket)
    return result


# ---------- Summarization ----------
def summarize_activity_logs(logs: list[ActivityLog], limit: int = 40) -> dict:
    by_app = defaultdict(int)
    by_category = defaultdict(int)
    rows = []
    topic_counts = defaultdict(int)
    latest_ended_at = None

    for log in logs:
        seconds = log.duration_seconds or 0
        app = log.app_name or "未知应用"
        category = classify_activity(log.app_name, log.window_title)
        display_title = (log.note or "").strip() if log.source == "manual" and log.note else log.window_title
        by_app[app] += seconds
        by_category[category] += seconds
        latest_ended_at = max(latest_ended_at, log.ended_at) if latest_ended_at else log.ended_at

        title = compact_title(display_title)
        readable_title = humanize_title(display_title)
        if title:
            topic_counts[title] += seconds
        rows.append({
            "time": f"{log.started_at.strftime('%H:%M')}-{log.ended_at.strftime('%H:%M')}",
            "app_name": app, "display_name": humanize_app_name(app),
            "window_title": title, "display_title": readable_title,
            "category": category,
            "duration_seconds": seconds, "duration_text": format_duration(seconds),
            "sentence": (
                f"{log.started_at.strftime('%H:%M')}-{log.ended_at.strftime('%H:%M')} "
                f"{category}：{humanize_app_name(app)}"
                f"{' / ' + title if title else ''}"
                f"（{format_duration(seconds)}）"
            ),
        })

    top_apps = [
        {"app_name": app, "display_name": humanize_app_name(app),
         "duration_seconds": seconds, "duration_text": format_duration(seconds)}
        for app, seconds in sorted(by_app.items(), key=lambda x: x[1], reverse=True)
    ]
    categories = [
        {"category": c, "duration_seconds": s, "duration_text": format_duration(s)}
        for c, s in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    ]
    top_topics = [
        {"title": t, "display_title": humanize_title(t),
         "duration_seconds": s, "duration_text": format_duration(s)}
        for t, s in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    ]

    highlights = []
    if categories:
        top = categories[0]
        highlights.append(f"今天主要在{top['category']}上花时间，累计约{top['duration_text']}。")
    for item in categories[1:3]:
        highlights.append(f"也有一些{item['category']}，大约{item['duration_text']}。")
    if top_topics:
        highlights.append("最常出现的窗口主题包括：" +
                          "、".join(t.get("display_title") or t["title"] for t in top_topics[:3]) + "。")

    events = build_activity_events(logs, limit=limit)
    return {
        "total_seconds": sum(by_app.values()),
        "total_text": format_duration(sum(by_app.values())),
        "top_apps": top_apps, "categories": categories,
        "top_topics": top_topics, "highlights": highlights,
        "events": events, "dayparts": build_dayparts(events),
        "privacy": summarize_privacy_logs(logs),
        "timeline": rows[:limit],
        "latest_ended_at": latest_ended_at.isoformat() if latest_ended_at else None,
    }


def summarize_activity_for_date(db: Session, target: date, limit: int = 40) -> dict:
    start, end = activity_day_range(target)
    logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
        ActivityLog.duration_seconds >= 20,
    ).order_by(ActivityLog.started_at.asc()).limit(1000).all()
    return summarize_activity_logs(logs, limit=limit)


# ---------- Rhythm ----------
def summarize_activity_rhythm(summary: dict) -> dict:
    events = summary.get("events") or []
    start_minutes = [
        value for value in (minutes_from_time(e.get("start_time")) for e in events)
        if value is not None
    ]
    end_minutes = [
        value for value in (minutes_from_time(e.get("end_time")) for e in events)
        if value is not None
    ]
    durations = [int(e.get("duration_seconds") or 0) for e in events if int(e.get("duration_seconds") or 0) > 0]
    event_count = len(durations)
    longest_focus = max(durations) if durations else 0
    avg_event_seconds = int(sum(durations) / event_count) if event_count else 0
    return {
        "first_start_minute": min(start_minutes) if start_minutes else None,
        "first_start_time": format_clock_minutes(min(start_minutes) if start_minutes else None),
        "last_end_minute": max(end_minutes) if end_minutes else None,
        "last_end_time": format_clock_minutes(max(end_minutes) if end_minutes else None),
        "event_count": event_count,
        "avg_event_seconds": avg_event_seconds,
        "avg_event_text": format_duration(avg_event_seconds),
        "longest_focus_seconds": longest_focus,
        "longest_focus_text": format_duration(longest_focus),
    }


def average_activity_rhythm(rows: list[dict]) -> dict:
    rhythms = [r.get("rhythm") or {} for r in rows if r.get("rhythm")]
    active = len(rhythms)
    if not active:
        return {
            "first_start_minute": None, "first_start_time": "--",
            "last_end_minute": None, "last_end_time": "--",
            "event_count": 0, "avg_event_seconds": 0, "avg_event_text": "0秒",
            "longest_focus_seconds": 0, "longest_focus_text": "0秒",
        }
    first_values = [r["first_start_minute"] for r in rhythms if r.get("first_start_minute") is not None]
    end_values = [r["last_end_minute"] for r in rhythms if r.get("last_end_minute") is not None]
    event_count = int(sum(int(r.get("event_count") or 0) for r in rhythms) / active)
    avg_event_seconds = int(sum(int(r.get("avg_event_seconds") or 0) for r in rhythms) / active)
    longest_focus_seconds = int(sum(int(r.get("longest_focus_seconds") or 0) for r in rhythms) / active)
    first_start = int(sum(first_values) / len(first_values)) if first_values else None
    last_end = int(sum(end_values) / len(end_values)) if end_values else None
    return {
        "first_start_minute": first_start, "first_start_time": format_clock_minutes(first_start),
        "last_end_minute": last_end, "last_end_time": format_clock_minutes(last_end),
        "event_count": event_count,
        "avg_event_seconds": avg_event_seconds, "avg_event_text": format_duration(avg_event_seconds),
        "longest_focus_seconds": longest_focus_seconds,
        "longest_focus_text": format_duration(longest_focus_seconds),
    }


# ---------- Comparison / Trends ----------
def build_activity_comparison(db: Session, target: date, days: int = 7) -> dict:
    days = max(2, min(int(days or 7), 30))
    today = summarize_activity_for_date(db, target, limit=24)
    today_rhythm = summarize_activity_rhythm(today)
    baseline_rows = []
    for offset in range(1, days + 1):
        day = target - timedelta(days=offset)
        summary = summarize_activity_for_date(db, day, limit=8)
        if summary.get("total_seconds", 0) > 0:
            baseline_rows.append({
                "date": day.isoformat(), "summary": summary,
                "rhythm": summarize_activity_rhythm(summary),
            })

    active_days = len(baseline_rows)
    baseline_total = sum(r["summary"].get("total_seconds", 0) for r in baseline_rows)
    baseline_avg = int(baseline_total / active_days) if active_days else 0
    baseline_categories = defaultdict(int)
    for row in baseline_rows:
        for item in row["summary"].get("categories", []):
            baseline_categories[item.get("category") or "其他活动"] += int(item.get("duration_seconds") or 0)
    baseline_category_avg = {
        c: int(s / active_days) if active_days else 0
        for c, s in baseline_categories.items()
    }

    today_categories = {
        item.get("category") or "其他活动": int(item.get("duration_seconds") or 0)
        for item in today.get("categories", [])
    }
    today_top = (today.get("categories") or [{}])[0].get("category") if today.get("categories") else ""
    baseline_rhythm = average_activity_rhythm(baseline_rows)
    insights = []
    rhythm_insights = []
    if not active_days:
        insights.append("最近几天还没有足够的活动记录，今天会先作为新的生活基准。")
    else:
        delta = int(today.get("total_seconds", 0) - baseline_avg)
        if abs(delta) >= 900:
            direction = "更忙一些" if delta > 0 else "更轻一点"
            insights.append(f"今天整体比近 {active_days} 个有记录的日子{direction}，差不多相差 {format_duration(abs(delta))}。")
        else:
            insights.append(f"今天整体节奏和近 {active_days} 个有记录的日子差不多。")

        ranked_diffs = []
        for c, s in today_categories.items():
            ranked_diffs.append((s - baseline_category_avg.get(c, 0), c, s))
        ranked_diffs.sort(key=lambda r: abs(r[0]), reverse=True)
        for diff, category, seconds in ranked_diffs[:2]:
            if abs(diff) < 600:
                continue
            trend = "更多" if diff > 0 else "更少"
            insights.append(f"{category}比平时{trend}，今天约 {format_duration(seconds)}，相差 {format_duration(abs(diff))}。")
        if today_top:
            insights.append(f"今天最明显的主线是{today_top}，她写日记时会优先参考这条节奏。")

        if today_rhythm.get("first_start_minute") is not None and baseline_rhythm.get("first_start_minute") is not None:
            start_delta = int(today_rhythm["first_start_minute"] - baseline_rhythm["first_start_minute"])
            if abs(start_delta) >= 30:
                direction = "更晚开始进入状态" if start_delta > 0 else "更早开始进入状态"
                rhythm_insights.append(f"今天比平时{direction}，大约差 {format_duration(abs(start_delta) * 60)}。")

        focus_delta = int(today_rhythm.get("longest_focus_seconds") or 0) - int(baseline_rhythm.get("longest_focus_seconds") or 0)
        if abs(focus_delta) >= 900 and today_rhythm.get("longest_focus_seconds"):
            direction = "更能沉下来" if focus_delta > 0 else "专注段更短"
            rhythm_insights.append(f"最长连续做事时间比平时{direction}，今天最长约 {today_rhythm.get('longest_focus_text')}。")

        event_delta = int(today_rhythm.get("event_count") or 0) - int(baseline_rhythm.get("event_count") or 0)
        if abs(event_delta) >= 3:
            direction = "更碎一些" if event_delta > 0 else "更集中一些"
            rhythm_insights.append(f"今天事件段数量比平时{direction}，一共整理出 {today_rhythm.get('event_count')} 段。")
        insights.extend(rhythm_insights[:2])

    return {
        "date": target.isoformat(), "window_days": days,
        "baseline_active_days": active_days,
        "today": {
            "total_seconds": today.get("total_seconds", 0),
            "total_text": today.get("total_text", "0秒"),
            "top_category": today_top,
            "categories": today.get("categories", [])[:6],
            "rhythm": today_rhythm,
        },
        "baseline": {
            "avg_total_seconds": baseline_avg,
            "avg_total_text": format_duration(baseline_avg),
            "active_days": active_days,
            "rhythm": baseline_rhythm,
        },
        "rhythm": {
            "today": today_rhythm, "baseline": baseline_rhythm,
            "insights": [humanize_context_text(l) for l in rhythm_insights[:3]],
        },
        "insights": [humanize_context_text(l) for l in insights[:4]],
    }


def build_activity_trends(db: Session, target: date, days: int = 30) -> dict:
    days = max(7, min(int(days or 30), 90))
    daily_rows = []
    for offset in range(days - 1, -1, -1):
        day = target - timedelta(days=offset)
        summary = summarize_activity_for_date(db, day, limit=24)
        rhythm = summarize_activity_rhythm(summary)
        daily_rows.append({
            "date": day.isoformat(),
            "total_seconds": int(summary.get("total_seconds") or 0),
            "total_text": summary.get("total_text") or "0秒",
            "top_category": (summary.get("categories") or [{}])[0].get("category") if summary.get("categories") else "",
            "rhythm": rhythm,
        })

    active_rows = [r for r in daily_rows if r["total_seconds"] > 0]
    midpoint = len(daily_rows) // 2
    early_rows = [r for r in daily_rows[:midpoint] if r["total_seconds"] > 0]
    recent_rows = [r for r in daily_rows[midpoint:] if r["total_seconds"] > 0]
    early_avg_total = average_seconds([r["total_seconds"] for r in early_rows])
    recent_avg_total = average_seconds([r["total_seconds"] for r in recent_rows])
    recent_rhythm = average_activity_rhythm([{"rhythm": r["rhythm"]} for r in recent_rows])
    all_rhythm = average_activity_rhythm([{"rhythm": r["rhythm"]} for r in active_rows])

    insights = []
    if len(active_rows) < 3:
        insights.append("最近活动记录还不够多，先把这些天作为生活节奏的起点。")
    else:
        total_delta = recent_avg_total - early_avg_total
        if early_avg_total and abs(total_delta) >= 900:
            direction = "更充实" if total_delta > 0 else "更轻一点"
            insights.append(f"最近半段日均活动比前半段{direction}，差不多相差 {format_duration(abs(total_delta))}。")
        else:
            insights.append("最近一段时间的整体活动量比较平稳。")

        recent_longest = average_seconds([int(r["rhythm"].get("longest_focus_seconds") or 0) for r in recent_rows])
        all_longest = average_seconds([int(r["rhythm"].get("longest_focus_seconds") or 0) for r in active_rows])
        focus_delta = recent_longest - all_longest
        if abs(focus_delta) >= 600 and recent_longest:
            direction = "更容易沉下来" if focus_delta > 0 else "更容易被打断"
            insights.append(f"最近的最长连续做事时间看起来{direction}，平均约 {format_duration(recent_longest)}。")

        starts = [r["rhythm"].get("first_start_minute") for r in active_rows if r["rhythm"].get("first_start_minute") is not None]
        recent_starts = [r["rhythm"].get("first_start_minute") for r in recent_rows if r["rhythm"].get("first_start_minute") is not None]
        if starts and recent_starts:
            all_start = int(sum(starts) / len(starts))
            recent_start = int(sum(recent_starts) / len(recent_starts))
            start_delta = recent_start - all_start
            if abs(start_delta) >= 30:
                direction = "更晚开始进入状态" if start_delta > 0 else "更早开始进入状态"
                insights.append(f"最近平均开始时间{direction}，大约在 {format_clock_minutes(recent_start)}。")

    return {
        "date": target.isoformat(), "window_days": days,
        "active_days": len(active_rows), "days": daily_rows,
        "summary": {
            "avg_total_seconds": average_seconds([r["total_seconds"] for r in active_rows]),
            "avg_total_text": format_duration(average_seconds([r["total_seconds"] for r in active_rows])),
            "recent_avg_total_seconds": recent_avg_total,
            "recent_avg_total_text": format_duration(recent_avg_total),
            "avg_first_start_time": all_rhythm.get("first_start_time"),
            "recent_first_start_time": recent_rhythm.get("first_start_time"),
            "avg_longest_focus_text": all_rhythm.get("longest_focus_text"),
            "recent_longest_focus_text": recent_rhythm.get("longest_focus_text"),
        },
        "insights": [humanize_context_text(l) for l in insights[:4]],
    }


# ---------- Context builders ----------
def build_activity_context(db: Session, target: date, limit: int = 40) -> str:
    start, end = activity_day_range(target)
    logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
        ActivityLog.duration_seconds >= 20,
    ).order_by(ActivityLog.started_at.asc()).limit(500).all()
    if not logs:
        return ""

    summary = summarize_activity_logs(logs, limit)
    app_lines = [f"- {humanize_app_name(i['app_name'])}: {i['duration_text']}" for i in summary["top_apps"][:8]]
    category_lines = [f"- {i['category']}: {i['duration_text']}" for i in summary["categories"][:8]]
    highlight_lines = [f"- {humanize_context_text(l)}" for l in summary["highlights"]]
    event_lines = [humanize_context_text(r.get("natural_sentence") or r.get("sentence")) for r in summary.get("events", [])[:limit]]
    return (
        "（本地活动感知）威威今天的电脑活动摘要：\n"
        "智能概括：\n" + "\n".join(highlight_lines) +
        "\n\n活动分类：\n" + "\n".join(category_lines) +
        "\n\n主要做事方式：\n" + "\n".join(app_lines) +
        "\n\n合并后的事件段：\n" + "\n".join(event_lines)
    )


def build_daily_summary_context(db: Session, target: date, limit: int = 12, auto_generate: bool = True) -> str:
    date_key = target.isoformat()
    summary = db.query(DailySummary).filter(DailySummary.date == date_key).first()
    if auto_generate and (not summary or not (summary.dayparts or [])):
        summary = generate_daily_summary(db, target)
    if not summary:
        return build_activity_context(db, target, limit=limit)

    highlights = summary.highlights or []
    categories = summary.categories or []
    apps = summary.top_apps or []
    events = summary.events or []
    dayparts = summary.dayparts or []
    comparison = build_activity_comparison(db, target, days=7)
    highlight_lines = [f"- {humanize_context_text(l)}" for l in highlights]
    category_lines = [
        f"- {i.get('category') or i.get('name') or '其他'}: {i.get('duration_text') or format_duration(i.get('duration_seconds') or 0)}"
        for i in categories[:8]
    ]
    app_lines = [
        f"- {humanize_app_name(i.get('app_name') or i.get('name') or '应用')}: {i.get('duration_text') or format_duration(i.get('duration_seconds') or 0)}"
        for i in apps[:8]
    ]
    event_lines = [
        f"- {humanize_context_text(i.get('natural_sentence') or i.get('sentence') or (str(i.get('time') or '') + ' ' + str(i.get('category') or '活动')))}"
        for i in events[:limit]
    ]
    daypart_lines = [
        f"- {humanize_context_text(i.get('summary') or ((i.get('label') or '时段') + '：' + (i.get('duration_text') or '')))}"
        for i in dayparts
    ]
    compare_lines = [f"- {humanize_context_text(l)}" for l in (comparison.get("insights") or [])]
    trends = build_activity_trends(db, target, days=30)
    trend_summary = trends.get("summary") or {}
    trend_lines = [f"- {humanize_context_text(l)}" for l in (trends.get("insights") or [])[:3]]
    if trend_summary:
        trend_lines.append(
            "- " + humanize_context_text(
                f"近30天平均活动 {trend_summary.get('avg_total_text') or '0秒'}，"
                f"最近平均开始 {trend_summary.get('recent_first_start_time') or '--'}，"
                f"最近最长专注约 {trend_summary.get('recent_longest_focus_text') or '--'}。"
            )
        )

    parts = [
        f"（今日总结，已整理）{date_key}，总活动时长 {format_duration(summary.total_seconds or 0)}。",
    ]
    if highlight_lines:
        parts.append("重点观察：\n" + "\n".join(highlight_lines))
    if category_lines:
        parts.append("活动分类：\n" + "\n".join(category_lines))
    if app_lines:
        parts.append("主要做事方式：\n" + "\n".join(app_lines))
    if daypart_lines:
        parts.append("按时段整理：\n" + "\n".join(daypart_lines))
    if compare_lines:
        parts.append("和平时相比：\n" + "\n".join(compare_lines))
    if trend_lines:
        parts.append("近30天趋势：\n" + "\n".join(trend_lines[:4]))
    if event_lines:
        parts.append("生活化事件线索：\n" + "\n".join(event_lines))
    if summary.summary:
        parts.append("可读摘要：\n" + humanize_context_text(summary.summary)[:1600])
    return "\n\n".join(parts)


def build_diary_evidence(db: Session, target: date) -> dict:
    summary = db.query(DailySummary).filter(DailySummary.date == target.isoformat()).first()
    if not summary or not (summary.dayparts or []):
        summary = generate_daily_summary(db, target)

    memories = db.query(PersonalMemory).filter(
        PersonalMemory.active == 1
    ).order_by(PersonalMemory.pinned.desc(), PersonalMemory.updated_at.desc()).limit(5).all()

    # We need activity config - import from shared config module
    from config import load_activity_config

    config = load_activity_config()
    start, end = activity_day_range(target)
    privacy_logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
    ).order_by(ActivityLog.started_at.asc()).limit(1000).all()
    privacy_summary = summarize_privacy_logs(privacy_logs)
    comparison = build_activity_comparison(db, target, days=7)
    trends = build_activity_trends(db, target, days=30)

    events = summary.events or []
    dayparts = summary.dayparts or []
    highlights = summary.highlights or []
    categories = summary.categories or []
    apps = summary.top_apps or []
    display_apps = []
    for item in apps[:5]:
        if not isinstance(item, dict):
            continue
        app_name = item.get("app_name") or item.get("name") or "应用"
        display_apps.append({**item, "display_name": humanize_app_name(app_name)})

    privacy_notes = []
    if config.get("enabled") is False:
        privacy_notes.append("本地活动记录已暂停。")
    else:
        privacy_notes.append("本地活动记录已开启。")
    if config.get("capture_window_titles") is False:
        privacy_notes.append("窗口标题不会被保存。")
    else:
        privacy_notes.append("窗口标题会保存，可用脱敏关键词过滤。")
    if config.get("excluded_apps"):
        privacy_notes.append("已排除：" + "、".join(config.get("excluded_apps", [])[:4]))
    if config.get("title_redact_keywords"):
        privacy_notes.append("脱敏关键词：" + "、".join(config.get("title_redact_keywords", [])[:4]))
    if privacy_summary["has_redacted"]:
        privacy_notes.append(f"今天已有 {privacy_summary['redacted_count']} 条窗口标题被脱敏，约 {privacy_summary['redacted_text']}。")

    photo_entries = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= start, DiaryEntry.created_at < end,
    ).order_by(DiaryEntry.created_at.desc()).limit(12).all()
    photo_items = []
    for entry in photo_entries:
        evidence = entry.evidence or {}
        photos = evidence.get("photos") if isinstance(evidence, dict) else None
        if not isinstance(photos, dict):
            continue
        for item in (photos.get("items") or []):
            if not isinstance(item, dict):
                continue
            if not (item.get("description") or item.get("error")):
                continue
            photo_items.append({
                "entry_id": entry.id,
                "entry_title": entry.title or "今天的日记",
                "image": item.get("image", ""),
                "description": item.get("description", ""),
                "ok": bool(item.get("ok")),
                "skipped": bool(item.get("skipped")),
                "error": item.get("error", ""),
            })
            if len(photo_items) >= 6:
                break
        if len(photo_items) >= 6:
            break

    def memory_to_dict(m):
        return {
            "id": m.id, "category": m.category or "general", "content": m.content,
            "source": m.source or "manual", "confidence": m.confidence or 0.0,
            "pinned": bool(m.pinned), "active": bool(m.active),
            "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
        }

    return {
        "date": target.isoformat(), "source": "daily_summary",
        "activity": {
            "total_seconds": summary.total_seconds or 0,
            "total_text": format_duration(summary.total_seconds or 0),
            "highlights": highlights[:4], "categories": categories[:5],
            "top_apps": display_apps, "events": events[:8],
            "dayparts": dayparts, "event_count": len(events),
        },
        "comparison": comparison,
        "trends": {
            "date": trends.get("date"), "window_days": trends.get("window_days"),
            "active_days": trends.get("active_days"),
            "summary": trends.get("summary") or {},
            "insights": trends.get("insights") or [],
        },
        "memories": [memory_to_dict(m) for m in memories],
        "photos": {"items": photo_items, "count": len(photo_items)},
        "privacy": {
            "enabled": bool(config.get("enabled", True)),
            "capture_window_titles": bool(config.get("capture_window_titles", True)),
            "retention_days": config.get("retention_days", 30),
            "redaction": privacy_summary,
            "notes": privacy_notes,
        },
        "context_preview": build_daily_summary_context(db, target, limit=8, auto_generate=False)[:1800],
    }


def generate_daily_summary(db: Session, target: date) -> DailySummary:
    start, end = activity_day_range(target)
    logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
        ActivityLog.duration_seconds >= 20,
    ).order_by(ActivityLog.started_at.asc()).limit(1000).all()
    summary_data = summarize_activity_logs(logs, limit=80) if logs else {
        "total_seconds": 0, "total_text": "0秒",
        "top_apps": [], "categories": [], "highlights": [],
        "events": [], "dayparts": [], "timeline": [],
    }
    date_key = target.isoformat()
    if summary_data["highlights"]:
        summary_text = "\n".join(summary_data["highlights"])
    else:
        summary_text = "今天还没有足够的活动记录。"
    if summary_data.get("events"):
        event_text = "\n".join(
            (r.get("natural_sentence") or r["sentence"]) for r in summary_data["events"][:12]
        )
        summary_text = summary_text + "\n\n生活化事件线索：\n" + event_text
    if summary_data.get("dayparts"):
        daypart_text = "\n".join(r["summary"] for r in summary_data["dayparts"] if r.get("summary"))
        if daypart_text:
            summary_text = summary_text + "\n\n按时段整理：\n" + daypart_text

    existing = db.query(DailySummary).filter(DailySummary.date == date_key).first()
    if existing:
        existing.summary = summary_text
        existing.highlights = summary_data.get("highlights", [])
        existing.categories = summary_data.get("categories", [])
        existing.top_apps = summary_data.get("top_apps", [])
        existing.events = summary_data.get("events", [])
        existing.dayparts = summary_data.get("dayparts", [])
        existing.total_seconds = summary_data.get("total_seconds", 0)
        existing.source = "activity"
        existing.updated_at = datetime.now()
        db.commit()
        db.refresh(existing)
        return existing

    created = DailySummary(
        date=date_key, summary=summary_text,
        highlights=summary_data.get("highlights", []),
        categories=summary_data.get("categories", []),
        top_apps=summary_data.get("top_apps", []),
        events=summary_data.get("events", []),
        dayparts=summary_data.get("dayparts", []),
        total_seconds=summary_data.get("total_seconds", 0),
        source="activity",
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    return created
