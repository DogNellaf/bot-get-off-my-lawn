"""Records the shop/warehouse UI so the buying flow can be automated.

Run the game, get to the results screen (or main menu), then run:

  python explore_shop.py

While it captures (one frame per second for 60 seconds), navigate the shop
manually with the mouse: open the warehouse, switch tabs, hover items, open a
weapon's page, etc. Frames land in calibration/shop/.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2

from bot.config import Config
from bot.logger import write_line
from bot.window import GameWindow

CAPTURE_DIR = Path("calibration/shop")
DURATION_SECONDS = 60


def main() -> None:
    config = Config.load_or_init()
    window = GameWindow(config.window_title)
    window.find()
    window.bring_to_foreground()

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    write_line(
        f"Захват начался: {DURATION_SECONDS} секунд, кадр в секунду. "
        "Ходите по складу мышью: вкладки, товары, покупка, выбор оружия."
    )
    for n in range(DURATION_SECONDS):
        frame = window.grab()
        cv2.imwrite(str(CAPTURE_DIR / f"shop_{n:02d}.png"), frame)
        if n % 5 == 0:
            write_line(f"{DURATION_SECONDS - n} сек осталось...")
        time.sleep(1.0)

    write_line(f"Готово, кадры в {CAPTURE_DIR}")


if __name__ == "__main__":
    main()
