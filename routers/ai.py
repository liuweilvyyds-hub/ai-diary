"""AI config, chat, vision, weather, upload, backup routes."""
import json
import os
import uuid
import shutil
import tempfile
import time
import base64
import mimetypes
from datetime import date as date_type, datetime, timedelta
from collections import OrderedDict
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy.orm import Session

from database import get_db, DiaryEntry, PersonalMemory
from services.ai_service import (
    AI_PROVIDER, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    OLLAMA_BASE_URL, OLLAMA_MODEL, VISION_BASE_URL, VISION_MODEL, VISION_ENABLED,
    SYSTEM_CHAT,
    call_ai_text, call_vision_image, ensure_vision_service,
    resolve_uploaded_image_path, load_ai_config_file, save_ai_config_file,
)
from services.memory_service import build_memory_context
from services.helpers import (
    entry_to_dict, memory_to_dict, daily_summary_to_dict,
    activity_to_dict, normalize_memory_text,
)

router = APIRouter(prefix="/api", tags=["ai"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

from pydantic import BaseModel as PydanticBase


# ---------- Upload ----------
@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片文件")
    ext = os.path.splitext(file.filename or ".jpg")[1] or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": name, "url": f"/static/uploads/{name}"}


# ---------- Vision ----------
class VisionAnalyzeRequest(PydanticBase):
    image: str
    prompt: str = ""


@router.post("/vision/analyze")
async def analyze_image(req: VisionAnalyzeRequest):
    path = resolve_uploaded_image_path(req.image)
    try:
        description = await call_vision_image(path, prompt=req.prompt)
        return {"ok": True, "image": req.image, "description": description,
                "model": VISION_MODEL, "base_url": VISION_BASE_URL}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"MiniCPM 视觉服务没有启动：{VISION_BASE_URL}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视觉识别失败：{e}")


@router.post("/vision/test")
async def test_vision_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片文件")
    ext = os.path.splitext(file.filename or ".jpg")[1] or ".jpg"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        description = await call_vision_image(
            tmp_path,
            prompt="请用中文简洁描述这张图片里和日记有关的内容，包括可见文字、人物、物品、场景和氛围。不要编造。",
        )
        return {"ok": True, "description": description, "model": VISION_MODEL, "base_url": VISION_BASE_URL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"视觉测试失败：{e}")
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@router.get("/vision/status")
async def get_vision_status():
    started = time.perf_counter()
    if not VISION_ENABLED:
        return {"ok": False, "enabled": False, "model": VISION_MODEL,
                "base_url": VISION_BASE_URL, "elapsed_ms": 0, "status": "disabled",
                "error": "照片理解已关闭"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{VISION_BASE_URL}/health")
            resp.raise_for_status()
            data = resp.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": True, "enabled": True, "model": VISION_MODEL, "base_url": VISION_BASE_URL,
                "elapsed_ms": elapsed_ms, "device": data.get("device", ""),
                "status": data.get("status", "ok")}
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "enabled": True, "model": VISION_MODEL, "base_url": VISION_BASE_URL,
                "elapsed_ms": elapsed_ms, "error": str(e)[:300]}


