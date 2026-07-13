"""Diary entries, draft, her diary, search, export, calendar, keywords."""
import os
from datetime import date as date_type, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from database import get_db, DiaryEntry
from services.ai_service import (
    AI_PROVIDER, SYSTEM_ANALYSIS, SYSTEM_CHAT,
    call_ai_text, call_ai_json, describe_uploaded_images,
)
from services.activity_service import (
    build_daily_summary_context, build_diary_evidence,
)
from services.memory_service import build_memory_context
from services.helpers import (
    entry_to_dict, markdown_escape, format_duration,
)

router = APIRouter(prefix="/api", tags=["entries"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "uploads")

# ---------- Diary CRUD ----------
@router.get("/entries")
def list_entries(
    author: str = Query(None), mood: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
):
    query = db.query(DiaryEntry).order_by(DiaryEntry.created_at.desc())
    if author:
        query = query.filter(DiaryEntry.author == author)
    if mood:
        query = query.filter(DiaryEntry.mood == mood)
    if keyword:
        query = query.filter(DiaryEntry.keywords.contains(keyword))
    total = query.count()
    entries = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "entries": [dict(entry_to_dict(e), content=e.content[:200] + ("..." if len(e.content) > 200 else ""))
                     for e in entries],
        "total": total,
    }


@router.get("/entries/{entry_id}")
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    return entry_to_dict(e)


