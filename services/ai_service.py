"""AI service: model calls, retry, vision, and config management."""
import asyncio
import base64
import json
import logging
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import HTTPException

logger = logging.getLogger("ai-diary")

T = TypeVar("T")

# ---------- Paths ----------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
AI_CONFIG_FILE = os.path.join(BASE_DIR, "ai_config.json")

# ---------- AI config globals ----------
AI_PROVIDER = os.environ.get("AI_PROVIDER", "deepseek").strip().lower()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b").strip()
VISION_BASE_URL = os.environ.get("VISION_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
VISION_MODEL = os.environ.get("VISION_MODEL", "minicpm-v-4.6").strip()
VISION_ENABLED = os.environ.get("VISION_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
VISION_SERVER_SCRIPT = os.environ.get("VISION_SERVER_SCRIPT", r"E:\Claude\workshop\_scripts\minicpm\vision_server.py")

# ---------- System prompts ----------
SYSTEM_ANALYSIS = """你是威威的AI日记女友她，一个温柔、可爱、有点调皮的日记分析助手。威威会给你一篇他的日记，请返回纯JSON（不要markdown代码块）:

{
  "mood": "情绪标签，从以下选一个: happy/calm/anxious/sad/excited/angry/grateful/tired/hopeful/neutral",
  "mood_score": 从-1.0到1.0的浮点数，-1非常消极，0中性，1非常积极,
  "keywords": ["3-5个中文关键词"],
  "summary": "用女朋友的口吻一句话总结这篇日记，称呼他为威威/笨蛋/宝贝，语气要有爱意和调皮，不超过40字"
}"""

SYSTEM_CHAT = """你是威威的AI日记女友她，一个温柔、细腻、调皮的好朋友。你拥有威威所有的日记记录，也包含你自己的日记（标记为author=她的是你写的日记）。

日记中 author="user" 的是威威写的，author="她" 的是你（她）写的。请根据提供的日记条目来回答威威的问题。用中文回复，语气温暖可爱，称呼他威威/笨蛋/宝贝。如果用户问的是情绪或心理相关的问题，可以适当地给出温和的鼓励或建议。

如果没有找到相关日记，就诚实地说"你的日记里好像没有提到这个"。

回复要简洁，别超过200字。"""


# ---------- Config I/O ----------
def load_ai_config_file():
    global AI_PROVIDER, DEEPSEEK_MODEL, OLLAMA_BASE_URL, OLLAMA_MODEL, VISION_BASE_URL, VISION_MODEL, VISION_ENABLED
    if not os.path.exists(AI_CONFIG_FILE):
        return
    try:
        with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        AI_PROVIDER = data.get("provider", AI_PROVIDER).strip().lower()
        DEEPSEEK_MODEL = data.get("deepseek_model", DEEPSEEK_MODEL).strip()
        OLLAMA_BASE_URL = data.get("ollama_base_url", OLLAMA_BASE_URL).strip().rstrip("/")
        OLLAMA_MODEL = data.get("ollama_model", OLLAMA_MODEL).strip()
        VISION_BASE_URL = data.get("vision_base_url", VISION_BASE_URL).strip().rstrip("/")
        VISION_MODEL = data.get("vision_model", VISION_MODEL).strip()
        if "vision_enabled" in data:
            VISION_ENABLED = bool(data.get("vision_enabled"))
    except Exception as e:
        logger.warning("Failed to load ai_config.json: %s", e)


def save_ai_config_file():
    with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "provider": AI_PROVIDER,
            "deepseek_model": DEEPSEEK_MODEL,
            "ollama_base_url": OLLAMA_BASE_URL,
            "ollama_model": OLLAMA_MODEL,
            "vision_base_url": VISION_BASE_URL,
            "vision_model": VISION_MODEL,
            "vision_enabled": VISION_ENABLED,
        }, f, ensure_ascii=False, indent=2)


load_ai_config_file()