@router.post("/vision/start")
async def start_vision_service():
    started = time.perf_counter()
    if not VISION_ENABLED:
        return {"ok": False, "enabled": False, "model": VISION_MODEL,
                "base_url": VISION_BASE_URL, "elapsed_ms": 0, "status": "disabled",
                "error": "照片理解已关闭"}
    try:
        await ensure_vision_service()
        status = await get_vision_status()
        status["started"] = True
        status["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return status
    except Exception as e:
        return {"ok": False, "enabled": True, "model": VISION_MODEL, "base_url": VISION_BASE_URL,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "started": False, "error": str(e)[:500]}


# ---------- Weather ----------
@router.get("/weather")
async def get_weather(city: str = Query("shanghai")):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://wttr.in/{city}?format=j1")
            resp.raise_for_status()
            w = resp.json()
            current = w.get("current_condition", [{}])[0]
            temp = current.get("temp_C", "?")
            code = current.get("weatherCode", "113")
            weather_icons = {
                "113": "☀️ 晴", "116": "⛅ 多云", "119": "☁️ 阴", "122": "☁️ 阴",
                "176": "🌦️ 阵雨", "200": "⛈️ 雷阵雨", "263": "🌧️ 小雨", "266": "🌧️ 小雨",
                "293": "🌧️ 小雨", "296": "🌧️ 小雨", "299": "🌧️ 中雨", "302": "🌧️ 中雨",
                "305": "🌧️ 大雨", "308": "🌧️ 大雨", "353": "🌧️ 阵雨", "356": "🌧️ 大雨",
                "359": "🌧️ 暴雨", "386": "⛈️ 雷阵雨", "389": "⛈️ 雷暴",
            }
            desc = weather_icons.get(code, f"🌤️ {current.get('weatherDesc', [{}])[0].get('value', '未知')}")
            return {"weather": f"{desc} {temp}°C", "temp": temp,
                    "humidity": current.get("humidity", "?"), "city": city}
    except Exception as e:
        return {"weather": "☀️ 未知", "temp": "?", "humidity": "?", "city": city, "error": str(e)}


# ---------- Chat (multi-turn) ----------
_chat_sessions: OrderedDict = OrderedDict()
MAX_SESSIONS = 100
MAX_HISTORY_PER_SESSION = 6


def _get_or_create_session(session_id: str) -> list:
    if session_id not in _chat_sessions:
        if len(_chat_sessions) >= MAX_SESSIONS:
            _chat_sessions.popitem(last=False)
        _chat_sessions[session_id] = []
    _chat_sessions.move_to_end(session_id)
    return _chat_sessions[session_id]


@router.post("/chat")
async def chat_with_diary(req: dict, db: Session = Depends(get_db)):
    question = req.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="question required")
    entries = db.query(DiaryEntry).order_by(DiaryEntry.created_at.desc()).limit(30).all()
    context = "\n---\n".join(
        f"[{e.created_at.strftime('%Y-%m-%d')}] 情绪:{e.mood} | {e.content[:300]}" for e in entries
    )
    memory_context = build_memory_context(db)

    session_id = (req or {}).get("session_id", "default")
    clear = (req or {}).get("clear_history", False)
    history = _get_or_create_session(session_id)
    if clear:
        history.clear()

    history_block = ""
    if history:
        history_lines = []
        for msg in history[-MAX_HISTORY_PER_SESSION:]:
            role_label = "威威" if msg["role"] == "user" else "她"
            history_lines.append(f"{role_label}：{msg['content']}")
        history_block = "对话历史：\n" + "\n".join(history_lines) + "\n\n"

    user_msg = f"{history_block}{memory_context}\n\n用户的日记记录:\n{context}\n\n用户的问题: {question}"
    try:
        reply = await call_ai_text(SYSTEM_CHAT, user_msg, temperature=0.7, max_tokens=400)
        history.append({"role": "user", "content": question, "ts": datetime.now().isoformat()})
        history.append({"role": "assistant", "content": reply, "ts": datetime.now().isoformat()})
        if len(history) > MAX_HISTORY_PER_SESSION * 2:
            history[:] = history[-MAX_HISTORY_PER_SESSION * 2:]
        return {"reply": reply, "provider": AI_PROVIDER, "session_id": session_id,
                "history_length": len(history)}
    except Exception as e:
        if AI_PROVIDER == "ollama":
            return {"reply": f"本地模型暂时没连上：{str(e)[:80]}。先确认 Ollama 正在运行，并且已经拉取 {OLLAMA_MODEL}。",
                    "provider": AI_PROVIDER}
        return {"reply": "请设置 DEEPSEEK_API_KEY 环境变量来启用 AI 对话功能。", "provider": AI_PROVIDER}


# ---------- AI Config ----------
@router.get("/ai/config")
def get_ai_config():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    return {
        "provider": AI_PROVIDER,
        "deepseek": {"has_key": bool(key), "model": DEEPSEEK_MODEL, "base_url": DEEPSEEK_BASE_URL},
        "ollama": {"model": OLLAMA_MODEL, "base_url": OLLAMA_BASE_URL},
        "vision": {"model": VISION_MODEL, "base_url": VISION_BASE_URL, "enabled": VISION_ENABLED},
    }


class AIConfigUpdate(PydanticBase):
    provider: Optional[str] = None
    deepseek_model: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    vision_model: Optional[str] = None
    vision_base_url: Optional[str] = None
    vision_enabled: Optional[bool] = None


@router.post("/ai/config")
def update_ai_config(config: AIConfigUpdate):
    import services.ai_service as ai_svc

    if config.provider is not None:
        provider = config.provider.strip().lower()
        if provider not in {"deepseek", "ollama"}:
            raise HTTPException(status_code=400, detail="provider must be deepseek or ollama")
        ai_svc.AI_PROVIDER = provider
    if config.deepseek_model is not None and config.deepseek_model.strip():
        ai_svc.DEEPSEEK_MODEL = config.deepseek_model.strip()
    if config.ollama_model is not None and config.ollama_model.strip():
        ai_svc.OLLAMA_MODEL = config.ollama_model.strip()
    if config.ollama_base_url is not None and config.ollama_base_url.strip():
        ai_svc.OLLAMA_BASE_URL = config.ollama_base_url.strip().rstrip("/")
    if config.vision_model is not None and config.vision_model.strip():
        ai_svc.VISION_MODEL = config.vision_model.strip()
    if config.vision_base_url is not None and config.vision_base_url.strip():
        ai_svc.VISION_BASE_URL = config.vision_base_url.strip().rstrip("/")
    if config.vision_enabled is not None:
        ai_svc.VISION_ENABLED = bool(config.vision_enabled)
    save_ai_config_file()
    return get_ai_config()


