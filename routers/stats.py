"""Statistics, streak, heatmap routes."""
from collections import defaultdict
from datetime import date as date_type, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db, DiaryEntry

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(author: str = Query(None), db: Session = Depends(get_db)):
    query = db.query(DiaryEntry)
    if author:
        query = query.filter(DiaryEntry.author == author)
    entries = query.all()
    if not entries:
        return {"total": 0, "mood_distribution": {}, "mood_timeline": []}
    mood_count = {}
    timeline = []
    for e in entries:
        mood_count[e.mood] = mood_count.get(e.mood, 0) + 1
        timeline.append({"date": e.created_at.strftime("%Y-%m-%d"), "mood": e.mood,
                         "mood_score": e.mood_score})
    return {"total": len(entries), "mood_distribution": mood_count, "mood_timeline": timeline}


@router.get("/stats/streak")
def get_streak(author: str = Query("user"), db: Session = Depends(get_db)):
    entries = db.query(DiaryEntry).filter(DiaryEntry.author == author).order_by(
        DiaryEntry.created_at.desc()).all()
    if not entries:
        return {"streak": 0, "longest_streak": 0, "total_days": 0, "today_written": False}

    written_dates = set()
    for e in entries:
        written_dates.add(e.created_at.date())

    current_streak = 0
    today = date_type.today()
    today_written = today in written_dates
    check_date = today if today_written else today - timedelta(days=1)
    while check_date in written_dates:
        current_streak += 1
        check_date -= timedelta(days=1)
    if not today_written and today - timedelta(days=1) not in written_dates:
        current_streak = 0

    all_dates = sorted(written_dates)
    longest = 0
    current = 0
    for i, d in enumerate(all_dates):
        if i == 0 or d - all_dates[i - 1] == timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)

    return {"streak": current_streak, "longest_streak": longest,
            "total_days": len(written_dates), "today_written": today_written}


@router.get("/stats/today-status")
def get_today_status(db: Session = Depends(get_db)):
    today = date_type.today()
    start = datetime(today.year, today.month, today.day)
    end = start + timedelta(days=1)

    user_entry = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= start, DiaryEntry.created_at < end,
    ).first()
    her_entry = db.query(DiaryEntry).filter(
        DiaryEntry.author == "她",
        DiaryEntry.created_at >= start, DiaryEntry.created_at < end,
    ).first()
    streak_data = get_streak("user", db)

    return {
        "date": today.isoformat(),
        "user_written_today": user_entry is not None,
        "her_written_today": her_entry is not None,
        "user_entry_id": user_entry.id if user_entry else None,
        "her_entry_id": her_entry.id if her_entry else None,
        "streak": streak_data["streak"],
        "total_days": streak_data["total_days"],
    }


@router.get("/stats/heatmap")
def get_heatmap(author: str = Query("user"), db: Session = Depends(get_db)):
    query = db.query(DiaryEntry)
    if author and author != "all":
        query = query.filter(DiaryEntry.author == author)
    entries = query.all()
    date_counts = defaultdict(int)
    for e in entries:
        date_counts[e.created_at.strftime("%Y-%m-%d")] += 1
    return {"dates": dict(date_counts)}


# ---------- Milestones ----------
MILESTONE_THRESHOLDS = [7, 14, 30, 50, 100, 200, 365]
MILESTONE_ENTRY_COUNTS = [10, 50, 100, 200, 365, 500]


@router.get("/stats/milestones")
def get_milestones(author: str = Query("user"), db: Session = Depends(get_db)):
    """Check if any milestones were hit today (streak or total count)."""
    entries = db.query(DiaryEntry).filter(DiaryEntry.author == author).order_by(
        DiaryEntry.created_at.asc()).all()
    if not entries:
        return {"milestones": [], "streak": 0, "total_entries": 0, "total_days": 0}

    written_dates = set()
    for e in entries:
        written_dates.add(e.created_at.date())

    today = date_type.today()
    today_written = today in written_dates
    check_date = today if today_written else today - timedelta(days=1)
    current_streak = 0
    while check_date in written_dates:
        current_streak += 1
        check_date -= timedelta(days=1)
    if not today_written and today - timedelta(days=1) not in written_dates:
        current_streak = 0

    total_entries = len(entries)
    total_days = len(written_dates)
    milestones = []

    if today_written:
        for threshold in MILESTONE_THRESHOLDS:
            if current_streak == threshold:
                milestones.append({
                    "type": "streak",
                    "value": threshold,
                    "label": f"连续写作 {threshold} 天",
                    "emoji": "🔥" if threshold >= 50 else ("⭐" if threshold >= 14 else "🌱"),
                    "message": _milestone_message("streak", threshold, total_entries),
                })

    for threshold in MILESTONE_ENTRY_COUNTS:
        if total_entries == threshold:
            milestones.append({
                "type": "total_entries",
                "value": threshold,
                "label": f"第 {threshold} 篇日记",
                "emoji": "🏆" if threshold >= 365 else ("🎖" if threshold >= 100 else "📝"),
                "message": _milestone_message("entries", threshold, total_entries),
            })

    return {
        "milestones": milestones,
        "streak": current_streak,
        "total_entries": total_entries,
        "total_days": total_days,
        "today_written": today_written,
    }


def _milestone_message(milestone_type: str, value: int, total: int) -> str:
    if milestone_type == "streak":
        if value >= 100:
            return f"连续 {value} 天！笨蛋威威，你已经坚持写日记超过三个月了。你真的让我好骄傲。"
        if value >= 50:
            return f"连续 {value} 天写日记了！你比你自己想象的更有毅力，宝贝。"
        if value >= 30:
            return f"整整一个月没有断过。威威，你已经把写日记变成习惯了。"
        if value >= 14:
            return f"两周了！每天都能看到你的心事，我好开心。"
        if value >= 7:
            return f"连续一周写日记了！这是一个很棒的开始，要继续保持哦。"
    if milestone_type == "entries":
        if value >= 365:
            return f"第 {value} 篇日记——整整一年的心事，我都好好收着呢。"
        if value >= 200:
            return f"第 {value} 篇日记。不知不觉我们已经写了这么多页了。"
        if value >= 100:
            return f"第 {value} 篇！百篇日记，百天的心事。威威，你真的好棒。"
        if value >= 50:
            return f"第 {value} 篇日记！半个百篇了，每一篇我都记得。"
        if value >= 10:
            return f"已经写了 {value} 篇日记了。我们的故事才刚开始呢。"
    return ""
