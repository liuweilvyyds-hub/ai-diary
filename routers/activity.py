"""Activity tracking, comparison, trends, daily summary, evidence, privacy."""
import os
from datetime import date as date_type, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db, ActivityLog, DailySummary, DiaryEntry, PersonalMemory
from services.activity_service import (
    summarize_activity_logs, summarize_activity_for_date,
    build_activity_comparison, build_activity_trends,
    build_activity_context, build_daily_summary_context,
    build_diary_evidence, generate_daily_summary,
    summarize_privacy_logs,
)
from services.helpers import (
    activity_to_dict, daily_summary_to_dict, memory_to_dict,
    activity_day_range, format_duration,
)
from services.cache import activity_cache, summary_cache

router = APIRouter(prefix="/api", tags=["activity"])

# Import config functions from shared module
from config import load_activity_config, save_activity_config

LAST_ACTIVITY_CLEANUP = None
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTIVITY_CONFIG_FILE = os.path.join(BASE_DIR, "activity_config.json")
AI_CONFIG_FILE = os.path.join(BASE_DIR, "ai_config.json")
DEFAULT_ACTIVITY_CONFIG = {
    "enabled": True,
    "capture_window_titles": True,
    "excluded_apps": [],
    "title_redact_keywords": ["password", "密码", "token", "secret", "key"],
    "retention_days": 30,
}