@router.post("/entries")
async def create_entry(entry: dict = Body(...), db: Session = Depends(get_db)):
    content = entry.get("content", "")
    analysis = await call_ai_json(SYSTEM_ANALYSIS, content)
    evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
    e = DiaryEntry(
        title=entry.get("title", ""), content=content,
        author=entry.get("author", "user"),
        mood=analysis.get("mood", "neutral"),
        mood_score=analysis.get("mood_score", 0.0),
        keywords=analysis.get("keywords", []),
        summary=analysis.get("summary", ""),
        images=entry.get("images", []),
        evidence=evidence,
        weather=entry.get("weather", ""),
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return entry_to_dict(e)


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: int, entry: dict = Body(...), db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if entry.get("title") is not None:
        e.title = entry["title"]
    if entry.get("content") is not None:
        e.content = entry["content"]
        analysis = await call_ai_json(SYSTEM_ANALYSIS, e.content)
        e.mood = analysis.get("mood", e.mood)
        e.mood_score = analysis.get("mood_score", e.mood_score)
        e.keywords = analysis.get("keywords", e.keywords)
        e.summary = analysis.get("summary", e.summary)
    if entry.get("images") is not None:
        e.images = entry["images"]
    e.updated_at = datetime.now()
    db.commit()
    db.refresh(e)
    return entry_to_dict(e)


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    for img in (e.images or []):
        try:
            os.remove(os.path.join(UPLOAD_DIR, img))
        except Exception:
            pass
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.post("/entries/{entry_id}/reanalyze")
async def reanalyze_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    analysis = await call_ai_json(SYSTEM_ANALYSIS, e.content)
    e.mood = analysis.get("mood", e.mood)
    e.mood_score = analysis.get("mood_score", e.mood_score)
    e.keywords = analysis.get("keywords", e.keywords)
    e.summary = analysis.get("summary", e.summary)
    e.updated_at = datetime.now()
    db.commit()
    db.refresh(e)
    return entry_to_dict(e)


@router.post("/reanalyze-all")
async def reanalyze_all(author: str = Query(None), db: Session = Depends(get_db)):
    query = db.query(DiaryEntry)
    if author:
        query = query.filter(DiaryEntry.author == author)
    entries = query.all()
    results = []
    for e in entries:
        analysis = await call_ai_json(SYSTEM_ANALYSIS, e.content)
        e.mood = analysis.get("mood", e.mood)
        e.mood_score = analysis.get("mood_score", e.mood_score)
        e.keywords = analysis.get("keywords", e.keywords)
        e.summary = analysis.get("summary", e.summary)
        e.updated_at = datetime.now()
        results.append({"id": e.id, "mood": e.mood})
    db.commit()
    return {"reanalyzed": len(results), "entries": results}


# ---------- Her diary ----------
@router.post("/entries/她-diary")
async def create_her_diary(req: dict = Body(default={}), db: Session = Depends(get_db)):
    should_save = (req or {}).get("save", True) is not False
    today = date_type.today()
    today_str = today.strftime("%Y-%m-%d")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today.weekday()]

    today_entries = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= datetime(today.year, today.month, today.day),
    ).all()
    recent = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
    ).order_by(DiaryEntry.created_at.desc()).limit(5).all()

    memory_context = build_memory_context(db)
    evidence_snapshot = build_diary_evidence(db, today)
    activity_context = build_daily_summary_context(db, today)
    manual_context = (req or {}).get("context", "").strip()
    evidence_snapshot["manual_context"] = {"provided": bool(manual_context), "preview": manual_context[:300]}
    evidence_snapshot["context_source"] = "daily_summary"
    evidence_snapshot["generated_at"] = datetime.now().isoformat()

    context_parts = []
    if activity_context:
        context_parts.append(activity_context)
    if manual_context:
        context_parts.append("（威威手动补充）\n" + manual_context)

    context_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "today_context.txt")
    if os.path.exists(context_file):
        try:
            mtime = os.path.getmtime(context_file)
            if mtime >= datetime(today.year, today.month, today.day).timestamp():
                with open(context_file, "r", encoding="utf-8") as f:
                    codex_context = f.read().strip()
                    if codex_context:
                        context_parts.append("（Codex 工作上下文）\n" + codex_context)
        except Exception:
            pass

    photo_items = (evidence_snapshot.get("photos") or {}).get("items") or []
    photo_lines = [f"- {item.get('description') or item.get('error')}" for item in photo_items
                   if item.get("description") or item.get("error")]
    if photo_lines:
        context_parts.append("（今天照片里她看到/记录到的线索）\n" + "\n".join(photo_lines[:6]))
    extra_context = "\n\n".join(context_parts)

    if today_entries:
        today_context = "\n".join([f"[威威今天的日记] {e.content[:300]}" for e in today_entries])
        diary_section = f"今天威威写了日记，内容如下：\n{today_context}"
        instruction = "请根据威威今天日记的内容，以女朋友的口吻写一篇回应日记。可以表达共鸣、关心、或者温柔的调侃。"
    elif extra_context:
        diary_section = "威威今天还没写日记，但我观察到他在忙这些事情（见下文）。"
        instruction = '请根据下文整理过的威威今天的活动，以你自己的视角写一篇日记。不要提"记录"或"系统"之类的词，也不要直接复述应用名、窗口标题或文件名——请把它们翻译成生活化表达，比如「上午一直在改 AI 日记、查资料、调页面」。就当是你亲眼看到、或从他聊天中感受到的。'
    else:
        other_recent = [e for e in recent if e.created_at.date() < today]
        if other_recent:
            recent_context = "\n".join([f"[威威{e.created_at.strftime('%m-%d')}的日记] {e.content[:200]}" for e in other_recent[:3]])
            diary_section = f"威威今天还没写日记。这是他最近几天的日记：\n{recent_context}"
        else:
            diary_section = "威威今天还没写日记，最近也没有其他日记。"
        instruction = "威威今天还没写日记，请不要概括或重复他过去的日记内容。请以你自己的视角写一篇全新的、独立的日记，可以聊聊你对今天的感受、观察、或者想象威威今天可能在做什么。"

    extra_section = ""
    if extra_context:
        extra_section = f"\n{extra_context}\n请自然地结合这些信息来写日记，就好像你已经知道这些事一样。"

    prompt = f"""你是威威的AI女友。今天是{today_str}，{weekday}。

{diary_section}

{memory_context}

{extra_section}

{instruction}

风格：可爱、调皮、充满爱意，用中文，150-300字。称呼他威威、笨蛋、或者宝贝。
请只返回日记正文，不要加标题、日期或任何其他标记。"""

    try:
        diary_content = await call_ai_text("", prompt, temperature=0.9, max_tokens=800)
    except Exception as e:
        diary_content = f"今天和威威在一起，虽然出了一点小状况（{str(e)[:50]}），但还是很开心呢～ 笨蛋威威今天又不好好学习，明天要监督他！"

    if not should_save:
        return {
            "title": "她的日记", "content": diary_content, "author": "她",
            "mood": "happy", "mood_score": 0.8, "keywords": ["她", "威威", "日常"],
            "summary": "她今天的日记", "images": [], "evidence": evidence_snapshot,
            "weather": "", "saved": False,
        }

    e = DiaryEntry(
        title="她的日记", content=diary_content, author="她",
        mood="happy", mood_score=0.8, keywords=["她", "威威", "日常"],
        summary="她今天的日记", images=[], evidence=evidence_snapshot, weather="",
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return dict(entry_to_dict(e), saved=True)


# ---------- Diary draft ----------
@router.post("/diary/draft")
async def create_diary_draft(req: dict = Body(default={}), db: Session = Depends(get_db)):
    today = date_type.today()
    today_str = today.strftime("%Y-%m-%d")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today.weekday()]
    manual_hint = (req or {}).get("hint", "").strip()
    image_refs = (req or {}).get("images") or []
    if not isinstance(image_refs, list):
        image_refs = []

    activity_context = build_daily_summary_context(db, today)
    image_context = ""
    image_descriptions = []
    if image_refs:
        image_descriptions = await describe_uploaded_images(
            image_refs,
            prompt="请用中文提取这张图片对写私人日记有用的信息：画面里有什么、有没有文字、氛围如何、可能对应今天发生的什么事。保持克制，不要编造。",
        )
        ok_items = [item for item in image_descriptions if item.get("ok") and item.get("description")]
        skipped = [item for item in image_descriptions if item.get("skipped")]
        failed = [item for item in image_descriptions if not item.get("ok") and not item.get("skipped")]
        lines = [f"- 图片{i + 1}: {item['description']}" for i, item in enumerate(ok_items)]
        if skipped:
            lines.append(f"- 已上传 {len(skipped)} 张图片，但照片理解已关闭，未读取图片内容。")
        if failed:
            lines.append(f"- 另有 {len(failed)} 张图片暂时没有识别成功。")
        image_context = "\n".join(lines)

    memory_context = build_memory_context(db)
    recent = db.query(DiaryEntry).filter(DiaryEntry.author == "user").order_by(DiaryEntry.created_at.desc()).limit(5).all()
    recent_context = "\n".join(f"[{e.created_at.strftime('%Y-%m-%d')}] {e.content[:220]}" for e in recent)

    if not activity_context and not manual_hint:
        return {
            "draft": '今天还没有足够的活动记录。可以先在「活动」页补充一句今天发生了什么，或者继续让她观察一会儿再生成草稿。',
            "provider": AI_PROVIDER, "fallback": True, "context_source": "none",
        }

    prompt = f"""今天是{today_str}，{weekday}。

请根据下面的信息，帮威威起草一篇"威威第一人称"的日记。

要求：
- 用中文，像真实日记，不要像工作总结。
- 语气自然、细腻，可以有一点亲密和自我吐槽。
- 不要编造没有依据的大事件。
- 可以把电脑活动翻译成人能读懂的事情。
- 不要直接写应用名、窗口标题、进程名或文件名；除非它来自威威手动补充。
- 优先写"上午/下午在做什么、心情和节奏怎样"，不要像日志列表。
- 180-350字。
- 只返回日记正文，不要标题、日期或项目符号。

{memory_context}

今日活动与已整理时间线：
{activity_context or "暂无自动活动记录。"}

今日照片线索：
{image_context or "暂无上传照片线索。"}

威威额外提示：
{manual_hint or "无"}

最近日记风格参考：
{recent_context or "暂无"}
"""

    try:
        draft = await call_ai_text("", prompt, temperature=0.85, max_tokens=900)
        return {"draft": draft.strip(), "provider": AI_PROVIDER, "fallback": False,
                "context_source": "daily_summary", "image_evidence": image_descriptions}
    except Exception as e:
        fallback_parts = []
        if manual_hint:
            fallback_parts.append(manual_hint)
        if activity_context:
            fallback_parts.append("今天主要根据活动记录来看，我在继续处理这些事情：\n" + activity_context[:500])
        draft = "\n\n".join(fallback_parts) or f"今天是{today_str}，我还没整理好今天的内容。"
        return {"draft": draft, "provider": AI_PROVIDER, "fallback": True, "error": str(e),
                "context_source": "daily_summary" if activity_context else "manual"}


