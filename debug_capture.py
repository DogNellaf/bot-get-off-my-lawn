"""Captures a series of gameplay frames for detection tuning.

Run the game, then:  python debug_capture.py
It brings the game to the foreground, clicks to unpause, and for ~10 seconds
saves two images per second into calibration/captures/:
  frame_NN.png           - the raw frame
  frame_NN_annotated.png - field trapezoid, detected aliens and their lanes
Play normally (or let aliens walk in) while it captures.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from bot.config import Config
from bot.input_controller import InputController
from bot.logger import write_line
from bot.vision import AlienVision, FieldGeometry
from bot.window import GameWindow

CAPTURE_DIR = Path("calibration/captures")
DURATION_SECONDS = 10
FRAMES_PER_SECOND = 2


def main() -> None:
    config = Config.load_or_init()
    window = GameWindow(config.window_title)
    window.find()
    window.bring_to_foreground()

    geometry = FieldGeometry(config.field_corners, config.lane_count)
    vision = AlienVision(
        geometry, config.alien_hsv_lower, config.alien_hsv_upper, config.min_blob_area
    )

    input_ctrl = InputController(
        config.lane_count, config.move_left_key, config.move_right_key, config.fire_key
    )
    time.sleep(0.3)
    cx, cy = window.center_screen_point()
    input_ctrl.click(cx, cy)
    write_line("Кликнул по игре для снятия паузы. Захват начнётся через 2 секунды...")
    time.sleep(2.0)

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    total = DURATION_SECONDS * FRAMES_PER_SECOND
    for n in range(total):
        frame = window.grab()
        cv2.imwrite(str(CAPTURE_DIR / f"frame_{n:02d}.png"), frame)

        annotated = frame.copy()
        corners = np.array(config.field_corners)
        cv2.polylines(annotated, [corners], True, (0, 255, 0), 2)
        for lane in range(config.lane_count):
            x0, y0 = geometry.lane_center_at(lane, 0.0)
            x1, y1 = geometry.lane_center_at(lane, 1.0)
            cv2.line(annotated, (x0, y0), (x1, y1), (0, 200, 200), 1)
            cv2.putText(annotated, str(lane), (x1 - 8, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 200), 2)

        aliens = vision.detect(frame)
        for a in aliens:
            cv2.circle(annotated, (a.x, a.y), 8, (0, 0, 255), -1)
            cv2.putText(
                annotated,
                f"L{a.lane} p{a.progress:.2f}",
                (a.x + 12, a.y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )
        cv2.imwrite(str(CAPTURE_DIR / f"frame_{n:02d}_annotated.png"), annotated)
        write_line(f"Кадр {n + 1}/{total}: пришельцев {len(aliens)}")
        time.sleep(1.0 / FRAMES_PER_SECOND)

    write_line(f"Готово, кадры в {CAPTURE_DIR}")


if __name__ == "__main__":
    main()