# ---------- Activity log ----------
@router.post("/activity/logs")
def create_activity_log(activity: dict = Body(...), db: Session = Depends(get_db)):
    started_at = activity.get("started_at") or datetime.now()
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)
    ended_at = activity.get("ended_at") or datetime.now()
    if isinstance(ended_at, str):
        ended_at = datetime.fromisoformat(ended_at)
    duration = activity.get("duration_seconds") or int(max((ended_at - started_at).total_seconds(), 0))
    log = ActivityLog(
        app_name=(activity.get("app_name") or "")[:200],
        window_title=activity.get("window_title", ""),
        started_at=started_at, ended_at=ended_at,
        duration_seconds=duration,
        source=(activity.get("source") or "manual")[:50],
        note=activity.get("note", ""),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return activity_to_dict(log)


@router.get("/activity/config")
def get_activity_config():
    return load_activity_config()


@router.post("/activity/config")
def update_activity_config(config_update: dict = Body(...)):
    from pydantic import BaseModel as PydanticBase

    class _Update(PydanticBase):
        enabled: Optional[bool] = None
        capture_window_titles: Optional[bool] = None
        excluded_apps: Optional[List[str]] = None
        title_redact_keywords: Optional[List[str]] = None
        retention_days: Optional[int] = None

    update = _Update(**{k: v for k, v in config_update.items() if v is not None})
    config = load_activity_config()
    data = update.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key in DEFAULT_ACTIVITY_CONFIG:
            config[key] = value
    return save_activity_config(config)


@router.post("/activity/cleanup")
def cleanup_activity_logs(req: dict = Body(default={}), db: Session = Depends(get_db)):
    global LAST_ACTIVITY_CLEANUP
    scope = (req.get("scope") or "expired").strip().lower()
    now = datetime.now()
    if scope == "expired":
        config = load_activity_config()
        cutoff = now - timedelta(days=config["retention_days"])
        query = db.query(ActivityLog).filter(ActivityLog.ended_at < cutoff)
    elif scope == "today":
        start, end = activity_day_range(date_type.today())
        query = db.query(ActivityLog).filter(ActivityLog.started_at < end, ActivityLog.ended_at >= start)
    elif scope == "all":
        query = db.query(ActivityLog)
    else:
        raise HTTPException(status_code=400, detail="scope must be expired, today, or all")
    deleted = query.delete(synchronize_session=False)
    db.commit()
    LAST_ACTIVITY_CLEANUP = {"scope": scope, "deleted": deleted, "at": datetime.now().isoformat(timespec="seconds")}
    return {"ok": True, "scope": scope, "deleted": deleted, "at": LAST_ACTIVITY_CLEANUP["at"]}


@router.get("/activity/today")
def get_today_activity(day: Optional[str] = Query(None), sync: bool = Query(False),
                        db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    cache_key = f"activity_today:{target.isoformat()}"
    if not sync:
        cached = activity_cache.get(cache_key)
        if cached is not None:
            return cached

    # Skip foreground sync (handled by main.py)
    start, end = activity_day_range(target)
    logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
    ).order_by(ActivityLog.started_at.desc()).limit(300).all()
    summary_logs = list(reversed(logs))
    summary = summarize_activity_logs(summary_logs)
    latest_ended_at = max((log.ended_at for log in logs), default=None)
    tracker_status = "inactive"
    age_seconds = None
    if latest_ended_at:
        age_seconds = int((datetime.now() - latest_ended_at).total_seconds())
        tracker_status = "active" if age_seconds <= 180 else "stale"

    result = {
        "date": target.isoformat(),
        "total_seconds": summary["total_seconds"],
        "total_text": summary["total_text"],
        "top_apps": summary["top_apps"][:12],
        "summary": summary,
        "tracker": {
            "status": tracker_status,
            "latest_ended_at": latest_ended_at.isoformat() if latest_ended_at else None,
            "age_seconds": age_seconds,
        },
        "logs": [activity_to_dict(log) for log in logs],
    }
    if not sync:
        activity_cache.set(cache_key, result, ttl=30 if target == date_type.today() else 120)
    return result


@router.get("/activity/context")
def get_activity_context(day: Optional[str] = Query(None), db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
    return {"date": target.isoformat(), "context": build_activity_context(db, target)}


@router.get("/activity/compare")
def get_activity_compare(day: Optional[str] = Query(None), days: int = Query(7, ge=2, le=30),
                          db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
    return build_activity_comparison(db, target, days=days)


@router.get("/activity/trends")
def get_activity_trends(day: Optional[str] = Query(None), days: int = Query(30, ge=7, le=90),
                         db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
    return build_activity_trends(db, target, days=days)


@router.get("/daily-summary")
def get_daily_summary(day: Optional[str] = Query(None), db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

    cache_key = f"daily_summary:{target.isoformat()}"
    cached = summary_cache.get(cache_key)
    if cached is not None:
        return cached

    s = db.query(DailySummary).filter(DailySummary.date == target.isoformat()).first()
    result = {"date": target.isoformat(), "summary": daily_summary_to_dict(s) if s else None}
    summary_cache.set(cache_key, result, ttl=60 if target == date_type.today() else 300)
    return result


@router.post("/daily-summary/generate")
def create_daily_summary(day: Optional[str] = Query(None), db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
    summary = generate_daily_summary(db, target)
    # Invalidate caches
    summary_cache.invalidate(f"daily_summary:{target.isoformat()}")
    activity_cache.invalidate(f"activity_today:{target.isoformat()}")
    return daily_summary_to_dict(summary)


@router.get("/diary/evidence")
def get_diary_evidence(day: Optional[str] = Query(None), db: Session = Depends(get_db)):
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date() if day else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")
    return build_diary_evidence(db, target)


@router.get("/privacy/audit")
def get_privacy_audit(db: Session = Depends(get_db)):
    from services.ai_service import VISION_ENABLED, VISION_MODEL, VISION_BASE_URL

    config = load_activity_config()
    start, end = activity_day_range(date_type.today())
    today_logs = db.query(ActivityLog).filter(
        ActivityLog.started_at < end, ActivityLog.ended_at >= start,
    ).order_by(ActivityLog.started_at.asc()).limit(1000).all()
    redaction = summarize_privacy_logs(today_logs)
    retention_days = int(config.get("retention_days") or 30)
    cutoff = datetime.now() - timedelta(days=retention_days)
    expired_count = db.query(ActivityLog).filter(ActivityLog.ended_at < cutoff).count()
    recent_count = db.query(ActivityLog).filter(ActivityLog.ended_at >= cutoff).count()

    def file_mtime(path):
        try:
            return datetime.fromtimestamp(os.path.getmtime(path))
        except OSError:
            return None

    config_times = [t for t in [file_mtime(ACTIVITY_CONFIG_FILE), file_mtime(AI_CONFIG_FILE)] if t]
    last_effective_at = max(config_times).isoformat(timespec="seconds") if config_times else None

    today = date_type.today()
    start_dt = datetime(today.year, today.month, today.day)
    photo_entries = db.query(DiaryEntry).filter(
        DiaryEntry.created_at >= start_dt, DiaryEntry.created_at < start_dt + timedelta(days=1),
    ).order_by(DiaryEntry.created_at.desc()).all()
    photo_usage = {"entry_count": 0, "item_count": 0, "analyzed_count": 0, "skipped_count": 0,
                    "failed_count": 0, "last_entry_at": None}
    for entry in photo_entries:
        evidence = entry.evidence if isinstance(entry.evidence, dict) else {}
        photos = evidence.get("photos") if isinstance(evidence, dict) else None
        if not isinstance(photos, dict):
            continue
        items = photos.get("items") or []
        if not items:
            continue
        photo_usage["entry_count"] += 1
        if photo_usage["last_entry_at"] is None:
            photo_usage["last_entry_at"] = entry.created_at.isoformat(timespec="seconds")
        for item in items:
            if not isinstance(item, dict):
                continue
            photo_usage["item_count"] += 1
            if item.get("skipped"):
                photo_usage["skipped_count"] += 1
            elif item.get("ok") is False:
                photo_usage["failed_count"] += 1
            else:
                photo_usage["analyzed_count"] += 1

    rules = [
        {"name": "活动记录", "status": "开启" if config.get("enabled", True) else "暂停",
         "detail": "开启后她能整理今天做过什么。" if config.get("enabled", True) else "暂停后不会继续记录电脑活动。"},
        {"name": "窗口标题", "status": "记录" if config.get("capture_window_titles", True) else "不记录",
         "detail": "用于更准确理解任务内容。" if config.get("capture_window_titles", True) else "只保存应用名称，减少细节暴露。"},
        {"name": "标题脱敏", "status": f"{len(config.get('title_redact_keywords') or [])} 个关键词",
         "detail": "、".join((config.get("title_redact_keywords") or [])[:6]) or "暂无关键词"},
        {"name": "排除应用", "status": f"{len(config.get('excluded_apps') or [])} 个应用",
         "detail": "、".join((config.get("excluded_apps") or [])[:6]) or "暂无排除项"},
        {"name": "活动保留", "status": f"{retention_days} 天",
         "detail": f"当前保留期内约 {recent_count} 条，过期待清理 {expired_count} 条。"},
        {"name": "最近生效", "status": last_effective_at.replace("T", " ") if last_effective_at else "暂无",
         "detail": "隐私和模型配置最近一次保存时间。"},
        {"name": "照片理解", "status": "开启" if VISION_ENABLED else "关闭",
         "detail": "开启时上传照片可交给本地 MiniCPM 识别。" if VISION_ENABLED else "关闭时图片只保存，不会被视觉模型读取。"},
        {"name": "照片调用", "status": f"{photo_usage['analyzed_count']} 次识别",
         "detail": f"今天保存 {photo_usage['item_count']} 张照片线索，跳过 {photo_usage['skipped_count']} 张，失败 {photo_usage['failed_count']} 张。"},
    ]
    return {
        "date": date_type.today().isoformat(), "rules": rules,
        "last_effective_at": last_effective_at, "redaction": redaction,
        "retention": {"days": retention_days, "cutoff": cutoff.isoformat(),
                       "recent_count": recent_count, "expired_count": expired_count},
        "cleanup": {"last": LAST_ACTIVITY_CLEANUP},
        "vision": {"enabled": VISION_ENABLED, "model": VISION_MODEL, "base_url": VISION_BASE_URL},
        "photo_usage": photo_usage,
    }
