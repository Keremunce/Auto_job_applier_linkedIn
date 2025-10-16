from __future__ import annotations

from typing import Optional

try:
    import pyautogui
except Exception:  # pragma: no cover - pyautogui may be unavailable in headless CI
    pyautogui = None


class UIController:
    """
    Abstraction over any GUI interactions so the automation can switch
    between interactive and headless modes safely.
    """

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless or pyautogui is None
        if not self.headless and pyautogui:
            pyautogui.FAILSAFE = True

    def alert(self, message: str, title: str = "LinkedIn Automation") -> Optional[str]:
        if self.headless or pyautogui is None:
            return None
        return pyautogui.alert(text=message, title=title)

    def confirm(
        self,
        message: str,
        title: str = "LinkedIn Automation",
        buttons: Optional[list[str]] = None,
    ) -> Optional[str]:
        if self.headless or pyautogui is None:
            return None
        return pyautogui.confirm(text=message, title=title, buttons=buttons or ["OK"])

    def keep_awake(self) -> None:
        if self.headless or pyautogui is None:
            return
        pyautogui.press("shift")