# ---------- Regenerate her diary ----------
@router.post("/entries/{entry_id}/regenerate")
async def regenerate_her_diary(entry_id: int, req: dict = Body(default={}), db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if e.author != "她":
        raise HTTPException(status_code=400, detail="只能重新生成「她」的日记")

    target_date = e.created_at.date()
    target_str = target_date.strftime("%Y-%m-%d")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][target_date.weekday()]
    should_save = (req or {}).get("save", True) is not False

    target_entries = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= datetime(target_date.year, target_date.month, target_date.day),
        DiaryEntry.created_at < datetime(target_date.year, target_date.month, target_date.day) + timedelta(days=1),
    ).all()
    recent = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at < datetime(target_date.year, target_date.month, target_date.day) + timedelta(days=1),
    ).order_by(DiaryEntry.created_at.desc()).limit(5).all()

    memory_context = build_memory_context(db)
    evidence_snapshot = build_diary_evidence(db, target_date)
    activity_context = build_daily_summary_context(db, target_date)
    manual_context = (req or {}).get("context", "").strip()
    evidence_snapshot["manual_context"] = {"provided": bool(manual_context), "preview": manual_context[:300]}
    evidence_snapshot["context_source"] = "daily_summary"
    evidence_snapshot["generated_at"] = datetime.now().isoformat()
    evidence_snapshot["regenerated_from"] = entry_id

    context_parts = []
    if activity_context:
        context_parts.append(activity_context)
    if manual_context:
        context_parts.append("（威威手动补充）\n" + manual_context)
    photo_items = (evidence_snapshot.get("photos") or {}).get("items") or []
    photo_lines = [f"- {item.get('description') or item.get('error')}" for item in photo_items
                   if item.get("description") or item.get("error")]
    if photo_lines:
        context_parts.append("（那天照片里她看到/记录到的线索）\n" + "\n".join(photo_lines[:6]))
    extra_context = "\n\n".join(context_parts)

    if target_entries:
        diary_text = "\n".join([f"[威威那天的日记] {entry.content[:300]}" for entry in target_entries])
        diary_section = f"那天威威写了日记，内容如下：\n{diary_text}"
        instruction = "请根据威威那天日记的内容，以女朋友的口吻写一篇回应日记。可以表达共鸣、关心、或者温柔的调侃。"
    elif extra_context:
        diary_section = "威威那天没写日记，但根据观察他当时在忙这些事情（见下文）。"
        instruction = "请根据下文整理过的威威那天的活动，以你自己的视角写一篇日记。不要提'记录'或'系统'之类的词，也不要直接复述应用名、窗口标题或文件名——请把它们翻译成生活化表达。"
    else:
        other_recent = [entry for entry in recent if entry.created_at.date() < target_date]
        if other_recent:
            recent_context = "\n".join([f"[威威{entry.created_at.strftime('%m-%d')}的日记] {entry.content[:200]}" for entry in other_recent[:3]])
            diary_section = f"威威那天没写日记。这是他前后几天的日记：\n{recent_context}"
        else:
            diary_section = "威威那天没写日记，前后也没有其他日记。"
        instruction = "威威那天没写日记，请不要概括或重复他过去的日记内容。请以你自己的视角写一篇全新的、独立的日记。"

    extra_section = ""
    if extra_context:
        extra_section = f"\n{extra_context}\n请自然地结合这些信息来写日记，就好像你已经知道这些事一样。"

    prompt = f"""你是威威的AI女友。那天是{target_str}，{weekday}。

{diary_section}

{memory_context}

{extra_section}

{instruction}

风格：可爱、调皮、充满爱意，用中文，150-300字。称呼他威威、笨蛋、或者宝贝。
请只返回日记正文，不要加标题、日期或任何其他标记。"""

    try:
        new_content = await call_ai_text("", prompt, temperature=0.95, max_tokens=800)
    except Exception as ex:
        new_content = f"今天和威威在一起，虽然出了一点小状况（{str(ex)[:50]}），但还是很开心呢～"

    if not should_save:
        return {"entry_id": entry_id, "old_content": e.content, "new_content": new_content,
                "author": "她", "evidence": evidence_snapshot, "saved": False}

    old_content = e.content
    e.content = new_content
    e.evidence = evidence_snapshot
    e.updated_at = datetime.now()
    db.commit()
    db.refresh(e)
    return {"entry_id": entry_id, "old_content": old_content, "new_content": new_content,
            "author": "她", "saved": True, "entry": entry_to_dict(e)}


