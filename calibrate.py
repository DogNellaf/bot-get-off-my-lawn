"""Interactive calibration helper.

Usage (run the game first, then this script against the running window):

  python calibrate.py field      # click the 4 corners of the lawn trapezoid
  python calibrate.py gameover   # select the 'Play Again' button on the results screen

Controls while a window is open:
  field:    left-click the corners in order: top-left, top-right,
            bottom-right, bottom-left. Backspace/z undoes, ESC/q finishes.
  gameover: drag a box around the restart button, ESC/q finishes.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import win32gui

from bot.config import Config
from bot.logger import MessageType, write_line
from bot.window import GameWindow

Box = tuple[int, int, int, int]


def _force_foreground(window_name: str) -> None:
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # Windows can refuse foreground-stealing from a background
            # process; clicking the window focuses it anyway.
            pass


class BoxSelector:
    """Mouse-driven rectangle selector that doesn't rely on cv2.selectROI's
    built-in ENTER/SPACE handling, which doesn't respond reliably on some
    OpenCV builds/window backends."""

    def __init__(self, window_name: str, frame: np.ndarray):
        self.window_name = window_name
        self.frame = frame
        self.boxes: list[Box] = []
        self._drag_start: tuple[int, int] | None = None
        self._drag_current: tuple[int, int] | None = None

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self._drag_start = (x, y)
            self._drag_current = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self._drag_start is not None:
            self._drag_current = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self._drag_start is not None:
            x0, y0 = self._drag_start
            box = (min(x0, x), min(y0, y), abs(x - x0), abs(y - y0))
            self._drag_start = None
            self._drag_current = None
            if box[2] > 2 and box[3] > 2:
                self.boxes = [box]

    def _render(self) -> np.ndarray:
        canvas = self.frame.copy()
        for x, y, w, h in self.boxes:
            cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 0), 2)
        if self._drag_start is not None and self._drag_current is not None:
            cv2.rectangle(canvas, self._drag_start, self._drag_current, (0, 165, 255), 2)
        return canvas

    def run(self) -> list[Box]:
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._on_mouse)
        cv2.imshow(self.window_name, self._render())
        cv2.waitKey(1)
        _force_foreground(self.window_name)

        while True:
            cv2.imshow(self.window_name, self._render())
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord("q")):
                break
            if key in (8, ord("z")):
                self.boxes = []
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break

        cv2.destroyWindow(self.window_name)
        return self.boxes


class CornerPicker:
    """Collects 4 clicked points: top-left, top-right, bottom-right, bottom-left."""

    LABELS = ["верхний-левый", "верхний-правый", "нижний-правый", "нижний-левый"]

    def __init__(self, window_name: str, frame: np.ndarray):
        self.window_name = window_name
        self.frame = frame
        self.points: list[tuple[int, int]] = []

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONUP and len(self.points) < 4:
            self.points.append((x, y))

    def _render(self) -> np.ndarray:
        canvas = self.frame.copy()
        for i, (x, y) in enumerate(self.points):
            cv2.circle(canvas, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(canvas, str(i + 1), (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        if len(self.points) >= 2:
            cv2.polylines(canvas, [np.array(self.points)], len(self.points) == 4, (0, 255, 0), 2)
        next_label = self.LABELS[len(self.points)] if len(self.points) < 4 else "готово, ESC"
        cv2.putText(canvas, f"Кликните: {next_label}", (20, 40), cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 255, 255), 2)
        return canvas

    def run(self) -> list[tuple[int, int]]:
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._on_mouse)
        cv2.imshow(self.window_name, self._render())
        cv2.waitKey(1)
        _force_foreground(self.window_name)

        while True:
            cv2.imshow(self.window_name, self._render())
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord("q")):
                break
            if key in (8, ord("z")) and self.points:
                self.points.pop()
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break

        cv2.destroyWindow(self.window_name)
        return self.points


def grab_while_focused(window: GameWindow, delay_seconds: int = 5) -> np.ndarray:
    """Grabs a frame while the game still has focus.

    The game pauses with a 'click to continue' overlay as soon as it loses
    focus, so the frame must be captured BEFORE any calibration window opens.
    The countdown gives the user time to click into the game and unpause it.
    """
    window.bring_to_foreground()
    write_line(
        f"Кликните по окну игры, чтобы снять паузу. Снимок будет сделан через {delay_seconds} сек..."
    )
    for remaining in range(delay_seconds, 0, -1):
        print(f"  {remaining}...")
        time.sleep(1)
    frame = window.grab()
    write_line("Снимок сделан.")
    return frame


def calibrate_field(config: Config, window: GameWindow) -> None:
    frame = grab_while_focused(window)
    write_line(
        "Кликните 4 угла газона по порядку: верхний-левый, верхний-правый, "
        "нижний-правый, нижний-левый (внутренние края изгородей, от заднего "
        "заборчика до переднего). Backspace/z — отменить точку, ESC/q — закончить."
    )
    points = CornerPicker("Calibrate field", frame).run()

    if len(points) != 4:
        write_line(f"Нужно ровно 4 точки, получено {len(points)}. Конфиг не изменён.", MessageType.WARNING)
        return

    config.field_corners = [[int(x), int(y)] for x, y in points]
    config.save()
    write_line("Углы газона сохранены в config.json")


def calibrate_gameover(config: Config, window: GameWindow) -> None:
    frame = grab_while_focused(window)
    write_line("Выделите рамкой кнопку 'Играть Заново' на экране результатов. ESC/q — закончить.")
    boxes = BoxSelector("Calibrate game over screen", frame).run()

    if not boxes:
        write_line("Область не выделена, шаблон не сохранён.", MessageType.WARNING)
        return

    x, y, w, h = boxes[0]
    template_path = Path(config.gameover_template)
    template_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(template_path), cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY))
    write_line(f"Шаблон кнопки рестарта сохранён в {template_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["field", "gameover"])
    args = parser.parse_args()

    config = Config.load_or_init()
    window = GameWindow(config.window_title)
    window.find()

    if args.mode == "field":
        calibrate_field(config, window)
    elif args.mode == "gameover":
        calibrate_gameover(config, window)


if __name__ == "__main__":
    main()
