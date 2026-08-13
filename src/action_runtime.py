from __future__ import annotations

import hashlib
import io
import os
import threading
import time
import webbrowser
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple


@dataclass(frozen=True)
class BackendResult:
    ok: bool
    executed: bool
    backend: str
    status: str
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ActionBackend(Protocol):
    name: str

    def available(self) -> bool: ...
    def supports(self, action_type: str) -> bool: ...
    def execute(self, action_type: str, target: str, parameters: Dict[str, Any], coords: Optional[Tuple[int, int]]) -> BackendResult: ...


class NullBackend:
    name = "unavailable"

    def available(self) -> bool:
        return False

    def supports(self, action_type: str) -> bool:
        return False

    def execute(self, action_type: str, target: str, parameters: Dict[str, Any], coords: Optional[Tuple[int, int]]) -> BackendResult:
        return BackendResult(False, False, self.name, "BACKEND_UNAVAILABLE", {"action_type": action_type})


class DryRunBackend:
    name = "dry-run"

    def available(self) -> bool:
        return True

    def supports(self, action_type: str) -> bool:
        return True

    def execute(self, action_type: str, target: str, parameters: Dict[str, Any], coords: Optional[Tuple[int, int]]) -> BackendResult:
        return BackendResult(True, False, self.name, "PLANNED", {"action_type": action_type, "target": target, "coordinates": list(coords) if coords else None})


class PyAutoGUIBackend:
    """Real local desktop executor, enabled only when the dependency and host opt-in exist."""

    name = "pyautogui"
    _supported = {
        "click", "type", "scroll", "navigate", "capture_screenshot", "hover",
        "drag_and_drop", "shortcut", "key_press", "vision_sample", "ocr_read_screen",
    }

    def __init__(self, screenshot_dir: str = ".openclaw/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self._pg = None
        try:
            import pyautogui  # type: ignore
            self._pg = pyautogui
        except Exception:
            self._pg = None

    def available(self) -> bool:
        return self._pg is not None

    def supports(self, action_type: str) -> bool:
        return action_type in self._supported

    def _screenshot(self) -> Dict[str, Any]:
        if self._pg is None:
            raise RuntimeError("pyautogui unavailable")
        image = self._pg.screenshot()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        raw = buffer.getvalue()
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "width": int(image.width),
            "height": int(image.height),
            "bytes": len(raw),
        }

    def execute(self, action_type: str, target: str, parameters: Dict[str, Any], coords: Optional[Tuple[int, int]]) -> BackendResult:
        if not self.available():
            return BackendResult(False, False, self.name, "BACKEND_UNAVAILABLE", {})
        if not self.supports(action_type):
            return BackendResult(False, False, self.name, "UNSUPPORTED_BY_BACKEND", {"action_type": action_type})
        pg = self._pg
        assert pg is not None
        try:
            if action_type == "click":
                if coords is None:
                    raise ValueError("click requires coords for desktop backend")
                pg.click(coords[0], coords[1], button=str(parameters.get("button", "left")))
                detail = {"coordinates": list(coords)}
            elif action_type == "type":
                text = parameters.get("text")
                if not isinstance(text, str):
                    raise ValueError("type requires parameters.text")
                pg.write(text, interval=float(parameters.get("interval", 0.0)))
                detail = {"characters": len(text)}
            elif action_type == "scroll":
                amount = int(parameters.get("amount", 0))
                pg.scroll(amount)
                detail = {"amount": amount}
            elif action_type == "navigate":
                opened = webbrowser.open(target, new=int(parameters.get("new", 0)))
                if not opened:
                    raise RuntimeError("browser did not accept navigation request")
                detail = {"opened": True}
            elif action_type == "hover":
                if coords is None:
                    raise ValueError("hover requires coords for desktop backend")
                pg.moveTo(coords[0], coords[1], duration=float(parameters.get("duration", 0.0)))
                detail = {"coordinates": list(coords)}
            elif action_type == "drag_and_drop":
                if coords is None:
                    raise ValueError("drag_and_drop requires source coords")
                destination = parameters.get("to")
                if not isinstance(destination, (list, tuple)) or len(destination) != 2:
                    raise ValueError("drag_and_drop requires parameters.to=[x,y]")
                pg.moveTo(coords[0], coords[1])
                pg.dragTo(int(destination[0]), int(destination[1]), duration=float(parameters.get("duration", 0.2)))
                detail = {"from": list(coords), "to": [int(destination[0]), int(destination[1])]}
            elif action_type in {"shortcut", "key_press"}:
                keys = parameters.get("keys")
                if action_type == "key_press" and not keys:
                    keys = [parameters.get("key") or target]
                if not isinstance(keys, (list, tuple)) or not keys or not all(isinstance(k, str) and k for k in keys):
                    raise ValueError("shortcut/key_press requires key(s)")
                if action_type == "shortcut":
                    pg.hotkey(*keys)
                else:
                    pg.press(keys[0])
                detail = {"key_count": len(keys)}
            elif action_type in {"capture_screenshot", "vision_sample"}:
                detail = self._screenshot()
            elif action_type == "ocr_read_screen":
                image = pg.screenshot()
                try:
                    import pytesseract  # type: ignore
                except Exception:
                    return BackendResult(False, False, self.name, "OCR_BACKEND_UNAVAILABLE", self._screenshot())
                text = pytesseract.image_to_string(image)
                detail = {"text": text, "characters": len(text), **self._screenshot()}
            else:
                raise ValueError(action_type)
            return BackendResult(True, True, self.name, "EXECUTED", detail)
        except Exception as exc:
            return BackendResult(False, False, self.name, "EXECUTION_FAILED", {"error": f"{type(exc).__name__}: {exc}"})