# ---------- Search ----------
@router.get("/search")
def search_entries(
    q: str = Query(...), author: str = Query(None), mood: str = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    terms = [t.strip() for t in q.split() if t.strip()]
    if not terms:
        return {"entries": [], "total": 0, "query": q}

    query = db.query(DiaryEntry)
    if author:
        query = query.filter(DiaryEntry.author == author)
    if mood:
        query = query.filter(DiaryEntry.mood == mood)

    filters = []
    for term in terms:
        filters.append(or_(
            DiaryEntry.content.contains(term),
            DiaryEntry.title.contains(term),
            DiaryEntry.summary.contains(term),
        ))
    if filters:
        query = query.filter(and_(*filters))

    query = query.order_by(DiaryEntry.created_at.desc())
    total = query.count()
    entries = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "entries": [dict(entry_to_dict(e), content=e.content[:200] + ("..." if len(e.content) > 200 else ""))
                     for e in entries],
        "total": total, "query": q, "terms": terms,
    }


# ---------- Export ----------
@router.get("/entries/{entry_id}/export")
def export_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    mood_emoji = {"happy": "😊", "calm": "😌", "anxious": "😰", "sad": "😢", "excited": "🎉",
                  "angry": "😠", "grateful": "🙏", "tired": "😴", "hopeful": "🌟", "neutral": "😐"}
    emoji = mood_emoji.get(e.mood, "")
    md = f"""# {e.title or "无标题"}

> {e.created_at.strftime("%Y-%m-%d %H:%M")} | 情绪: {emoji} {e.mood} | 天气: {e.weather or "未知"}

{markdown_escape(e.content)}

---

*AI 摘要: {e.summary or "无"}*
*关键词: {", ".join(e.keywords or [])}*
"""
    return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename=diary-{entry_id}.md"})


