"""Local health checks for the AI Diary app.

The default checks are read-only and avoid calling text generation APIs. Use
--draft to also exercise /api/diary/draft, which may call the configured model.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    warning: bool = False


class HealthClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method.upper())
        with urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def upload_image(self, path: str, field_name: str = "file") -> Any:
        boundary = f"----ai-diary-health-{uuid.uuid4().hex}"
        filename = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as image_file:
            payload = image_file.read()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {mime}\r\n\r\n".encode("ascii"),
                payload,
                b"\r\n",
                f"--{boundary}--\r\n".encode("ascii"),
            ]
        )
        req = Request(
            f"{self.base_url}/api/vision/test",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def pass_check(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=True, detail=detail)


def fail_check(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=False, detail=detail)


def warn_check(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=True, detail=detail, warning=True)


def require_keys(name: str, value: dict[str, Any], keys: list[str]) -> CheckResult | None:
    missing = [key for key in keys if key not in value]
    if missing:
        return fail_check(name, f"missing keys: {', '.join(missing)}")
    return None


def check_frontend_contracts() -> list[CheckResult]:
    results: list[CheckResult] = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(root, "static", "index.html")
    try:
        with open(index_path, "r", encoding="utf-8") as html_file:
            html = html_file.read()
    except OSError as exc:
        return [fail_check("Frontend contracts", f"cannot read static/index.html: {exc}")]

    match = re.search(
        r"function renderReviewEvidence\(entry\) \{(?P<body>[\s\S]*?)\n    \}\n    window\.renderReviewEvidence",
        html,
    )
    if not match:
        results.append(fail_check("Review evidence comparison", "renderReviewEvidence export block was not found"))
        return results

    body = match.group("body")
    required_tokens = [
        "evidence.comparison || {}",
        "comparison.insights",
        "comparison.rhythm",
        "evidence.trends || {}",
        "trends.insights",
        "longest_focus_text",
        "和平时相比",
        "节奏：",
        "近30天：",
        "旧版她写的日记",
        "没有保存活动证据快照",
    ]
    missing_tokens = [token for token in required_tokens if token not in body]
    if missing_tokens:
        results.append(
            fail_check(
                "Review evidence comparison",
                f"renderer is missing comparison support tokens: {', '.join(missing_tokens)}",
            )
        )
    else:
        results.append(pass_check("Review evidence comparison", "review evidence renderer shows comparison insights"))

    dashboard_tokens = [
        "loadActivityCompare(diaryHint)",
        "loadActivityTrendsForDashboard()",
        "renderDashboardActivityTrend",
        "dashboardTrendChart",
        "dashboard-trend-guide",
        "eventPoints",
        "切换频率",
        "/api/activity/trends?days=30",
        "dashboardSummary",
        "data.rhythm",
        "rhythm.insights",
        "rhythmInsights[0] || insights[0]",
        "近 30 天",
        "和平时相比",
    ]
    missing_dashboard_tokens = [token for token in dashboard_tokens if token not in html]
    if missing_dashboard_tokens:
        results.append(
            fail_check(
                "Dashboard activity comparison",
                f"dashboard compare contract is missing tokens: {', '.join(missing_dashboard_tokens)}",
            )
        )
    else:
        results.append(pass_check("Dashboard activity comparison", "dashboard observation includes activity comparison"))

    her_evidence_tokens = [
        "const trends = data.trends || {}",
        "trendInsights",
        "a.display_name || a.app_name",
        "e.display_name || e.app_name",
        "l.display_name || l.app_name",
        "l.display_title || l.window_title",
        "herEvidenceActivity",
        "近30天：",
        "her-letter-bouquet-ref.png",
        "her-letter-stamp-ref.png",
        "function renderHerObserveDetails",
        "__herObserveState",
        "desktop-title-text",
        "mobile-title-text",
        "herMoodScore",
        "herKeywords",
        "her-observe-line",
        "her-app-row",
        "herObserveSummary",
        "情绪标签",
        "情绪指数",
        "关键词",
        "her-memory-pill",
    ]
    missing_her_tokens = [token for token in her_evidence_tokens if token not in html]
    if missing_her_tokens:
        results.append(
            fail_check(
                "Her evidence trends",
                f"her evidence renderer is missing trend tokens: {', '.join(missing_her_tokens)}",
            )
        )
    else:
        results.append(pass_check("Her evidence trends", "her diary evidence card shows long-term trends"))

    layout_tokens = [
        ".app {",
        "max-width: none;",
        "margin: 0;",
        ".main {",
        "max-width: 1394px;",
        "font-size: 28px;",
        "showPage(\"dashboard\")",
        "if ($(\"statActivity\"))",
        'id="page-dashboard"',
        'id="page-write"',
        'id="page-her"',
        'id="page-review"',
        'id="page-activity"',
        'id="page-memory"',
        'id="page-settings"',
        "dashboard-grid",
        "review-grid",
        "memory-layout",
        "settings-layout",
        "her-page-stack",
    ]
    missing_layout_tokens = [token for token in layout_tokens if token not in html]
    if missing_layout_tokens:
        results.append(
            fail_check(
                "Frontend layout contract",
                f"layout contract is missing tokens: {', '.join(missing_layout_tokens)}",
            )
        )
    elif 'showPage("write")' in html:
        results.append(fail_check("Frontend layout contract", "default page regressed to write page"))
    else:
        results.append(pass_check("Frontend layout contract", "core pages keep reference-style layout anchors"))

    visible_action_tokens = [
        "function exportSelectedReview()",
        "/api/entries/${currentReviewEntryId}/export",
        "document.querySelector(\".review-export\")?.addEventListener(\"click\", exportSelectedReview)",
        "function closeReviewDetail()",
        'class="review-close-btn"',
        'onclick="closeReviewDetail()"',
        "function displayEntryTitle(entry)",
        "const displayTitle = displayEntryTitle(e)",
        "$(\"reviewDetailTitle\").textContent = displayEntryTitle(entry)",
        'class="review-item ${authorClass}${active}"',
        "const authorClass = isHerAuthor(e.author)",
        "const moodClassMap = {",
        "function regenerateHerDiary()",
        "onclick=\"regenerateHerDiary()\"",
        "function saveHerLetter()",
        "onclick=\"saveHerLetter()\"",
        "currentHerEntryId",
        "currentReviewEntryId",
        "currentHerDraftEvidence",
        "save: false",
        "确认后可以保存为她的日记",
        "function removeUploadedImage(imageUrl, node)",
        "uploadedImages = uploadedImages.filter",
        "preview-remove",
        "function initSamplePreviewRemoval()",
        "function initDiaryImageDropzone()",
        "drag-over",
        "event.dataTransfer?.files",
        "点击或拖拽",
        "function editMemory(id)",
        "onclick=\"editMemory",
        "function dismissCandidateMemory(index)",
        "onclick=\"dismissCandidateMemory",
        "candidate-table-head",
        "证据次数",
        "candidate-evidence",
        "memory-quote-card",
        'id="memoryStatus"',
        "已忽略这条候选",
        "function renderMemoryCandidates(candidates)",
        "function toggleCandidateList()",
        "function scrollToMemoryCandidates()",
        "memoryCandidateExpanded",
        "candidate-list-footer",
        "待确认候选",
        "data-provider-tab=\"deepseek\"",
        "data-settings-focus=\"vision\"",
        "settings-hidden-fields",
        'id="ollamaModel"',
        'id="ollamaUrl"',
        "function updateManualActivityCount()",
        'id="manualActivityCount"',
        'id="activityActionStatus"',
        'maxlength="200"',
        "function cleanupExpired()",
        'onclick="cleanupExpired()"',
        'body: JSON.stringify({ scope: "expired" })',
        "function syncPrivacySwitches()",
        "function togglePrivacySelect(selectId)",
        'id="activityEnabledSwitch"',
        'id="captureTitlesSwitch"',
        'onclick="togglePrivacySelect(\'activityEnabled\')"',
        'onclick="togglePrivacySelect(\'captureTitles\')"',
    ]
    missing_action_tokens = [token for token in visible_action_tokens if token not in html]
    if missing_action_tokens:
        results.append(
            fail_check(
                "Visible UI actions",
                f"visible action implementations are missing tokens: {', '.join(missing_action_tokens)}",
            )
        )
    elif "本地文本模型 Ollama" in html or 'data-provider-tab="ollama"' in html:
        results.append(
            fail_check(
                "Visible UI actions",
                "settings page should keep Ollama compatibility hidden and must not show an Ollama card/tab",
            )
        )
    else:
        results.append(pass_check("Visible UI actions", "visible export and her-diary buttons have concrete handlers"))

    onclick_functions = sorted(
        {
            name
            for handler in re.findall(r'onclick="([^"]+)"', html)
            for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", handler)
        }
    )
    builtin_call_names = {"Number", "String", "Boolean", "Math", "Date", "JSON"}
    defined_functions = set(re.findall(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", html))
    defined_functions.update(re.findall(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", html))
    missing_onclick = [
        name
        for name in onclick_functions
        if name not in defined_functions and name not in builtin_call_names
    ]
    delegated_bindings = [
        ('id="btnSave"', '$("btnSave").addEventListener("click", saveEntry)'),
        ('id="btnDraft"', '$("btnDraft").addEventListener("click", draftEntry)'),
        ('id="btnHer"', '$("btnHer").addEventListener("click", writeHerDiary)'),
        ('id="themeToggle"', '$("themeToggle")?.addEventListener("click", toggleTheme)'),
        ('review-export', 'document.querySelector(".review-export")?.addEventListener("click", exportSelectedReview)'),
        ('id="imageInput"', '$("imageInput").addEventListener("change"'),
        ('id="manualActivity"', '$("manualActivity")?.addEventListener("input", updateManualActivityCount)'),
    ]
    missing_bindings = [
        f"{selector} -> {binding}"
        for selector, binding in delegated_bindings
        if selector not in html or binding not in html
    ]
    if missing_onclick or missing_bindings:
        details = []
        if missing_onclick:
            details.append(f"onclick functions without definitions: {', '.join(missing_onclick)}")
        if missing_bindings:
            details.append(f"missing delegated bindings: {'; '.join(missing_bindings)}")
        results.append(fail_check("Frontend action wiring audit", " | ".join(details)))
    else:
        results.append(
            pass_check(
                "Frontend action wiring audit",
                f"{len(onclick_functions)} onclick handlers and {len(delegated_bindings)} delegated bindings are wired",
            )
        )

    review_filter_tokens = [
        "/api/entries?page_size=100",
        "const moodAliases = {",
        "\"开心\": [\"happy\"",
        "\"难过\": [\"sad\", \"anxious\", \"angry\"",
        "const moodLabel = (mood) =>",
        "[\"她\", \"北落师门\"].includes",
    ]
    missing_review_filter_tokens = [token for token in review_filter_tokens if token not in html]
    if missing_review_filter_tokens:
        results.append(
            fail_check(
                "Review filters",
                f"review filters are missing tokens: {', '.join(missing_review_filter_tokens)}",
            )
        )
    else:
        results.append(pass_check("Review filters", "review search and filters map visible labels to stored values"))

    theme_tokens = [
        'id="themeToggle"',
        'id="themeLabel"',
        "function applyTheme(theme)",
        "function toggleTheme()",
        "localStorage.setItem(\"aiDiaryTheme\"",
        "localStorage.getItem(\"aiDiaryTheme\")",
        "body[data-theme=\"night\"]",
        "$(\"themeToggle\")?.addEventListener(\"click\", toggleTheme)",
    ]
    missing_theme_tokens = [token for token in theme_tokens if token not in html]
    if missing_theme_tokens:
        results.append(
            fail_check(
                "Theme toggle",
                f"theme toggle is missing tokens: {', '.join(missing_theme_tokens)}",
            )
        )
    else:
        results.append(pass_check("Theme toggle", "sidebar theme switch is interactive and persisted"))

    return results


def run_checks(
    client: HealthClient,
    include_draft: bool,
    start_vision: bool,
    vision_image: str | None,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    config = client.get("/api/ai/config")
    missing = require_keys("AI config", config, ["provider", "deepseek", "vision"])
    if missing:
        results.append(missing)
    else:
        vision = config.get("vision") or {}
        vision_detail = (
            f"provider={config.get('provider')}, "
            f"deepseek_model={(config.get('deepseek') or {}).get('model')}, "
            f"vision_model={vision.get('model')}, vision_enabled={vision.get('enabled')}"
        )
        results.append(pass_check("AI config", vision_detail))

    activity_config = client.get("/api/activity/config")
    missing = require_keys(
        "Activity config",
        activity_config,
        ["enabled", "capture_window_titles", "retention_days", "excluded_apps", "title_redact_keywords"],
    )
    if missing:
        results.append(missing)
    else:
        results.append(
            pass_check(
                "Activity config",
                f"enabled={activity_config.get('enabled')}, capture_titles={activity_config.get('capture_window_titles')}, retention={activity_config.get('retention_days')}d",
            )
        )

    privacy = client.get("/api/privacy/audit")
    missing = require_keys(
        "Privacy audit",
        privacy,
        ["rules", "redaction", "retention", "vision", "last_effective_at", "cleanup", "photo_usage"],
    )
    if missing:
        results.append(missing)
    else:
        rules = privacy.get("rules") or []
        photo_missing = require_keys(
            "Privacy photo usage",
            privacy.get("photo_usage") or {},
            ["entry_count", "item_count", "analyzed_count", "skipped_count", "failed_count"],
        )
        if len(rules) < 5:
            results.append(fail_check("Privacy audit", f"expected at least 5 privacy rules, got {len(rules)}"))
        elif photo_missing:
            results.append(photo_missing)
        else:
            retention = privacy.get("retention") or {}
            photo_usage = privacy.get("photo_usage") or {}
            results.append(
                pass_check(
                    "Privacy audit",
                    f"rules={len(rules)}, retention={retention.get('days')}d, recent={retention.get('recent_count')}, expired={retention.get('expired_count')}, photo_items={photo_usage.get('item_count')}",
                )
            )

    activity = client.get("/api/activity/today")
    missing = require_keys("Today activity", activity, ["date", "total_seconds", "summary", "top_apps", "tracker", "logs"])
    if missing:
        results.append(missing)
    else:
        summary = activity.get("summary") or {}
        tracker = activity.get("tracker") or {}
        results.append(
            pass_check(
                "Today activity",
                f"total={activity.get('total_seconds')}s, apps={len(activity.get('top_apps') or [])}, logs={len(activity.get('logs') or [])}, tracker={tracker.get('status')}",
            )
        )
        today_apps = activity.get("top_apps") or []
        if today_apps and not all(isinstance(app, dict) and app.get("display_name") for app in today_apps[:3]):
            results.append(fail_check("Today activity app names", "top_apps are missing display_name"))
        else:
            results.append(pass_check("Today activity app names", f"display_names={min(len(today_apps), 3)}"))
        summary_events = (summary.get("events") or []) if isinstance(summary, dict) else []
        timeline_rows = (summary.get("timeline") or []) if isinstance(summary, dict) else []
        top_topics = (summary.get("top_topics") or []) if isinstance(summary, dict) else []
        summary_highlights = "\n".join(summary.get("highlights") or []) if isinstance(summary, dict) else ""
        if summary_events and not all(isinstance(event, dict) and event.get("display_name") for event in summary_events[:3]):
            results.append(fail_check("Activity event app names", "summary.events are missing display_name"))
        elif timeline_rows and not all(isinstance(row, dict) and row.get("display_name") for row in timeline_rows[:3]):
            results.append(fail_check("Activity event app names", "summary.timeline rows are missing display_name"))
        else:
            results.append(pass_check("Activity event app names", f"events={min(len(summary_events), 3)}, timeline={min(len(timeline_rows), 3)}"))
        if top_topics and not all(isinstance(topic, dict) and topic.get("display_title") for topic in top_topics[:3]):
            results.append(fail_check("Activity topic titles", "top_topics are missing display_title"))
        else:
            topic_leaks = [
                token
                for token in ["Codex", "Microsoft Edge", "Microsoft\u200b Edge", "msedge", ".exe"]
                if token.lower() in summary_highlights.lower()
            ]
            if topic_leaks:
                results.append(fail_check("Activity topic titles", f"highlights contain raw topic tokens: {', '.join(topic_leaks)}"))
            else:
                results.append(pass_check("Activity topic titles", f"display_titles={min(len(top_topics), 3)}"))
        if activity.get("total_seconds", 0) <= 0:
            results.append(warn_check("Activity data", "no activity seconds found for today; tracker may be paused or idle"))
        if not isinstance(summary, dict):
            results.append(fail_check("Activity summary", "summary is not an object"))

    comparison = client.get("/api/activity/compare", query={"days": 7})
    missing = require_keys("Activity comparison", comparison, ["today", "baseline", "insights", "baseline_active_days", "rhythm"])
    if missing:
        results.append(missing)
    else:
        insights = comparison.get("insights") or []
        if not isinstance(insights, list):
            results.append(fail_check("Activity comparison", "insights is not a list"))
        else:
            results.append(
                pass_check(
                    "Activity comparison",
                    f"baseline_days={comparison.get('baseline_active_days')}, insights={len(insights)}",
                )
            )
        rhythm = comparison.get("rhythm") or {}
        today_rhythm = rhythm.get("today") or {}
        baseline_rhythm = rhythm.get("baseline") or {}
        rhythm_insights = rhythm.get("insights") or []
        rhythm_missing = []
        for prefix, value in [("today", today_rhythm), ("baseline", baseline_rhythm)]:
            missing_rhythm = require_keys(
                "Activity rhythm comparison",
                value,
                ["first_start_time", "last_end_time", "event_count", "avg_event_text", "longest_focus_text"],
            )
            if missing_rhythm:
                rhythm_missing.append(f"{prefix}: {missing_rhythm.detail}")
        if rhythm_missing:
            results.append(fail_check("Activity rhythm comparison", "; ".join(rhythm_missing)))
        elif not isinstance(rhythm_insights, list):
            results.append(fail_check("Activity rhythm comparison", "rhythm.insights is not a list"))
        else:
            results.append(
                pass_check(
                    "Activity rhythm comparison",
                    f"today_start={today_rhythm.get('first_start_time')}, events={today_rhythm.get('event_count')}, longest={today_rhythm.get('longest_focus_text')}, insights={len(rhythm_insights)}",
                )
            )

    trends = client.get("/api/activity/trends", query={"days": 30})
    missing = require_keys("Activity trends", trends, ["days", "summary", "insights", "active_days", "window_days"])
    if missing:
        results.append(missing)
    else:
        trend_days = trends.get("days") or []
        trend_summary = trends.get("summary") or {}
        trend_insights = trends.get("insights") or []
        if not isinstance(trend_days, list) or not isinstance(trend_insights, list):
            results.append(fail_check("Activity trends", "days/insights are not lists"))
        else:
            missing_summary = require_keys(
                "Activity trends",
                trend_summary,
                ["avg_total_text", "recent_avg_total_text", "avg_first_start_time", "recent_first_start_time", "avg_longest_focus_text", "recent_longest_focus_text"],
            )
            if missing_summary:
                results.append(missing_summary)
            else:
                results.append(
                    pass_check(
                        "Activity trends",
                        f"window={trends.get('window_days')}d, active_days={trends.get('active_days')}, insights={len(trend_insights)}",
                    )
                )

    daily_summary = client.get("/api/daily-summary")
    missing = require_keys("Daily summary endpoint", daily_summary, ["date", "summary"])
    if missing:
        results.append(missing)
    else:
        summary = daily_summary.get("summary")
        if not summary:
            results.append(warn_check("Daily summary", "no daily summary exists yet; run /api/daily-summary/generate from the app"))
        else:
            keys = sorted(summary.keys())
            results.append(pass_check("Daily summary", f"available keys={', '.join(keys[:8])}"))

    evidence = client.get("/api/diary/evidence")
    missing = require_keys("Diary evidence", evidence, ["activity", "comparison", "trends", "memories", "privacy", "photos"])
    if missing:
        results.append(missing)
    else:
        evidence_activity = evidence.get("activity") or {}
        events = evidence_activity.get("events") or evidence.get("events") or []
        dayparts = evidence_activity.get("dayparts") or evidence.get("dayparts") or []
        evidence_apps = evidence_activity.get("top_apps") or []
        photos = evidence.get("photos") or {}
        comparison = evidence.get("comparison") or {}
        evidence_trends = evidence.get("trends") or {}
        privacy_data = evidence.get("privacy") or {}
        context_preview = str(evidence.get("context_preview") or "")
        if not isinstance(events, list) or not isinstance(dayparts, list):
            results.append(fail_check("Diary evidence", "events/dayparts are not lists"))
            events = []
            dayparts = []
        results.append(
            pass_check(
                "Diary evidence",
                f"events={len(events)}, dayparts={len(dayparts)}, apps={len(evidence_apps)}, photo_items={len(photos.get('items') or [])}, privacy_keys={len(privacy_data.keys())}",
            )
        )
        if evidence_apps and not all(isinstance(app, dict) and app.get("display_name") for app in evidence_apps[:3]):
            results.append(fail_check("Diary evidence app names", "top_apps are missing display_name"))
        else:
            results.append(pass_check("Diary evidence app names", f"display_names={min(len(evidence_apps), 3)}"))
        if not isinstance(comparison.get("insights"), list):
            results.append(fail_check("Diary evidence comparison", "comparison.insights is not a list"))
        else:
            results.append(
                pass_check(
                    "Diary evidence comparison",
                    f"baseline_days={comparison.get('baseline_active_days')}, insights={len(comparison.get('insights') or [])}",
                )
            )
        missing_evidence_trends = require_keys("Diary evidence trends", evidence_trends, ["summary", "insights", "active_days", "window_days"])
        if missing_evidence_trends:
            results.append(missing_evidence_trends)
        elif not isinstance(evidence_trends.get("insights"), list):
            results.append(fail_check("Diary evidence trends", "trends.insights is not a list"))
        else:
            results.append(
                pass_check(
                    "Diary evidence trends",
                    f"window={evidence_trends.get('window_days')}d, active_days={evidence_trends.get('active_days')}, insights={len(evidence_trends.get('insights') or [])}",
                )
            )
        leaked_tokens = [
            token
            for token in [
                ".exe",
                "msedge",
                "microsoft edge",
                "google chrome",
                "codex",
                "codex.exe",
                "python.exe",
                "uvicorn",
                "sunloginclient",
                "clash-verge",
                "shellhost",
                "haojiao_quality",
            ]
            if token.lower() in context_preview.lower()
        ]
        if leaked_tokens:
            results.append(
                fail_check(
                    "Diary context humanized",
                    f"context_preview still contains machine tokens: {', '.join(leaked_tokens)}",
                )
            )
        elif context_preview:
            results.append(pass_check("Diary context humanized", "context_preview avoids raw process names"))
            if "和平时相比" in context_preview:
                results.append(pass_check("Diary context comparison", "context_preview includes activity comparison"))
            else:
                results.append(fail_check("Diary context comparison", "context_preview does not include activity comparison"))
            if "近30天趋势" in context_preview:
                results.append(pass_check("Diary context trends", "context_preview includes long-term activity trends"))
            else:
                results.append(fail_check("Diary context trends", "context_preview does not include long-term activity trends"))

    entries = client.get("/api/entries", query={"page_size": 1})
    missing = require_keys("Entries list", entries, ["entries", "total"])
    if missing:
        results.append(missing)
    else:
        results.append(pass_check("Entries list", f"total={entries.get('total')}, sample={len(entries.get('entries') or [])}"))

    streak = client.get("/api/stats/streak", query={"author": "user"})
    missing = require_keys("User streak", streak, ["streak", "longest_streak"])
    if missing:
        results.append(missing)
    else:
        results.append(
            pass_check(
                "User streak",
                f"current={streak.get('streak')}, longest={streak.get('longest_streak')}, total_days={streak.get('total_days')}",
            )
        )

    heatmap = client.get("/api/stats/heatmap")
    if isinstance(heatmap, list):
        results.append(pass_check("Stats heatmap", f"items={len(heatmap)}"))
    elif isinstance(heatmap, dict):
        results.append(pass_check("Stats heatmap", f"keys={', '.join(sorted(heatmap.keys())[:6])}"))
    else:
        results.append(fail_check("Stats heatmap", f"unexpected type: {type(heatmap).__name__}"))

    vision_status = client.get("/api/vision/status")
    missing = require_keys("Vision status", vision_status, ["enabled", "model", "base_url"])
    if missing:
        results.append(missing)
    else:
        if vision_status.get("ok"):
            results.append(
                pass_check(
                    "Vision status",
                    f"online model={vision_status.get('model')}, device={vision_status.get('device', 'unknown')}, elapsed={vision_status.get('elapsed_ms')}ms",
                )
            )
        else:
            results.append(
                warn_check(
                    "Vision status",
                    f"not online: enabled={vision_status.get('enabled')}, status={vision_status.get('status')}, error={vision_status.get('error')}",
                )
            )

    if include_draft:
        draft = client.post("/api/diary/draft", body={"hint": "健康检查：请确认草稿接口可返回内容。"})
        missing = require_keys("Diary draft", draft, ["draft", "provider"])
        if missing:
            results.append(missing)
        else:
            draft_text = str(draft.get("draft") or "")
            if len(draft_text.strip()) < 10:
                results.append(fail_check("Diary draft", "draft text is too short"))
            else:
                results.append(
                    pass_check(
                        "Diary draft",
                        f"provider={draft.get('provider')}, fallback={draft.get('fallback', False)}, chars={len(draft_text)}",
                    )
                )

    if start_vision:
        started = client.post("/api/vision/start")
        if started.get("ok"):
            results.append(
                pass_check(
                    "Vision start",
                    f"online model={started.get('model')}, device={started.get('device', 'unknown')}, elapsed={started.get('elapsed_ms')}ms",
                )
            )
        else:
            results.append(
                fail_check(
                    "Vision start",
                    f"enabled={started.get('enabled')}, error={started.get('error')}, elapsed={started.get('elapsed_ms')}ms",
                )
            )

    if vision_image:
        if not os.path.isfile(vision_image):
            results.append(fail_check("Vision image test", f"file not found: {vision_image}"))
        else:
            tested = client.upload_image(vision_image)
            description = str(tested.get("description") or "").strip()
            if tested.get("ok") and len(description) >= 8:
                results.append(
                    pass_check(
                        "Vision image test",
                        f"model={tested.get('model')}, chars={len(description)}, preview={description[:80]}",
                    )
                )
            else:
                results.append(
                    fail_check(
                        "Vision image test",
                        f"unexpected response: {json.dumps(tested, ensure_ascii=False)[:300]}",
                    )
                )

    results.extend(check_frontend_contracts())

    return results


def print_results(results: list[CheckResult], elapsed_ms: int) -> None:
    for result in results:
        prefix = "WARN" if result.warning else "PASS" if result.ok else "FAIL"
        print(f"[{prefix}] {result.name}: {result.detail}")
    failures = [result for result in results if not result.ok]
    warnings = [result for result in results if result.warning]
    print(f"\nSummary: {len(results) - len(failures)} passed, {len(failures)} failed, {len(warnings)} warnings, {elapsed_ms} ms")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI Diary local API health.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"App base URL, default: {DEFAULT_BASE_URL}")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout seconds, default: 8")
    parser.add_argument("--draft", action="store_true", help="Also call /api/diary/draft; may use the configured AI model")
    parser.add_argument("--vision-start", action="store_true", help="Also start MiniCPM via /api/vision/start; may take a few minutes")
    parser.add_argument("--vision-image", help="Also upload one local image to /api/vision/test; may use the local vision model")
    args = parser.parse_args()
    if (args.vision_start or args.vision_image) and args.timeout < 150:
        args.timeout = 180

    client = HealthClient(args.base_url, args.timeout)
    started = time.perf_counter()
    try:
        results = run_checks(
            client,
            include_draft=args.draft,
            start_vision=args.vision_start,
            vision_image=args.vision_image,
        )
    except HTTPError as exc:
        print(f"[FAIL] HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"[FAIL] cannot reach {args.base_url}: {exc.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"[FAIL] request timed out after {args.timeout}s", file=sys.stderr)
        return 1
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print_results(results, elapsed_ms)
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