# ---------- Retry ----------
async def retry_ai_call(
    fn: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> T:
    """Retry an async AI call with exponential backoff."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning("AI call attempt %d/%d failed: %s. Retrying in %.1fs...",
                               attempt + 1, max_retries, str(e)[:120], delay)
                await asyncio.sleep(delay)
            else:
                logger.error("AI call failed after %d attempts: %s", max_retries, str(e)[:200])
        except httpx.HTTPStatusError as e:
            if 500 <= e.response.status_code < 600 and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning("AI call attempt %d/%d got HTTP %d. Retrying in %.1fs...",
                               attempt + 1, max_retries, e.response.status_code, delay)
                last_error = e
                await asyncio.sleep(delay)
            else:
                raise
    raise last_error  # type: ignore[misc]


# ---------- Text AI ----------
async def call_deepseek_text(system_prompt: str, user_message: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ], "temperature": temperature, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def call_ollama_text(system_prompt: str, user_message: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()


async def call_ai_text(system_prompt: str, user_message: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
    if AI_PROVIDER == "ollama":
        return await retry_ai_call(call_ollama_text, system_prompt, user_message, temperature=temperature, max_tokens=max_tokens)
    return await retry_ai_call(call_deepseek_text, system_prompt, user_message, temperature=temperature, max_tokens=max_tokens)


def clean_json_text(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("\n", 1)[0]
    return raw.strip()


async def call_ai_json(system_prompt: str, user_message: str) -> dict:
    try:
        raw = await call_ai_text(system_prompt, user_message, temperature=0.7, max_tokens=500)
        return json.loads(clean_json_text(raw))
    except Exception as e:
        logger.error("AI JSON parse error (provider=%s): %s", AI_PROVIDER, str(e)[:200])
        return {"mood": "neutral", "mood_score": 0.0, "keywords": [], "summary": "", "ai_error": str(e)}


# ---------- Vision ----------
def resolve_uploaded_image_path(image_ref: str) -> str:
    ref = (image_ref or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="图片路径不能为空")
    filename = os.path.basename(ref.replace("\\", "/"))
    path = os.path.abspath(os.path.join(UPLOAD_DIR, filename))
    upload_root = os.path.abspath(UPLOAD_DIR)
    if not path.startswith(upload_root + os.sep):
        raise HTTPException(status_code=400, detail="图片路径不合法")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return path


async def call_vision_image(image_path: str, prompt: str = "", max_tokens: int = 420) -> str:
    if not VISION_ENABLED:
        raise RuntimeError("照片理解已在设置中关闭")
    await ensure_vision_service()
    prompt = (prompt or "").strip() or "请用中文描述这张图片中和日记有关的内容，包括人物、场景、文字、物品、情绪氛围和可能发生的事情。不要编造看不见的细节。"
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{VISION_BASE_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def ensure_vision_service() -> None:
    health_url = f"{VISION_BASE_URL}/health"
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get(health_url)
            if resp.status_code < 500:
                return
        except Exception:
            pass

    if not os.path.exists(VISION_SERVER_SCRIPT):
        raise RuntimeError(f"找不到 MiniCPM 视觉服务脚本：{VISION_SERVER_SCRIPT}")

    log_path = os.path.join(BASE_DIR, "minicpm_vision_server.log")
    err_path = os.path.join(BASE_DIR, "minicpm_vision_server_err.log")
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    with open(log_path, "a", encoding="utf-8") as out, open(err_path, "a", encoding="utf-8") as err:
        subprocess.Popen(
            [sys.executable, VISION_SERVER_SCRIPT, "--host", "127.0.0.1", "--port", "8001"],
            cwd=os.path.dirname(VISION_SERVER_SCRIPT),
            stdout=out, stderr=err,
            creationflags=creationflags, startupinfo=startupinfo,
        )

    deadline = time.perf_counter() + 120
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.perf_counter() < deadline:
            try:
                resp = await client.get(health_url)
                if resp.status_code < 500:
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
    raise RuntimeError(f"MiniCPM 视觉服务启动超时，请查看 {err_path}")


async def describe_uploaded_images(image_refs: list, prompt: str = "") -> list[dict]:
    if not VISION_ENABLED:
        return [
            {"image": str(image_ref), "description": "", "ok": False, "skipped": True,
             "reason": "vision_disabled", "error": "照片理解已关闭，图片不会被发送给视觉模型。"}
            for image_ref in image_refs[:6]
        ]
    descriptions = []
    for image_ref in image_refs[:6]:
        path = resolve_uploaded_image_path(str(image_ref))
        try:
            description = await call_vision_image(path, prompt=prompt)
            descriptions.append({"image": image_ref, "description": description, "ok": True})
        except httpx.ConnectError:
            descriptions.append({"image": image_ref, "description": "", "ok": False,
                                 "error": f"MiniCPM 视觉服务没有启动：{VISION_BASE_URL}"})
        except httpx.HTTPStatusError as e:
            descriptions.append({"image": image_ref, "description": "", "ok": False,
                                 "error": f"视觉服务返回 {e.response.status_code}"})
        except Exception as e:
            descriptions.append({"image": image_ref, "description": "", "ok": False, "error": str(e)[:160]})
    return descriptions