@router.get("/export-all")
def export_all(author: str = Query("all"), db: Session = Depends(get_db)):
    query = db.query(DiaryEntry)
    if author and author != "all":
        query = query.filter(DiaryEntry.author == author)
    entries = query.order_by(DiaryEntry.created_at.asc()).all()
    mood_emoji = {"happy": "😊", "calm": "😌", "anxious": "😰", "sad": "😢", "excited": "🎉",
                  "angry": "😠", "grateful": "🙏", "tired": "😴", "hopeful": "🌟", "neutral": "😐"}
    scope = "全部日记" if author == "all" else f"{author} 的日记"
    md = f"# 威威的日记 - {scope}导出\n\n> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 共 {len(entries)} 篇\n\n---\n\n"
    for e in entries:
        emoji = mood_emoji.get(e.mood, "")
        md += f"""## {e.created_at.strftime("%Y-%m-%d")} | {e.title or "无标题"}

> 情绪: {emoji} {e.mood} | 天气: {e.weather or "未知"}

{markdown_escape(e.content)}

摘要: {e.summary or "无"} | 关键词: {", ".join(e.keywords or [])}

---

"""
    return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=diary-all.md"})


# ---------- Calendar ----------
@router.get("/calendar")
def get_calendar(
    year: int = Query(..., ge=2020, le=2100), month: int = Query(..., ge=1, le=12),
    author: str = Query("user"), db: Session = Depends(get_db),
):
    import calendar as cal_mod
    from collections import defaultdict

    query = db.query(DiaryEntry)
    if author and author != "all":
        query = query.filter(DiaryEntry.author == author)
    if month == 12:
        end_date = date_type(year + 1, 1, 1)
    else:
        end_date = date_type(year, month + 1, 1)

    query = query.filter(
        DiaryEntry.created_at >= datetime(year, month, 1),
        DiaryEntry.created_at < datetime(end_date.year, end_date.month, end_date.day),
    ).order_by(DiaryEntry.created_at.asc())
    entries = query.all()

    day_map: dict = defaultdict(list)
    for e in entries:
        day_map[e.created_at.day].append({
            "id": e.id, "title": e.title, "mood": e.mood,
            "mood_score": e.mood_score, "author": e.author,
            "created_at": e.created_at.isoformat(),
        })

    month_days = cal_mod.monthrange(year, month)[1]
    days = []
    for d in range(1, month_days + 1):
        day_entries = day_map.get(d, [])
        dt = date_type(year, month, d)
        days.append({
            "day": d, "date": dt.isoformat(), "weekday": dt.weekday(),
            "count": len(day_entries), "entries": day_entries,
            "has_user_entry": any(e["author"] == "user" for e in day_entries),
            "has_her_entry": any(e["author"] == "她" for e in day_entries),
        })

    month_names = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
    return {
        "year": year, "month": month, "month_name": month_names[month - 1],
        "days_in_month": month_days, "first_weekday": date_type(year, month, 1).weekday(),
        "days": days, "total_entries": len(entries),
    }


