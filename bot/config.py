from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

from bot.logger import MessageType, write_line

VERSION = "2.0.0"
CONFIG_PATH = Path("config.json")


@dataclass
class Config:
    supported_app_version: str = VERSION

    window_title: str = "Get Off My Lawn"

    lane_count: int = 7
    # Lawn trapezoid corners in client-area pixels: top-left, top-right,
    # bottom-right, bottom-left. Refine with `python calibrate.py field`.
    field_corners: List[List[int]] = field(
        default_factory=lambda: [[770, 200], [1225, 200], [1550, 690], [355, 690]]
    )

    # Aliens' blue body color in HSV (measured from real frames: H 109-117,
    # S 124-225, V up to 240; grass is H~23, bricks H~14, sky is desaturated).
    alien_hsv_lower: List[int] = field(default_factory=lambda: [95, 80, 100])
    alien_hsv_upper: List[int] = field(default_factory=lambda: [130, 255, 255])
    min_blob_area: int = 300

    # "keyboard": move between lanes with keys and fire.
    # "mouse": click directly on aliens (the game is a mobile port, so tapping
    # the target is likely the native control scheme).
    control_mode: str = "keyboard"

    move_left_key: str = "a"
    move_right_key: str = "d"
    fire_key: str = "space"

    # Emergency power-ups: client-area coords of the HUD buttons (Soundwave
    # ear, Cane Time clock, Infuriate heart) clicked when an alien is about to
    # reach the fence and Murray can't get there in time.
    powerup_points: List[List[int]] = field(
        default_factory=lambda: [[1596, 998], [1737, 1000], [1857, 1005]]
    )
    powerup_threshold: float = 0.82
    powerup_cooldown: float = 12.0

    step_cooldown: float = 0.03
    restart_wait: float = 3.0

    gameover_template: str = "calibration/gameover.png"

    # Shop flow (all points are client-area coords on 1920x1080).
    shop_enabled: bool = True
    shop_every_runs: int = 3
    # "Пойти на склад" button on the results screen.
    shop_button_point: List[int] = field(default_factory=lambda: [1630, 540])
    # Left-most fully visible carousel card: clicking it attempts a purchase.
    shop_card_point: List[int] = field(default_factory=lambda: [470, 530])
    # Right carousel arrow, advances the item list by one.
    shop_arrow_point: List[int] = field(default_factory=lambda: [1723, 750])
    # Home button that leaves the shop.
    shop_home_point: List[int] = field(default_factory=lambda: [1290, 985])
    shop_carousel_length: int = 8

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load_or_init(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            write_line(f"Конфиг {path} не найден, создаю новый со значениями по умолчанию", MessageType.WARNING)
            config = cls()
            config.save(path)
            return config

        raw = json.loads(path.read_text(encoding="utf-8"))
        stored_version = raw.get("supported_app_version", "0.0.0")

        if stored_version.split(".")[0] != VERSION.split(".")[0]:
            write_line(
                f"Конфиг от версии {stored_version} несовместим с текущей {VERSION}. "
                f"Создаю новый (старые ключи из него будут потеряны).",
                MessageType.WARNING,
            )
            config = cls()
            config.save(path)
            return config

        config = cls()
        for key, value in raw.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config
