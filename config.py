"""Shared configuration: activity config loaded from disk."""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIVITY_CONFIG_FILE = os.path.join(BASE_DIR, "activity_config.json")

DEFAULT_ACTIVITY_CONFIG = {
    "enabled": True,
    "capture_window_titles": True,
    "excluded_apps": [],
    "title_redact_keywords": ["password", "密码", "token", "secret", "key"],
    "retention_days": 30,
}


def load_activity_config():
    config = dict(DEFAULT_ACTIVITY_CONFIG)
    if os.path.exists(ACTIVITY_CONFIG_FILE):
        try:
            with open(ACTIVITY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update({k: data[k] for k in DEFAULT_ACTIVITY_CONFIG if k in data})
        except Exception:
            pass
    config["enabled"] = bool(config.get("enabled", True))
    config["capture_window_titles"] = bool(config.get("capture_window_titles", True))
    config["excluded_apps"] = [str(x).strip() for x in (config.get("excluded_apps") or []) if str(x).strip()]
    config["title_redact_keywords"] = [str(x).strip() for x in (config.get("title_redact_keywords") or []) if str(x).strip()]
    config["retention_days"] = max(1, min(int(config.get("retention_days") or 30), 365))
    return config


def save_activity_config(config: dict):
    clean = dict(DEFAULT_ACTIVITY_CONFIG)
    clean.update({k: config[k] for k in DEFAULT_ACTIVITY_CONFIG if k in config})
    clean["excluded_apps"] = [str(x).strip() for x in (clean.get("excluded_apps") or []) if str(x).strip()]
    clean["title_redact_keywords"] = [str(x).strip() for x in (clean.get("title_redact_keywords") or []) if str(x).strip()]
    clean["retention_days"] = max(1, min(int(clean.get("retention_days") or 30), 365))
    with open(ACTIVITY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return clean