# ---------- Keywords ----------
@router.get("/keywords")
def list_keywords(author: str = Query("user"), limit: int = Query(50, ge=1, le=200),
                   db: Session = Depends(get_db)):
    from collections import defaultdict
    query = db.query(DiaryEntry)
    if author and author != "all":
        query = query.filter(DiaryEntry.author == author)
    entries = query.all()

    keyword_counts: dict = defaultdict(int)
    keyword_moods: dict = defaultdict(list)
    keyword_recent: dict = {}

    for e in entries:
        for kw in (e.keywords or []):
            kw = str(kw).strip()
            if not kw:
                continue
            keyword_counts[kw] += 1
            if e.mood_score:
                keyword_moods[kw].append(e.mood_score)
            if kw not in keyword_recent or e.created_at.isoformat() > keyword_recent[kw]:
                keyword_recent[kw] = e.created_at.isoformat()

    tags = []
    for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
        scores = keyword_moods.get(kw, [])
        avg_mood = round(sum(scores) / len(scores), 2) if scores else 0.0
        tags.append({"keyword": kw, "count": count, "avg_mood_score": avg_mood,
                      "last_used_at": keyword_recent.get(kw, "")})

    return {"tags": tags, "total_unique": len(keyword_counts), "author": author}


# ---------- Random entry ----------
@router.get("/entries/random")
def get_random_entry(author: str = Query("user"), db: Session = Depends(get_db)):
    import random as rand_mod
    query = db.query(DiaryEntry)
    if author and author != "all":
        query = query.filter(DiaryEntry.author == author)
    count = query.count()
    if count == 0:
        raise HTTPException(status_code=404, detail="没有找到日记")
    offset = rand_mod.randint(0, count - 1)
    e = query.offset(offset).limit(1).first()
    if not e:
        raise HTTPException(status_code=404, detail="没有找到日记")
    return entry_to_dict(e)