@router.post("/ai/test")
async def test_ai_config():
    started = time.perf_counter()
    model = OLLAMA_MODEL if AI_PROVIDER == "ollama" else DEEPSEEK_MODEL
    try:
        reply = await call_ai_text(
            "你是 AI 日记的模型连通性测试助手。请只回复一句简短中文。",
            "请回复：模型连接正常。", temperature=0.2, max_tokens=60,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": True, "provider": AI_PROVIDER, "model": model, "elapsed_ms": elapsed_ms, "reply": reply[:200]}
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "provider": AI_PROVIDER, "model": model, "elapsed_ms": elapsed_ms, "error": str(e)[:300]}


# ---------- Debug ----------
@router.get("/debug/env")
def debug_env():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    return {"has_key": bool(key), "key_len": len(key), "key_prefix": key[:10] if key else "empty",
            "ai_provider": AI_PROVIDER}


# ---------- Backup / Restore ----------
@router.get("/backup/export")
def backup_export(db: Session = Depends(get_db)):
    entries = db.query(DiaryEntry).order_by(DiaryEntry.created_at.asc()).all()
    memories = db.query(PersonalMemory).order_by(PersonalMemory.created_at.asc()).all()
    from database import DailySummary, ActivityLog
    summaries = db.query(DailySummary).order_by(DailySummary.created_at.asc()).all()
    activity_logs = db.query(ActivityLog).order_by(ActivityLog.started_at.asc()).limit(5000).all()

    data = {
        "version": "1.0", "exported_at": datetime.now().isoformat(),
        "entries": [entry_to_dict(e) for e in entries],
        "memories": [memory_to_dict(m) for m in memories],
        "daily_summaries": [daily_summary_to_dict(s) for s in summaries],
        "activity_logs": [activity_to_dict(log) for log in activity_logs],
        "stats": {"total_entries": len(entries), "total_memories": len(memories),
                   "total_summaries": len(summaries), "total_activity_logs": len(activity_logs)},
    }
    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return PlainTextResponse(
        content=json_str, media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=ai-diary-backup-{date_type.today().isoformat()}.json"},
    )


class BackupImportRequest(PydanticBase):
    entries: list = []
    memories: list = []
    merge: bool = True


@router.post("/backup/import")
def backup_import(req: BackupImportRequest, db: Session = Depends(get_db)):
    imported = {"entries": 0, "memories": 0, "skipped_entries": 0, "skipped_memories": 0}

    if req.entries:
        existing_titles = set()
        if req.merge:
            existing = db.query(DiaryEntry.title, DiaryEntry.created_at).all()
            existing_titles = {(e.title, e.created_at.strftime("%Y-%m-%d %H:%M")) for e in existing}
        for item in req.entries:
            key = (item.get("title", ""), item.get("created_at", ""))
            if req.merge and key in existing_titles:
                imported["skipped_entries"] += 1
                continue
            try:
                created_at = datetime.fromisoformat(item.get("created_at", "")) if item.get("created_at") else datetime.now()
            except (ValueError, TypeError):
                created_at = datetime.now()
            e = DiaryEntry(
                title=item.get("title", ""), content=item.get("content", ""),
                mood=item.get("mood", "neutral"), mood_score=float(item.get("mood_score", 0) or 0),
                keywords=item.get("keywords") or [], summary=item.get("summary", ""),
                images=item.get("images") or [], evidence=item.get("evidence") or {},
                author=item.get("author", "user"), weather=item.get("weather", ""),
                created_at=created_at, updated_at=datetime.now(),
            )
            db.add(e)
            imported["entries"] += 1

    if req.memories:
        existing_contents = set()
        if req.merge:
            existing = db.query(PersonalMemory.content).all()
            existing_contents = {normalize_memory_text(e[0]) for e in existing}
        for item in req.memories:
            content = item.get("content", "").strip()
            if not content:
                continue
            if req.merge and normalize_memory_text(content) in existing_contents:
                imported["skipped_memories"] += 1
                continue
            m = PersonalMemory(
                category=item.get("category", "general"), content=content,
                source=item.get("source", "backup"), confidence=float(item.get("confidence", 1.0) or 1.0),
                pinned=1 if item.get("pinned") else 0, active=1,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            db.add(m)
            imported["memories"] += 1

    db.commit()
    return {"ok": True, **imported}


# ---------- Static files ----------
@router.get("/images/{filename}")
def serve_image(filename: str):
    return FileResponse(os.path.join(UPLOAD_DIR, filename))
