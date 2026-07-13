"""Runtime UI layout checks for the AI Diary frontend.

This script opens the local app in a real browser and verifies that the core
pink diary pages keep their expected layout anchors. It is intentionally
focused on stable signals: active page state, page title, horizontal overflow,
and non-zero dimensions for key layout containers.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


DEFAULT_BASE_URL = "http://127.0.0.1:8000/"
DEFAULT_VIEWPORT = {"width": 1680, "height": 945}


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    active_id: str
    selectors: tuple[str, ...]


PAGE_SPECS = (
    PageSpec("dashboard", "看板", "page-dashboard", ("#page-dashboard .dashboard-grid", "#page-dashboard .stats-row")),
    PageSpec("write", "我写日记", "page-write", ("#page-write .grid", "#diaryContent", "#page-write .analysis-card")),
    PageSpec("her", "她写日记", "page-her", ("#page-her .her-page-stack", "#page-her .her-letter")),
    PageSpec("review", "回顾", "page-review", ("#page-review .review-grid", "#page-review .review-detail")),
    PageSpec("activity", "活动", "page-activity", ("#page-activity .activity-layout", "#page-activity .activity-side")),
    PageSpec("memory", "记忆", "page-memory", ("#page-memory .memory-layout", "#page-memory .memory-add-box")),
    PageSpec("settings", "设置", "page-settings", ("#page-settings .settings-layout", "#visionProviderCard")),
)


def collect_metrics(page: Any, spec: PageSpec) -> dict[str, Any]:
    return page.evaluate(
        """(spec) => {
            const rectFor = (selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                };
            };
            const h1 = document.querySelector("h1");
            const subtitle = document.querySelector(".subtitle");
            const writeStatus = document.querySelector("#writeStatus");
            const uploadStrip = document.querySelector("#page-write .upload-strip");
            const uploadTile = document.querySelector("#page-write .upload-tile");
            const previewChips = Array.from(document.querySelectorAll("#page-write #imagePreview .preview-chip"));
            const dashboardStatCards = Array.from(document.querySelectorAll("#page-dashboard .stat-card"));
            const dashboardStatValues = Array.from(document.querySelectorAll("#page-dashboard .stat-value"));
            const dashboardStatsCard = document.querySelector("#page-dashboard .dashboard-stats-card");
            const dashboardGrid = document.querySelector("#page-dashboard .dashboard-grid");
            const dashboardObserveNote = document.querySelector("#page-dashboard .dashboard-observe-note");
            const herObserveMuted = document.querySelector("#page-her .her-observe-card > .card-head .muted");
            const herObserveCard = document.querySelector("#page-her .her-observe-card");
            const herLetter = document.querySelector("#page-her .her-letter");
            const herLetterContent = document.querySelector("#page-her .her-letter .letter-content");
            const reviewDetailBody = document.querySelector("#page-review .review-detail-body");
            const reviewEvidenceBox = document.querySelector("#reviewEvidence");
            const activityCompareBox = document.querySelector("#activityCompare");
            const privacyAuditList = document.querySelector("#privacyAuditList");
            const activityLocalNote = document.querySelector("#page-activity .activity-local-note");
            const memoryList = document.querySelector("#page-memory .long-memory-list");
            const memoryCandidates = document.querySelector("#memoryCandidates");
            const memoryIntro = document.querySelector("#page-memory .memory-side .side-note:first-child");
            return {
                key: spec.key,
                title: h1 ? h1.textContent.trim() : "",
                h1FontSize: h1 ? getComputedStyle(h1).fontSize : "",
                subtitleFontSize: subtitle ? getComputedStyle(subtitle).fontSize : "",
                activePages: Array.from(document.querySelectorAll(".page.active")).map((el) => el.id),
                overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                viewport: { width: window.innerWidth, height: window.innerHeight },
                selectors: Object.fromEntries(spec.selectors.map((selector) => [selector, rectFor(selector)])),
                write: spec.key === "write" ? {
                    statusText: writeStatus ? writeStatus.textContent.trim() : null,
                    statusDisplay: writeStatus ? getComputedStyle(writeStatus).display : null,
                    uploadTileCount: uploadTile ? 1 : 0,
                    samplePreviewCount: previewChips.filter((el) => el.dataset.samplePreview === "true").length,
                    uploadStripHeight: uploadStrip ? Math.round(uploadStrip.getBoundingClientRect().height) : 0,
                    previewOverflowX: uploadStrip ? getComputedStyle(document.querySelector("#page-write .preview-row")).overflowX : null,
                    previewOverflowY: uploadStrip ? getComputedStyle(document.querySelector("#page-write .preview-row")).overflowY : null,
                    previewRowSpread: previewChips.length
                        ? Math.max(...previewChips.map((el) => Math.round(el.getBoundingClientRect().top))) - Math.min(...previewChips.map((el) => Math.round(el.getBoundingClientRect().top)))
                        : 0,
                } : null,
                dashboard: spec.key === "dashboard" ? {
                    statCount: dashboardStatCards.length,
                    statHeightMin: dashboardStatCards.length ? Math.min(...dashboardStatCards.map((el) => Math.round(el.getBoundingClientRect().height))) : 0,
                    statHeightMax: dashboardStatCards.length ? Math.max(...dashboardStatCards.map((el) => Math.round(el.getBoundingClientRect().height))) : 0,
                    statTopSpread: dashboardStatCards.length ? Math.max(...dashboardStatCards.map((el) => Math.round(el.getBoundingClientRect().top))) - Math.min(...dashboardStatCards.map((el) => Math.round(el.getBoundingClientRect().top))) : 0,
                    statValueFont: dashboardStatValues.length ? parseFloat(getComputedStyle(dashboardStatValues[0]).fontSize) : 0,
                    summaryCardHeight: dashboardStatsCard ? Math.round(dashboardStatsCard.getBoundingClientRect().height) : 0,
                    gridBottom: dashboardGrid ? Math.round(dashboardGrid.getBoundingClientRect().bottom) : 0,
                    observeWidth: dashboardObserveNote ? Math.round(dashboardObserveNote.getBoundingClientRect().width) : 0,
                    observeHeadingDisplay: dashboardObserveNote ? getComputedStyle(dashboardObserveNote.querySelector("h3") || dashboardObserveNote).display : null,
                } : null,
                her: spec.key === "her" ? {
                    observeMutedDisplay: herObserveMuted ? getComputedStyle(herObserveMuted).display : null,
                    observeHeight: herObserveCard ? Math.round(herObserveCard.getBoundingClientRect().height) : 0,
                    letterHeight: herLetter ? Math.round(herLetter.getBoundingClientRect().height) : 0,
                    letterContentOffset: herLetter && herLetterContent ? Math.round(herLetterContent.getBoundingClientRect().left - herLetter.getBoundingClientRect().left) : 0,
                    letterContentWidth: herLetterContent ? Math.round(herLetterContent.getBoundingClientRect().width) : 0,
                } : null,
                review: spec.key === "review" ? {
                    detailLineHeight: reviewDetailBody ? parseFloat(getComputedStyle(reviewDetailBody).lineHeight) : 0,
                    evidenceDisplay: reviewEvidenceBox ? getComputedStyle(reviewEvidenceBox).display : null,
                    evidenceHeight: reviewEvidenceBox ? Math.round(reviewEvidenceBox.getBoundingClientRect().height) : 0,
                    evidenceMaxHeight: reviewEvidenceBox ? parseFloat(getComputedStyle(reviewEvidenceBox).maxHeight) : 0,
                } : null,
                activity: spec.key === "activity" ? {
                    compareBorderTop: activityCompareBox ? getComputedStyle(activityCompareBox).borderTopWidth : null,
                    compareBackground: activityCompareBox ? getComputedStyle(activityCompareBox).backgroundColor : null,
                    privacyAuditMaxHeight: privacyAuditList ? parseFloat(getComputedStyle(privacyAuditList).maxHeight) : 0,
                    localNoteText: activityLocalNote ? activityLocalNote.textContent.trim() : "",
                } : null,
                memory: spec.key === "memory" ? {
                    listMaxHeight: memoryList ? parseFloat(getComputedStyle(memoryList).maxHeight) : 0,
                    candidateMaxHeight: memoryCandidates ? parseFloat(getComputedStyle(memoryCandidates).maxHeight) : 0,
                    introBackground: memoryIntro ? getComputedStyle(memoryIntro).backgroundImage : "",
                } : null,
            };
        }""",
        {"key": spec.key, "selectors": list(spec.selectors)},
    )


def validate_metrics(spec: PageSpec, metrics: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if metrics.get("title") != spec.title:
        errors.append(f"title expected {spec.title!r}, got {metrics.get('title')!r}")
    if metrics.get("activePages") != [spec.active_id]:
        errors.append(f"active page expected [{spec.active_id}], got {metrics.get('activePages')}")
    if metrics.get("overflowX"):
        errors.append("horizontal overflow detected")
    if metrics.get("h1FontSize") != "28px":
        errors.append(f"h1 font-size expected 28px, got {metrics.get('h1FontSize')!r}")
    if spec.key == "dashboard":
        dashboard = metrics.get("dashboard") or {}
        if dashboard.get("statCount") != 4:
            errors.append(f"dashboard expected 4 top stat cards, got {dashboard.get('statCount')}")
        if dashboard.get("statTopSpread", 0) > 4:
            errors.append(f"dashboard top stat cards should stay in one row, top spread={dashboard.get('statTopSpread')}px")
        if dashboard.get("statHeightMin", 0) < 150:
            errors.append(f"dashboard top stat cards should keep reference-like height, got min={dashboard.get('statHeightMin')}px")
        if dashboard.get("statValueFont", 0) < 42:
            errors.append(f"dashboard stat value font expected >= 42px, got {dashboard.get('statValueFont')}px")
        if dashboard.get("summaryCardHeight", 0) > 285:
            errors.append(f"dashboard diary statistics card should stay compact, got {dashboard.get('summaryCardHeight')}px")
        viewport_height = (metrics.get("viewport") or {}).get("height", 0)
        if viewport_height and dashboard.get("gridBottom", 0) > viewport_height + 4:
            errors.append(f"dashboard first screen should not be pushed below viewport, bottom={dashboard.get('gridBottom')} viewport={viewport_height}")
        if dashboard.get("observeWidth", 9999) > 460:
            errors.append(f"dashboard observation strip should stay lightweight, got width={dashboard.get('observeWidth')}px")
        if dashboard.get("observeHeadingDisplay") != "none":
            errors.append(f"dashboard observation strip heading should stay hidden, got {dashboard.get('observeHeadingDisplay')!r}")
    if spec.key == "her":
        her = metrics.get("her") or {}
        if her.get("observeMutedDisplay") != "none":
            errors.append(f"her observe card should not repeat the page subtitle, got muted display={her.get('observeMutedDisplay')!r}")
        if her.get("letterHeight", 0) < 360:
            errors.append(f"her letter should keep reference-style envelope height, got {her.get('letterHeight')}px")
        if her.get("letterContentOffset", 999) > 150:
            errors.append(f"her letter text should start on the left side of the paper, got offset={her.get('letterContentOffset')}px")
        if her.get("letterContentWidth", 0) > 820:
            errors.append(f"her letter text should leave room for stamp and bouquet, got width={her.get('letterContentWidth')}px")
    if spec.key == "write":
        write = metrics.get("write") or {}
        if write.get("statusText") or write.get("statusDisplay") != "none":
            errors.append(
                f"write idle status should be hidden and empty, got display={write.get('statusDisplay')!r}, text={write.get('statusText')!r}"
            )
        if write.get("uploadTileCount") != 1 or write.get("samplePreviewCount") != 5:
            errors.append(
                f"write upload strip expected 1 upload tile and 5 sample previews, got tile={write.get('uploadTileCount')}, previews={write.get('samplePreviewCount')}"
            )
        if write.get("previewRowSpread", 0) > 4:
            errors.append(f"write upload previews should stay in one row, top spread={write.get('previewRowSpread')}px")
        if write.get("previewOverflowX") != "visible" or write.get("previewOverflowY") != "visible":
            errors.append(
                f"write desktop preview row should not show internal scrollbars, got overflowX={write.get('previewOverflowX')!r}, overflowY={write.get('previewOverflowY')!r}"
            )
    if spec.key == "review":
        review = metrics.get("review") or {}
        detail_rect = (metrics.get("selectors") or {}).get("#page-review .review-detail") or {}
        if detail_rect.get("y", 999) > 85:
            errors.append(f"review detail card should start near the page title like the reference, got y={detail_rect.get('y')}")
        if review.get("detailLineHeight", 0) > 31:
            errors.append(f"review detail body should keep compact paper line-height, got {review.get('detailLineHeight')}px")
        if review.get("evidenceDisplay") != "none" and review.get("evidenceHeight", 0) > 130:
            errors.append(f"review evidence snapshot should stay compact, got {review.get('evidenceHeight')}px")
        if review.get("evidenceMaxHeight", 0) > 130:
            errors.append(f"review evidence max-height should stay <=130px, got {review.get('evidenceMaxHeight')}px")
    if spec.key == "activity":
        activity = metrics.get("activity") or {}
        if activity.get("compareBorderTop") != "0px":
            errors.append(f"activity comparison text should stay paper-like without an inner box border, got {activity.get('compareBorderTop')}")
        if activity.get("privacyAuditMaxHeight", 0) > 190:
            errors.append(f"activity privacy audit list should stay compact, got max-height {activity.get('privacyAuditMaxHeight')}px")
        if "本机保存" not in activity.get("localNoteText", ""):
            errors.append("activity local privacy note should explain that data stays on this device")
    if spec.key == "memory":
        memory = metrics.get("memory") or {}
        if memory.get("listMaxHeight", 0) > 270:
            errors.append(f"memory confirmed/preview list should stay compact, got max-height {memory.get('listMaxHeight')}px")
        if memory.get("candidateMaxHeight", 0) > 320:
            errors.append(f"memory candidates table should stay compact, got max-height {memory.get('candidateMaxHeight')}px")
        if "analysis-flower-ref" not in memory.get("introBackground", ""):
            errors.append("memory intro side card should keep the reference flower accent")

    selectors = metrics.get("selectors") or {}
    for selector in spec.selectors:
        rect = selectors.get(selector)
        if not rect:
            errors.append(f"missing selector {selector}")
            continue
        if rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
            errors.append(f"selector {selector} has empty rect {rect}")
    return errors


def validate_visible_actions(page: Any, timeout_ms: int) -> list[str]:
    errors: list[str] = []

    try:
        page.locator("#themeToggle").click(timeout=timeout_ms)
        theme = page.evaluate("document.body.dataset.theme")
        stored_theme = page.evaluate("localStorage.getItem('aiDiaryTheme')")
        if theme != "night" or stored_theme != "night":
            errors.append(f"theme toggle expected night persistence, got theme={theme!r}, stored={stored_theme!r}")
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(300)
        persisted_theme = page.evaluate("document.body.dataset.theme")
        if persisted_theme != "night":
            errors.append(f"theme reload expected night, got {persisted_theme!r}")
        page.locator("#themeToggle").click(timeout=timeout_ms)
        if page.evaluate("document.body.dataset.theme") != "light":
            errors.append("theme toggle did not return to light")
    except PlaywrightError as exc:
        errors.append(f"theme toggle interaction failed: {exc}")

    try:
        page.locator('button[data-page="settings"]').click(timeout=timeout_ms)
        page.wait_for_timeout(300)
        page.locator('[data-provider-tab="deepseek"]').click(timeout=timeout_ms)
        provider = page.locator("#provider").input_value(timeout=timeout_ms)
        if provider != "deepseek":
            errors.append(f"deepseek tab expected provider=deepseek, got {provider!r}")
        page.locator('[data-settings-focus="vision"]').click(timeout=timeout_ms)
        active_vision = page.locator('[data-settings-focus="vision"].active').count()
        if active_vision != 1:
            errors.append("vision settings tab did not become active")
    except PlaywrightError as exc:
        errors.append(f"settings tab interaction failed: {exc}")

    try:
        page.locator('button[data-page="activity"]').click(timeout=timeout_ms)
        page.wait_for_function(
            """() => {
                const status = document.querySelector("#activityConfigStatus")?.textContent || "";
                return status.includes("当前保留");
            }""",
            timeout=timeout_ms,
        )
        before = page.locator("#activityEnabled").input_value(timeout=timeout_ms)
        page.locator("#activityEnabledSwitch").click(timeout=timeout_ms)
        after = page.locator("#activityEnabled").input_value(timeout=timeout_ms)
        if after == before:
            errors.append(f"activity enabled switch did not change select value from {before!r}")
        page.locator("#activityEnabledSwitch").click(timeout=timeout_ms)
        restored = page.locator("#activityEnabled").input_value(timeout=timeout_ms)
        if restored != before:
            errors.append(f"activity enabled switch did not restore select value to {before!r}, got {restored!r}")
    except PlaywrightError as exc:
        errors.append(f"activity privacy switch interaction failed: {exc}")

    try:
        page.locator('button[data-page="review"]').click(timeout=timeout_ms)
        page.wait_for_timeout(500)
        first_review_item = page.locator("#reviewList .review-item").nth(0)
        if first_review_item.count():
            height = first_review_item.bounding_box(timeout=timeout_ms)["height"]
            if height > 132:
                errors.append(f"review item height expected <= 132px, got {height:.1f}px")
        review_title_check = page.evaluate(
            """() => {
                const herTitle = document.querySelector("#reviewList .review-item.her strong")?.textContent?.trim() || "";
                const detailTitle = document.querySelector("#reviewDetailTitle")?.textContent?.trim() || "";
                const evidenceBox = document.querySelector("#reviewEvidence");
                return {
                    herTitle,
                    detailTitle,
                    evidenceDisplay: evidenceBox ? getComputedStyle(evidenceBox).display : null,
                    evidenceText: evidenceBox?.textContent?.trim() || "",
                };
            }"""
        )
        generic_review_titles = {"她的日记", "她今天的日记"}
        if review_title_check.get("herTitle") in generic_review_titles:
            errors.append("review her diary list title should be derived from content, not the generic stored title")
        if review_title_check.get("detailTitle") in generic_review_titles:
            errors.append("review detail title should be derived from content, not the generic stored title")
        if review_title_check.get("evidenceDisplay") == "none" or not review_title_check.get("evidenceText"):
            errors.append("review detail should show evidence snapshot or an old-entry explanation")
    except PlaywrightError as exc:
        errors.append(f"review paper-card layout check failed: {exc}")

    required_actions = page.evaluate(
        """() => ({
            removeUploadedImage: typeof window.removeUploadedImage === "function",
            editMemory: typeof window.editMemory === "function",
            dismissCandidateMemory: typeof window.dismissCandidateMemory === "function",
            saveConfig: typeof window.saveConfig === "function",
            cleanupToday: typeof window.cleanupToday === "function",
            cleanupExpired: typeof window.cleanupExpired === "function",
            closeReviewDetail: typeof window.closeReviewDetail === "function",
            reviewCloseButton: !!document.querySelector(".review-close-btn"),
            toggleCandidateList: typeof window.toggleCandidateList === "function",
            scrollToMemoryCandidates: typeof window.scrollToMemoryCandidates === "function",
            manualActivityCount: !!document.querySelector("#manualActivityCount"),
            activityActionStatus: !!document.querySelector("#activityActionStatus"),
            activityEnabledSwitch: !!document.querySelector("#activityEnabledSwitch"),
            captureTitlesSwitch: !!document.querySelector("#captureTitlesSwitch"),
            togglePrivacySelect: typeof window.togglePrivacySelect === "function",
            syncPrivacySwitches: typeof window.syncPrivacySwitches === "function",
            herObserveColumns: document.querySelectorAll("#page-her .her-observe-grid .note-card").length >= 3,
            herObserveSummary: !!document.querySelector("#herObserveSummary")?.textContent.trim(),
            herObserveMoodLabels: ["情绪标签", "情绪指数", "关键词"].every((token) => document.body.textContent.includes(token)),
            uploadRemoveStyle: !!document.querySelector("style")?.textContent.includes("preview-remove"),
            noVisibleOllamaCard: !document.body.textContent.includes("本地文本模型 Ollama"),
        })"""
    )
    for name, ok in required_actions.items():
        if not ok:
            errors.append(f"visible action contract missing {name}")

    return errors


def validate_mobile_her(page: Any, base_url: str, timeout_ms: int) -> list[str]:
    errors: list[str] = []
    try:
        page.set_viewport_size({"width": 720, "height": 941})
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(700)
        page.locator('button[data-page="her"]').click(timeout=timeout_ms)
        page.wait_for_timeout(500)
        metrics = page.evaluate(
            """() => {
                const rectFor = (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        right: Math.round(rect.right),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    };
                };
                return {
                    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                    viewportWidth: window.innerWidth,
                    app: rectFor(".app"),
                    weather: rectFor(".weather"),
                    observe: rectFor("#page-her .her-observe-card"),
                    visibleNav: Array.from(document.querySelectorAll(".nav button")).filter((el) => getComputedStyle(el).display !== "none").map((el) => el.dataset.page),
                    activePages: Array.from(document.querySelectorAll(".page.active")).map((el) => el.id),
                };
            }"""
        )
        if metrics.get("overflowX"):
            errors.append("mobile her page has horizontal overflow")
        if metrics.get("activePages") != ["page-her"]:
            errors.append(f"mobile her active page expected [page-her], got {metrics.get('activePages')}")
        if metrics.get("visibleNav") != ["dashboard", "write", "her", "review", "settings"]:
            errors.append(f"mobile nav expected dashboard/write/her/review/settings, got {metrics.get('visibleNav')}")
        app = metrics.get("app") or {}
        if not app or app.get("width", 0) <= 0:
            errors.append("mobile her app shell missing")
        elif app.get("width", 0) > 700:
            errors.append(f"mobile her app width expected <= 700, got {app.get('width')}")
        weather = metrics.get("weather") or {}
        if not weather or weather.get("width", 0) <= 0:
            errors.append("mobile weather pill missing")
        elif weather.get("right", 0) > metrics.get("viewportWidth", 720):
            errors.append(f"mobile weather pill clipped at right={weather.get('right')}")
        observe = metrics.get("observe") or {}
        if not observe or observe.get("y", 9999) > 220:
            errors.append(f"mobile her observe card starts too low: {observe}")
        elif observe.get("height", 0) > 430:
            errors.append(f"mobile her observe card expected <= 430px tall, got {observe.get('height')}")
    except PlaywrightError as exc:
        errors.append(f"mobile her layout interaction failed: {exc}")
    return errors


def run(base_url: str, timeout_ms: int, headful: bool) -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        page = browser.new_page(viewport=DEFAULT_VIEWPORT)
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(700)

            failures: list[str] = []
            for spec in PAGE_SPECS:
                button = page.locator(f'button[data-page="{spec.key}"]')
                if button.count() != 1:
                    failures.append(f"{spec.key}: nav button missing or duplicated")
                    continue
                button.click(timeout=timeout_ms)
                page.wait_for_timeout(350)
                metrics = collect_metrics(page, spec)
                errors = validate_metrics(spec, metrics)
                if errors:
                    failures.extend(f"{spec.key}: {error}" for error in errors)
                else:
                    viewport = metrics.get("viewport") or {}
                    print(
                        f"[PASS] {spec.key}: title={spec.title}, viewport={viewport.get('width')}x{viewport.get('height')}, no overflow"
                    )

            action_errors = validate_visible_actions(page, timeout_ms)
            if action_errors:
                failures.extend(f"actions: {error}" for error in action_errors)
            else:
                print("[PASS] actions: theme, settings tabs, and visible action contracts")

            mobile_errors = validate_mobile_her(page, base_url, timeout_ms)
            if mobile_errors:
                failures.extend(f"mobile-her: {error}" for error in mobile_errors)
            else:
                print("[PASS] mobile-her: 720px her diary layout has no clipping or overflow")

            if failures:
                for failure in failures:
                    print(f"[FAIL] {failure}")
                print(f"\nSummary: {len(PAGE_SPECS) - len(set(f.split(':', 1)[0] for f in failures))} passed, {len(failures)} issues")
                return 1

            print(f"\nSummary: {len(PAGE_SPECS)} pages passed runtime layout checks")
            return 0
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI Diary frontend layout in a real browser.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"App URL, default: {DEFAULT_BASE_URL}")
    parser.add_argument("--timeout-ms", type=int, default=10_000, help="Browser action timeout in milliseconds")
    parser.add_argument("--headful", action="store_true", help="Show the browser while checking")
    args = parser.parse_args()

    try:
        return run(args.base_url, args.timeout_ms, args.headful)
    except PlaywrightError as exc:
        print(f"[FAIL] Playwright error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