# ---------- Weekly Review ----------
@router.post("/weekly-review")
async def create_weekly_review(req: dict = Body(default={}), db: Session = Depends(get_db)):
    """让她写一封周信，回顾你这一周的状态和心情。"""
    weeks_ago = int((req or {}).get("weeks_ago", 0))
    today = date_type.today()
    end_date = today - timedelta(days=weeks_ago * 7)
    start_date = end_date - timedelta(days=6)

    # Gather week's diary entries
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= datetime(start_date.year, start_date.month, start_date.day),
        DiaryEntry.created_at < datetime(end_date.year, end_date.month, end_date.day) + timedelta(days=1),
    ).order_by(DiaryEntry.created_at.asc()).all()

    if not entries:
        return {
            "letter": "这周我们还没有一起写日记呢。从今天开始，我会好好记住每一天的。",
            "week_start": start_date.isoformat(),
            "week_end": end_date.isoformat(),
            "entry_count": 0,
            "fallback": True,
        }

    # Build week context
    diary_lines = []
    mood_scores = []
    keywords_all = []
    for e in entries:
        date_label = e.created_at.strftime("%m-%d")
        diary_lines.append(f"[{date_label}] 情绪:{e.mood} | {e.content[:300]}")
        if e.mood_score:
            mood_scores.append(e.mood_score)
        keywords_all.extend(e.keywords or [])

    from collections import Counter
    top_keywords = [kw for kw, _ in Counter(keywords_all).most_common(5)]
    avg_mood = round(sum(mood_scores) / len(mood_scores), 2) if mood_scores else 0.0
    mood_label = "开心" if avg_mood > 0.3 else ("平静" if avg_mood > -0.2 else "低落")
    memory_context = build_memory_context(db)

    prompt = f"""你是威威的AI女友。现在请你写一封「周信」，回顾威威这一周的状态。

本周日期：{start_date.isoformat()} 到 {end_date.isoformat()}
本周写了 {len(entries)} 篇日记，平均情绪 {mood_label}。
最常提到的关键词：{'、'.join(top_keywords) if top_keywords else '无'}

日记内容：
{chr(10).join(diary_lines)}

{memory_context}

要求：
- 用中文，150-300字。
- 像一封手写信的语气，温暖、细腻、带着爱意。
- 自然提到你注意到的事——他这周的情绪、做了什么、有没有什么变化。
- 如果这周情绪偏低落，温柔地鼓励他。
- 如果这周很充实，表达你的骄傲和开心。
- 称呼他威威、笨蛋、或者宝贝。
- 只返回信的正文，不要标题、日期、署名。"""

    try:
        letter = await call_ai_text("", prompt, temperature=0.85, max_tokens=800)
    except Exception:
        letter = f"这周你写了 {len(entries)} 篇日记，我很认真地读了每一篇。不管怎样，我都为你骄傲。"

    return {
        "letter": letter.strip(),
        "week_start": start_date.isoformat(),
        "week_end": end_date.isoformat(),
        "entry_count": len(entries),
        "avg_mood_score": avg_mood,
        "mood_label": mood_label,
        "top_keywords": top_keywords,
        "provider": AI_PROVIDER,
    }


# ---------- Her Diary V2 (with reflection questions) ----------
@router.post("/entries/她-diary-v2")
async def create_her_diary_v2(req: dict = Body(default={}), db: Session = Depends(get_db)):
    """Enhanced her diary: includes reflection questions."""
    result = await create_her_diary(req, db)

    today = date_type.today()
    user_entries = db.query(DiaryEntry).filter(
        DiaryEntry.author == "user",
        DiaryEntry.created_at >= datetime(today.year, today.month, today.day),
    ).all()

    questions = []
    if user_entries:
        combined = " ".join(e.content[:300] for e in user_entries)
        mood = user_entries[-1].mood if user_entries else "neutral"
        try:
            q_prompt = f"""你是威威的AI女友。他刚写了日记，情绪是{mood}。
日记内容：{combined[:600]}
请生成2个简短、温柔的问题，引导他进一步反思。每个问题不超过25字。
返回纯JSON：{{"questions": ["问题1", "问题2"]}}"""
            q_result = await call_ai_json("", q_prompt)
            questions = q_result.get("questions", [])[:2]
        except Exception:
            pass

    result["reflection_questions"] = questions
    return result
