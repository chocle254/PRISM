"""
Desktop Agent
─────────────
Controls the user's screen using PyAutoGUI.
Receives action commands from the orchestrator and executes them
as real mouse movements and keyboard input — works on ANY app or tab.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

SCREEN_W = 1920
SCREEN_H = 1080

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    SCREEN_W, SCREEN_H = pyautogui.size()
    PYAUTOGUI_AVAILABLE = True
    logger.info(f"PyAutoGUI loaded — screen: {SCREEN_W}x{SCREEN_H}")
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("PyAutoGUI not installed. Run: pip install pyautogui pygetwindow")


class DesktopAgent:
    """
    Executes real desktop actions using PyAutoGUI.

    Supported actions:
    - click          : click at coordinates or named position
    - type           : type text into focused element
    - find_and_click : find element by description and click it
    - find_and_type  : find element and type into it
    - hotkey         : press keyboard shortcuts e.g. ctrl+t
    - scroll         : scroll at a position
    - navigate       : open a URL in the browser address bar
    - screenshot     : take and return a screenshot
    """

    def __init__(self):
        self._available = PYAUTOGUI_AVAILABLE

    def is_available(self) -> bool:
        return self._available

    # ── Main Dispatcher ─────────────────────────────────────────────────────────
    async def execute(self, action_type: str, target: str, value: str = "") -> dict:
        """
        Execute a desktop action asynchronously.
        Runs PyAutoGUI in a thread pool to avoid blocking the event loop.
        """
        if not self._available:
            return {
                "success": False,
                "error": "PyAutoGUI not installed. Run: pip install pyautogui"
            }

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._execute_sync, action_type, target, value
            )
        except Exception as e:
            logger.error(f"Desktop action error: {e}")
            return {"success": False, "error": str(e)}

    def _execute_sync(self, action_type: str, target: str, value: str = "") -> dict:
        """Synchronous execution — runs in thread pool."""
        try:
            actions = {
                "click":          lambda: self._click(target),
                "type":           lambda: self._type_text(value),
                "find_and_click": lambda: self._find_and_click(target),
                "find_and_type":  lambda: self._find_and_type(target, value),
                "hotkey":         lambda: self._hotkey(target),
                "scroll":         lambda: self._scroll(target, int(value) if value else 3),
                "move":           lambda: self._move(target),
                "navigate":       lambda: self._open_url(target),
                "screenshot":     lambda: self._take_screenshot(),
            }

            handler = actions.get(action_type)
            if handler:
                return handler()
            return {"success": False, "error": f"Unknown action: {action_type}"}

        except pyautogui.FailSafeException:
            return {"success": False, "error": "Failsafe triggered — mouse moved to top-left corner"}
        except Exception as e:
            logger.error(f"Sync action error: {e}")
            return {"success": False, "error": str(e)}

    # ── Individual Actions ──────────────────────────────────────────────────────
    def _click(self, target: str) -> dict:
        x, y = self._resolve_position(target)
        pyautogui.click(x, y)
        logger.info(f"Clicked ({x}, {y})")
        return {"success": True, "action": "click", "x": x, "y": y}

    def _type_text(self, text: str) -> dict:
        """Type text — uses clipboard paste for unicode support."""
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(text, interval=0.04)
        logger.info(f"Typed: {text[:60]}")
        return {"success": True, "action": "type", "text": text}

    def _find_and_click(self, target: str) -> dict:
        """Find a UI element by description and click it."""
        x, y = self._infer_position(target)
        pyautogui.click(x, y)
        logger.info(f"Find+click '{target}' at ({x}, {y})")
        return {"success": True, "action": "find_and_click", "target": target, "x": x, "y": y}

    def _find_and_type(self, target: str, value: str) -> dict:
        """Find a UI element, click it, then type into it."""
        click_result = self._find_and_click(target)
        if not click_result["success"]:
            return click_result
        time.sleep(0.4)
        # Clear existing text first
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        return self._type_text(value)

    def _hotkey(self, keys: str) -> dict:
        """Press a keyboard shortcut. Format: 'ctrl+t', 'enter', 'ctrl+shift+i'"""
        key_list = [k.strip() for k in keys.replace("+", ",").split(",")]
        pyautogui.hotkey(*key_list)
        logger.info(f"Hotkey: {keys}")
        return {"success": True, "action": "hotkey", "keys": keys}

    def _scroll(self, target: str, clicks: int = 3) -> dict:
        x, y = self._resolve_position(target)
        pyautogui.scroll(clicks, x=x, y=y)
        return {"success": True, "action": "scroll", "x": x, "y": y, "clicks": clicks}

    def _move(self, target: str) -> dict:
        x, y = self._resolve_position(target)
        pyautogui.moveTo(x, y, duration=0.4)
        return {"success": True, "action": "move", "x": x, "y": y}

    def _open_url(self, url: str) -> dict:
        """Navigate to a URL in a new tab."""
        pyautogui.hotkey("ctrl", "t")   # Open new tab
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "l")   # Focus address bar
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")   # Select all existing text
        time.sleep(0.1)
        try:
            import pyperclip
            pyperclip.copy(url)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(url, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        logger.info(f"Navigating to: {url}")
        return {"success": True, "action": "navigate", "url": url}

    def _take_screenshot(self) -> dict:
        """Take a screenshot and return as base64."""
        import base64
        import io
        screenshot = pyautogui.screenshot()
        buf = io.BytesIO()
        screenshot.save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"success": True, "action": "screenshot", "image": b64}

    # ── Position Resolvers ──────────────────────────────────────────────────────
    def _resolve_position(self, target: str) -> tuple[int, int]:
        """Convert target string to (x, y) screen coordinates."""
        # Direct "x,y" coordinates
        if "," in target:
            parts = target.split(",")
            if len(parts) == 2:
                try:
                    return int(parts[0].strip()), int(parts[1].strip())
                except ValueError:
                    pass

        return self._infer_position(target)

    def _infer_position(self, description: str) -> tuple[int, int]:
        """
        Map natural language UI descriptions to screen coordinates.
        Based on common browser and app layouts.
        """
        desc = description.lower()

        # ── Browser chrome ──────────────────────────────────────────────────────
        if any(w in desc for w in ["address bar", "url bar", "omnibox", "location bar"]):
            return SCREEN_W // 2, 60
        if any(w in desc for w in ["new tab button", "new tab"]):
            return 250, 35
        if any(w in desc for w in ["back button", "back arrow", "go back"]):
            return 30, 60
        if any(w in desc for w in ["forward button", "go forward"]):
            return 58, 60
        if any(w in desc for w in ["refresh", "reload"]):
            return 85, 60
        if any(w in desc for w in ["bookmark", "star"]):
            return SCREEN_W - 150, 60

        # ── Input fields ────────────────────────────────────────────────────────
        if any(w in desc for w in ["chat input", "message input", "message box",
                                    "prompt input", "ask gemini", "search gemini",
                                    "type here", "chat box", "input field",
                                    "text input", "text area", "text box"]):
            return SCREEN_W // 2, int(SCREEN_H * 0.88)
        if any(w in desc for w in ["search bar", "search box", "search input",
                                    "google search", "search field"]):
            return SCREEN_W // 2, int(SCREEN_H * 0.45)

        # ── Buttons ─────────────────────────────────────────────────────────────
        if any(w in desc for w in ["send button", "send", "submit button", "submit"]):
            return int(SCREEN_W * 0.88), int(SCREEN_H * 0.88)
        if any(w in desc for w in ["ok button", "confirm", "yes button"]):
            return SCREEN_W // 2, int(SCREEN_H * 0.6)
        if any(w in desc for w in ["close button", "x button", "dismiss"]):
            return SCREEN_W - 20, 20

        # ── Page regions ────────────────────────────────────────────────────────
        if any(w in desc for w in ["top", "header", "navbar", "navigation bar"]):
            return SCREEN_W // 2, 100
        if any(w in desc for w in ["bottom", "footer"]):
            return SCREEN_W // 2, SCREEN_H - 80
        if any(w in desc for w in ["left sidebar", "left panel", "left menu", "sidebar"]):
            return 150, SCREEN_H // 2
        if any(w in desc for w in ["right sidebar", "right panel"]):
            return SCREEN_W - 150, SCREEN_H // 2
        if any(w in desc for w in ["center", "middle", "main content"]):
            return SCREEN_W // 2, SCREEN_H // 2

        # Default — center of screen
        logger.warning(f"Could not infer position for: '{description}', using center")
        return SCREEN_W // 2, SCREEN_H // 2


# ── Singleton instance ─────────────────────────────────────────────────────────
desktop = DesktopAgent()