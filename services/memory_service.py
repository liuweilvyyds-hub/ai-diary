"""Memory service: candidate generation and context building."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict

from sqlalchemy.orm import Session

from database import ActivityLog, DiaryEntry, PersonalMemory
from services.activity_service import classify_activity, summarize_activity_logs
from services.helpers import format_duration, normalize_memory_text


def build_memory_context(db: Session, limit: int = 30) -> str:
    memories = db.query(PersonalMemory).filter(PersonalMemory.active == 1).order_by(
        PersonalMemory.pinned.desc(),
        PersonalMemory.updated_at.desc(),
    ).limit(limit).all()
    if not memories:
        return ""
    grouped = defaultdict(list)
    for memory in memories:
        grouped[memory.category or "general"].append(memory.content)
    lines = ["（长期个人记忆）她已经知道这些关于威威的稳定信息："]
    for category, items in grouped.items():
        lines.append(f"{category}:")
        for item in items[:8]:
            lines.append(f"- {item}")
    return "\n".join(lines)


def memory_exists(db: Session, content: str) -> bool:
    target = normalize_memory_text(content)
    if not target:
        return False
    memories = db.query(PersonalMemory).filter(PersonalMemory.active == 1).all()
    for memory in memories:
        existing = normalize_memory_text(memory.content)
        if target in existing or existing in target:
            return True
    return False


def add_memory_candidate(
    candidates: List[Dict],
    db: Session,
    category: str,
    content: str,
    reason: str,
    confidence: float = 0.75,
    memory_type: str = "recent",
    evidence_count: int = 1,
    evidence_span_days: int = 1,
):
    content = content.strip()
    if not content or memory_exists(db, content):
        return
    if any(normalize_memory_text(c["content"]) == normalize_memory_text(content) for c in candidates):
        return
    memory_type = "long_term" if memory_type == "long_term" else "recent"
    recommended = memory_type == "long_term" or confidence >= 0.8
    candidates.append({
        "category": category,
        "content": content,
        "reason": reason,
        "confidence": max(0.0, min(confidence, 1.0)),
        "memory_type": memory_type,
        "recommended": recommended,
        "evidence": {
            "count": max(int(evidence_count or 1), 1),
            "span_days": max(int(evidence_span_days or 1), 1),
        },
        "source": "candidate",
    })


def generate_memory_candidates(db: Session, days: int = 7) -> List[Dict]:
    days = max(1, min(days, 30))
    since = datetime.now() - timedelta(days=days)
    candidates: List[Dict] = []

    logs = db.query(ActivityLog).filter(
        ActivityLog.started_at >= since,
        ActivityLog.duration_seconds >= 30,
    ).order_by(ActivityLog.started_at.asc()).limit(2000).all()
    if logs:
        summary = summarize_activity_logs(logs, limit=80)
        for category in summary["categories"][:3]:
            if category["duration_seconds"] >= 300:
                active_dates = {
                    log.started_at.date() for log in logs
                    if classify_activity(log.app_name, log.window_title) == category["category"]
                }
                memory_type = "long_term" if len(active_dates) >= 3 or category["duration_seconds"] >= 7200 else "recent"
                label = "经常" if memory_type == "long_term" else "最近"
                add_memory_candidate(
                    candidates, db, "习惯",
                    f"威威{label}进行{category['category']}，近{days}天累计约{category['duration_text']}。",
                    "根据最近电脑活动分类统计生成。",
                    0.82 if memory_type == "long_term" else 0.68,
                    memory_type,
                    len(active_dates),
                    min(days, max(len(active_dates), 1)),
                )
        for topic in summary["top_topics"][:5]:
            title = topic["title"]
            if topic["duration_seconds"] < 120 or len(title) < 3:
                continue
            topic_dates = {log.started_at.date() for log in logs if title and title in (log.window_title or "")}
            if "ai-diary" in title.lower() or "AI 日记" in title:
                add_memory_candidate(
                    candidates, db, "项目",
                    "ai-diary 是威威正在持续优化的 AI 日记项目。",
                    f"窗口标题多次出现：{title}", 0.85, "long_term",
                    len(topic_dates), min(days, max(len(topic_dates), 1)),
                )
            elif "Codex" in title:
                add_memory_candidate(
                    candidates, db, "工具",
                    "威威会使用 Codex 辅助开发和整理项目。",
                    f"窗口标题多次出现：{title}",
                    0.75, "long_term" if len(topic_dates) >= 2 else "recent",
                    len(topic_dates), min(days, max(len(topic_dates), 1)),
                )
            else:
                add_memory_candidate(
                    candidates, db, "关注",
                    f"威威最近关注过：{title}",
                    "根据最近高频窗口标题生成。",
                    0.6, "recent",
                    len(topic_dates), min(days, max(len(topic_dates), 1)),
                )

    entries = db.query(DiaryEntry).filter(
        DiaryEntry.created_at >= since
    ).order_by(DiaryEntry.created_at.desc()).limit(30).all()
    keyword_counts = defaultdict(int)
    for entry in entries:
        for keyword in (entry.keywords or []):
            if keyword:
                keyword_counts[str(keyword)] += 1
    for keyword, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        if count >= 2:
            add_memory_candidate(
                candidates, db, "关注",
                f"威威最近多次在日记里提到「{keyword}」。",
                "根据最近日记关键词生成。",
                0.72 if count >= 3 else 0.65,
                "long_term" if count >= 4 else "recent",
                count, days,
            )

    return candidates[:12]
