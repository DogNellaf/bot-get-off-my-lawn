from __future__ import annotations

from dataclasses import dataclass

import mss
import numpy as np
import win32gui


@dataclass
class WindowRect:
    left: int
    top: int
    width: int
    height: int


class GameWindow:
    """Locates the game window by title and grabs its client area as frames."""

    def __init__(self, title_substring: str):
        self.title_substring = title_substring.lower()
        self._hwnd: int | None = None
        self._sct = mss.mss()

    def find(self) -> int:
        found: list[int] = []

        def _callback(hwnd: int, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if self.title_substring in title.lower():
                found.append(hwnd)

        win32gui.EnumWindows(_callback, None)

        if not found:
            raise RuntimeError(
                f"Не найдено окно, содержащее '{self.title_substring}' в заголовке. "
                "Убедитесь, что игра запущена."
            )

        self._hwnd = found[0]
        return self._hwnd

    def rect(self) -> WindowRect:
        if self._hwnd is None:
            self.find()
        left, top, right, bottom = win32gui.GetClientRect(self._hwnd)
        left, top = win32gui.ClientToScreen(self._hwnd, (left, top))
        right, bottom = win32gui.ClientToScreen(self._hwnd, (right, bottom))
        return WindowRect(left=left, top=top, width=right - left, height=bottom - top)

    def bring_to_foreground(self) -> None:
        if self._hwnd is None:
            self.find()
        try:
            win32gui.SetForegroundWindow(self._hwnd)
        except Exception:
            # Windows may refuse foreground-stealing from a background
            # process; the follow-up click into the window focuses it anyway.
            pass

    def center_screen_point(self) -> tuple[int, int]:
        r = self.rect()
        return r.left + r.width // 2, r.top + r.height // 2

    def grab(self) -> np.ndarray:
        """Returns the current client-area frame as a BGR numpy array."""
        r = self.rect()
        if r.width <= 0 or r.height <= 0:
            raise RuntimeError("Окно игры свёрнуто или имеет нулевой размер.")
        monitor = {"left": r.left, "top": r.top, "width": r.width, "height": r.height}
        frame = np.array(self._sct.grab(monitor))
        return frame[:, :, :3]  # drop alpha channel, keep BGR
