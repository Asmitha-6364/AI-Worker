"""
Browser Automation Tool using Playwright.
Controls a real Chromium browser instance, captures screenshots, DOM states,
and interacts with AcmeOps web forms.
"""

import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

from playwright.sync_api import sync_playwright, Page, Browser, Playwright, TimeoutError as PlaywrightTimeoutError

from config import SCREENSHOTS_DIR, BROWSER_HEADLESS, BROWSER_SLOW_MO
from tools.base import BaseTool, ToolResult, ToolStatus


class BrowserSession:
    """Singleton-style or managed Playwright browser session."""
    _instance = None

    def __init__(self, headless: bool = BROWSER_HEADLESS):
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def start(self):
        if not self.playwright:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=BROWSER_SLOW_MO
            )
            context = self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcmeAIWorker/1.0"
            )
            self.page = context.new_page()

    def ensure_page(self) -> Page:
        if not self.page or self.page.is_closed():
            self.start()
        return self.page

    def take_screenshot(self, name_prefix: str = "step") -> str:
        page = self.ensure_page()
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{name_prefix}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.png"
        filepath = SCREENSHOTS_DIR / filename
        page.screenshot(path=str(filepath), full_page=True)
        return str(filepath)

    def close(self):
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
            if self.browser and self.browser.is_connected():
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        finally:
            self.page = None
            self.browser = None
            self.playwright = None


# Shared session instance
_session: Optional[BrowserSession] = None

def get_browser_session() -> BrowserSession:
    global _session
    if _session is None:
        _session = BrowserSession()
        _session.start()
    return _session


class BrowserNavigateTool(BaseTool):
    @property
    def name(self) -> str:
        return "browser_navigate"

    @property
    def description(self) -> str:
        return "Navigate the browser to a specific URL (e.g. AcmeOps login or invoices inbox). Returns page title and current URL."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The destination URL to open, e.g. 'http://127.0.0.1:8000/invoices/new'"
                }
            },
            "required": ["url"]
        }

    def execute(self, url: str, **kwargs) -> ToolResult:
        session = get_browser_session()
        page = session.ensure_page()
        try:
            response = page.goto(url, wait_until="networkidle", timeout=10000)
            status_code = response.status if response else 200
            screenshot = session.take_screenshot("navigate")

            # Check if page rendered an error page
            if status_code >= 500 or "Internal Server Error" in page.title():
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output={"url": page.url, "title": page.title(), "http_status": status_code},
                    error=f"Server returned HTTP {status_code}: {page.title()}",
                    error_type="UI_CRASH_OR_500",
                    screenshot_path=screenshot
                )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "current_url": page.url,
                    "title": page.title(),
                    "http_status": status_code
                },
                screenshot_path=screenshot
            )
        except Exception as e:
            screenshot = session.take_screenshot("nav_error")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Navigation failed: {str(e)}",
                error_type="NAVIGATION_ERROR",
                screenshot_path=screenshot
            )


class BrowserClickTool(BaseTool):
    @property
    def name(self) -> str:
        return "browser_click"

    @property
    def description(self) -> str:
        return "Click on a button, link, or clickable element in the browser identified by CSS selector or data-testid."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or data-testid selector, e.g. '[data-testid=\"btn-login\"]' or 'button[type=\"submit\"]'."
                }
            },
            "required": ["selector"]
        }

    def execute(self, selector: str, **kwargs) -> ToolResult:
        session = get_browser_session()
        page = session.ensure_page()
        try:
            page.wait_for_selector(selector, timeout=7000)
            page.click(selector)
            # Short wait for any resulting navigation or network requests
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            time.sleep(0.3)
            screenshot = session.take_screenshot("click")

            # Check for error banners or 500 pages
            page_text = page.inner_text("body")
            if "500 Internal Server Error" in page_text or "Database lock timeout" in page_text:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output={"url": page.url, "page_title": page.title()},
                    error="500 Internal Server Error: Database lock timeout on web form worker.",
                    error_type="UI_CRASH_OR_500",
                    screenshot_path=screenshot
                )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "clicked_selector": selector,
                    "current_url": page.url,
                    "page_title": page.title()
                },
                screenshot_path=screenshot
            )
        except PlaywrightTimeoutError:
            screenshot = session.take_screenshot("click_timeout")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Element selector '{selector}' was not found or not clickable within timeout.",
                error_type="ELEMENT_NOT_FOUND",
                screenshot_path=screenshot
            )
        except Exception as e:
            screenshot = session.take_screenshot("click_error")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Click failed: {str(e)}",
                error_type="BROWSER_ERROR",
                screenshot_path=screenshot
            )


class BrowserFillTool(BaseTool):
    @property
    def name(self) -> str:
        return "browser_fill"

    @property
    def description(self) -> str:
        return "Type or fill a value into a form input field in the browser identified by selector."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or data-testid for input, e.g. '[data-testid=\"input-vendor\"]'."
                },
                "value": {
                    "type": "string",
                    "description": "The string text or numeric value to enter into the field."
                }
            },
            "required": ["selector", "value"]
        }

    def execute(self, selector: str, value: str, **kwargs) -> ToolResult:
        session = get_browser_session()
        page = session.ensure_page()
        try:
            page.wait_for_selector(selector, timeout=5000)
            page.fill(selector, str(value))
            screenshot = session.take_screenshot("fill")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "selector": selector,
                    "value_filled": str(value)
                },
                screenshot_path=screenshot
            )
        except Exception as e:
            screenshot = session.take_screenshot("fill_error")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Failed to fill input '{selector}': {str(e)}",
                error_type="ELEMENT_NOT_FOUND",
                screenshot_path=screenshot
            )


class BrowserGetDomSummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "browser_get_dom_summary"

    @property
    def description(self) -> str:
        return "Inspect the current browser page: returns structured high-signal DOM state including interactive inputs, buttons, tables, alert banners, and page title."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    def execute(self, **kwargs) -> ToolResult:
        session = get_browser_session()
        page = session.ensure_page()
        try:
            url = page.url
            title = page.title()

            # Extract structured summary via JavaScript
            dom_data = page.evaluate("""() => {
                const inputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
                    id: el.id || '',
                    name: el.name || '',
                    type: el.type || el.tagName.toLowerCase(),
                    testid: el.getAttribute('data-testid') || '',
                    placeholder: el.placeholder || '',
                    value: el.value || ''
                }));

                const buttons = Array.from(document.querySelectorAll('button, a.btn, input[type="submit"]')).map(el => ({
                    text: el.innerText.trim() || el.value || '',
                    testid: el.getAttribute('data-testid') || '',
                    id: el.id || '',
                    tag: el.tagName.toLowerCase()
                }));

                const alerts = Array.from(document.querySelectorAll('.alert, [role="alert"]')).map(el => ({
                    text: el.innerText.trim(),
                    className: el.className
                }));

                const headers = Array.from(document.querySelectorAll('h1, h2, h3')).map(el => el.innerText.trim());

                return { inputs, buttons, alerts, headers };
            }""")

            screenshot = session.take_screenshot("dom_inspect")

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "current_url": url,
                    "page_title": title,
                    "interactive_elements": dom_data
                },
                screenshot_path=screenshot
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Failed to inspect DOM: {str(e)}",
                error_type="BROWSER_ERROR"
            )
