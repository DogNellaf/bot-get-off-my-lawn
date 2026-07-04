from __future__ import annotations

import time

import pydirectinput

pydirectinput.PAUSE = 0.0


class InputController:
    """Sends keyboard input to the game via DirectInput-compatible SendInput calls."""

    def __init__(
        self,
        lane_count: int,
        move_left_key: str,
        move_right_key: str,
        fire_key: str,
        key_press_duration: float = 0.05,
    ):
        self.lane_count = lane_count
        self.move_left_key = move_left_key
        self.move_right_key = move_right_key
        self.fire_key = fire_key
        self.key_press_duration = key_press_duration
        self.current_lane = lane_count // 2

    def reset_position(self) -> None:
        """Assumes the character starts centered; call after a restart."""
        self.current_lane = self.lane_count // 2

    def hard_resync(self) -> None:
        """Walks all the way left (extra presses past the edge do nothing) so
        the lane counter is guaranteed to match reality again. Needed after
        any in-game mouse click: a click can move Murray and desync the
        counter."""
        for _ in range(self.lane_count + 1):
            self.tap(self.move_left_key)
        self.current_lane = 0

    def move_to_lane(self, target_lane: int, fire_between_steps: bool = False) -> None:
        target_lane = max(0, min(self.lane_count - 1, target_lane))
        while self.current_lane != target_lane:
            key = self.move_right_key if target_lane > self.current_lane else self.move_left_key
            self.tap(key)
            self.current_lane += 1 if target_lane > self.current_lane else -1
            # A shot on every lane crossed costs nothing and clips aliens we
            # pass over on the way to the main target.
            if fire_between_steps and self.current_lane != target_lane:
                self.fire()

    def fire(self) -> None:
        self.tap(self.fire_key)

    def tap(self, key: str, duration: float | None = None) -> None:
        pydirectinput.keyDown(key)
        time.sleep(duration if duration is not None else self.key_press_duration)
        pydirectinput.keyUp(key)
        time.sleep(0.01)

    def click(self, x: int, y: int) -> None:
        pydirectinput.moveTo(x, y)
        time.sleep(0.05)
        pydirectinput.click(x, y)