class PlaywrightBackend:
    """Real browser executor using a Chromium CDP endpoint or an opted-in local launch."""

    name = "playwright"
    _supported = {
        "click", "type", "scroll", "navigate", "inspect_dom", "capture_screenshot",
        "hover", "drag_and_drop", "shortcut", "key_press", "vision_sample",
    }

    def __init__(self, *, cdp_url: Optional[str] = None, launch: bool = False, headless: bool = True):
        self.cdp_url = cdp_url
        self.launch = launch
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            self._pw = sync_playwright().start()
            if cdp_url:
                self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
            elif launch:
                self._browser = self._pw.chromium.launch(headless=headless)
            if self._browser:
                context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                self._page = context.pages[0] if context.pages else context.new_page()
        except Exception:
            self.close()

    def close(self) -> None:
        try:
            if self._browser and self.launch:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._page = None

    def available(self) -> bool:
        return self._page is not None

    def supports(self, action_type: str) -> bool:
        return action_type in self._supported

    def execute(self, action_type: str, target: str, parameters: Dict[str, Any], coords: Optional[Tuple[int, int]]) -> BackendResult:
        if not self.available():
            return BackendResult(False, False, self.name, "BACKEND_UNAVAILABLE", {})
        if not self.supports(action_type):
            return BackendResult(False, False, self.name, "UNSUPPORTED_BY_BACKEND", {"action_type": action_type})
        page = self._page
        try:
            if action_type == "navigate":
                response = page.goto(target, wait_until=str(parameters.get("wait_until", "domcontentloaded")))
                detail = {"url": page.url, "http_status": response.status if response else None}
            elif action_type == "click":
                if target:
                    page.click(target, timeout=float(parameters.get("timeout_ms", 10000)))
                elif coords:
                    page.mouse.click(coords[0], coords[1])
                else:
                    raise ValueError("click requires selector target or coords")
                detail = {"selector": target or None, "coordinates": list(coords) if coords else None}
            elif action_type == "type":
                text = parameters.get("text")
                if not isinstance(text, str):
                    raise ValueError("type requires parameters.text")
                if not target:
                    raise ValueError("type requires selector target")
                if bool(parameters.get("append", False)):
                    page.type(target, text)
                else:
                    page.fill(target, text)
                detail = {"selector": target, "characters": len(text)}
            elif action_type == "scroll":
                dx = float(parameters.get("dx", 0))
                dy = float(parameters.get("dy", parameters.get("amount", 0)))
                page.mouse.wheel(dx, dy)
                detail = {"dx": dx, "dy": dy}
            elif action_type == "inspect_dom":
                if not target:
                    raise ValueError("inspect_dom requires selector target")
                loc = page.locator(target).first
                detail = loc.evaluate("el => ({tag: el.tagName, text: el.textContent, id: el.id, className: el.className, role: el.getAttribute('role')})")
            elif action_type in {"capture_screenshot", "vision_sample"}:
                raw = page.screenshot(full_page=bool(parameters.get("full_page", False)))
                detail = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "url": page.url}
            elif action_type == "hover":
                if not target:
                    raise ValueError("hover requires selector target")
                page.hover(target)
                detail = {"selector": target}
            elif action_type == "drag_and_drop":
                destination = parameters.get("to")
                if not target or not isinstance(destination, str) or not destination:
                    raise ValueError("drag_and_drop requires source target and parameters.to selector")
                page.drag_and_drop(target, destination)
                detail = {"source": target, "destination": destination}
            elif action_type in {"shortcut", "key_press"}:
                keys = parameters.get("keys")
                if isinstance(keys, (list, tuple)):
                    key = "+".join(str(k) for k in keys)
                else:
                    key = str(parameters.get("key") or target)
                if not key:
                    raise ValueError("key required")
                page.keyboard.press(key)
                detail = {"key": key}
            else:
                raise ValueError(action_type)
            return BackendResult(True, True, self.name, "EXECUTED", detail)
        except Exception as exc:
            return BackendResult(False, False, self.name, "EXECUTION_FAILED", {"error": f"{type(exc).__name__}: {exc}"})


class SlidingWindowRateLimiter:
    def __init__(self, max_per_second: int):
        if max_per_second <= 0:
            raise ValueError("max_per_second must be > 0")
        self.max_per_second = max_per_second
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            cutoff = current - 1.0
            while self._events and self._events[0] <= cutoff:
                self._events.popleft()
            if len(self._events) >= self.max_per_second:
                return False
            self._events.append(current)
            return True


def choose_backend(config: Dict[str, Any]) -> ActionBackend:
    execution = config.get("execution", {})
    requested = str(execution.get("backend", "auto")).lower()
    if requested == "dry-run":
        return DryRunBackend()
    if requested == "none":
        return NullBackend()

    cdp_env = str(execution.get("browser_cdp_env", "OPENCLAW_BROWSER_CDP_URL"))
    cdp_url = os.getenv(cdp_env) or None
    launch_browser = bool(execution.get("launch_browser", False))
    if requested in {"auto", "playwright", "browser"} and (cdp_url or launch_browser):
        backend = PlaywrightBackend(cdp_url=cdp_url, launch=launch_browser, headless=bool(execution.get("browser_headless", True)))
        if backend.available():
            return backend
        if requested != "auto":
            return backend

    local_gui_env = str(execution.get("local_gui_env", "OPENCLAW_LOCAL_GUI"))
    local_gui_enabled = os.getenv(local_gui_env, "").lower() in {"1", "true", "yes", "on"}
    if requested in {"auto", "pyautogui", "desktop"} and local_gui_enabled:
        backend = PyAutoGUIBackend(str(execution.get("screenshot_dir", ".openclaw/screenshots")))
        if backend.available() or requested != "auto":
            return backend

    return NullBackend()
