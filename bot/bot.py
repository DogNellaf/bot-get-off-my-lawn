from __future__ import annotations

import time
from pathlib import Path

import cv2

from bot.config import Config
from bot.input_controller import InputController
from bot.logger import MessageType, write_line
from bot.vision import Alien, AlienVision, FieldGeometry, GameOverDetector, PauseDetector, annotate
from bot.window import GameWindow

INCIDENT_DIR = Path("calibration/incidents")
SHOP_VISIT_DIR = Path("calibration/shop_visits")
DEBUG_FRAMES_DIR = Path("calibration/debug_frames")
# Ring buffer size: at ~2 frames/sec this keeps the last few minutes.
DEBUG_FRAMES_KEEP = 400


class LawnBot:
    def __init__(self, config: Config, debug: bool = False):
        self.config = config
        self.debug = debug
        self._last_debug_time = 0.0
        self.window = GameWindow(config.window_title)
        self.input = InputController(
            lane_count=config.lane_count,
            move_left_key=config.move_left_key,
            move_right_key=config.move_right_key,
            fire_key=config.fire_key,
        )
        self.geometry = FieldGeometry(config.field_corners, config.lane_count)
        self.vision = AlienVision(
            geometry=self.geometry,
            hsv_lower=config.alien_hsv_lower,
            hsv_upper=config.alien_hsv_upper,
            min_blob_area=config.min_blob_area,
        )
        self.game_over = GameOverDetector(Path(config.gameover_template))
        self.pause = PauseDetector()
        self.runs_completed = 0
        self._last_target_lane: int | None = None
        self._idle_steps = 0
        self._last_incident_time = 0.0
        self._incident_counter = 0
        self._last_powerup_time = 0.0
        self._powerup_index = 0
        self._debug_frame_counter = 0
        self._last_debug_frame_time = 0.0
        # Per-lane threat memory (decayed max alien progress). Survives the
        # frames where a hit alien flashes white and briefly drops out of the
        # color mask, so the bot doesn't abandon a lane mid-kill.
        self._lane_threat = [0.0] * config.lane_count
        self._target_empty_streak = 0

    def _client_to_screen(self, x: int, y: int) -> tuple[int, int]:
        r = self.window.rect()
        return r.left + x, r.top + y

    def _debug_log(self, aliens: list[Alien], target_lane: int | None) -> None:
        if not self.debug or time.time() - self._last_debug_time < 1.0:
            return
        self._last_debug_time = time.time()
        if not aliens and target_lane is None:
            write_line("Пришельцев не видно")
            return
        parts = " ".join(
            f"[дорожка {a.lane}, прогресс {a.progress:.2f}, площадь {a.area}]" for a in aliens
        )
        threats = " ".join(f"{t:.2f}" for t in self._lane_threat)
        write_line(
            f"Вижу {len(aliens)}: {parts} | угрозы: {threats} | цель: {target_lane}, "
            f"Мюррей: {self.input.current_lane}"
        )

    def step(self) -> None:
        frame = self.window.grab()

        if self.pause.is_paused(frame):
            write_line("Игра на паузе — кликаю, чтобы продолжить.", MessageType.WARNING)
            self.input.click(*self._client_to_screen(*self.pause.click_point()))
            time.sleep(0.7)
            return

        restart_button = self.game_over.find_restart_button(frame)
        if restart_button is not None:
            self.runs_completed += 1
            if self.config.shop_enabled and self.runs_completed % self.config.shop_every_runs == 0:
                self._visit_shop()
                # The results screen is re-detected on the next step, and the
                # restart happens then (or we notice the shop dropped us
                # somewhere else and the recorder shows where).
                return
            write_line(
                f"Забег #{self.runs_completed} окончен. Кликаю 'Играть Заново' и начинаю следующий."
            )
            sx, sy = self._client_to_screen(*restart_button)
            self.input.click(sx, sy)
            time.sleep(self.config.restart_wait)
            self.input.reset_position()
            return

        aliens = self.vision.detect(frame)
        target_lane = self._pick_target_lane(aliens)
        self._debug_log(aliens, target_lane)
        self._record_incident(frame, aliens)
        self._record_debug_frame(frame, aliens, target_lane)

        if self.config.control_mode == "mouse":
            if aliens:
                closest = max(aliens, key=lambda a: a.progress)
                sx, sy = self._client_to_screen(closest.x, closest.y)
                self.input.click(sx, sy)
        else:
            if target_lane is not None:
                self._idle_steps = 0
                self._maybe_use_powerup()
                self.input.move_to_lane(target_lane, fire_between_steps=True)
                self._last_target_lane = target_lane
            else:
                self._last_target_lane = None
                self._resync_when_idle()
            self.input.fire()

    def _record_debug_frame(self, frame, aliens: list[Alien], target_lane: int | None) -> None:
        """In --debug, continuously saves annotated frames into a ring buffer
        (calibration/debug_frames/) so detection can be reviewed after a run."""
        if not self.debug or time.time() - self._last_debug_frame_time < 0.5:
            return
        self._last_debug_frame_time = time.time()
        DEBUG_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        canvas = annotate(frame, self.geometry, aliens)
        threats = " ".join(f"{t:.2f}" for t in self._lane_threat)
        cv2.putText(
            canvas,
            f"murray:{self.input.current_lane} target:{target_lane} threats:[{threats}]",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            2,
        )
        index = self._debug_frame_counter % DEBUG_FRAMES_KEEP
        self._debug_frame_counter += 1
        cv2.imwrite(str(DEBUG_FRAMES_DIR / f"dbg_{index:03d}.png"), canvas)

    def _click_client_point(self, point: list[int], pause: float) -> None:
        sx, sy = self._client_to_screen(point[0], point[1])
        self.input.click(sx, sy)
        time.sleep(pause)

    def _shop_snapshot(self, tag: str) -> None:
        SHOP_VISIT_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOP_VISIT_DIR / f"run{self.runs_completed:03d}_{tag}.png"
        cv2.imwrite(str(path), self.window.grab())

    def _visit_shop(self) -> None:
        """From the results screen: open the warehouse, attempt to buy every
        carousel item in order (a click on an unaffordable card does nothing),
        then leave through the home button.

        Every stage is snapshotted to calibration/shop_visits/ so the flow can
        be verified and tuned from real frames."""
        write_line(f"Забег #{self.runs_completed} окончен. Захожу на склад за покупками.")
        self._click_client_point(self.config.shop_button_point, pause=2.0)
        self._shop_snapshot("entered")

        for slot in range(self.config.shop_carousel_length):
            self._click_client_point(self.config.shop_card_point, pause=0.7)
            if slot == 0:
                self._shop_snapshot("first_buy_attempt")
            self._click_client_point(self.config.shop_arrow_point, pause=0.7)

        self._shop_snapshot("before_leaving")
        self._click_client_point(self.config.shop_home_point, pause=2.5)
        self._shop_snapshot("after_leaving")
        write_line("Склад пройден, возвращаюсь к игре.")

    def _maybe_use_powerup(self) -> None:
        """Emergency brake: an alien is nearly at the fence and Murray is too
        far to save it with the musket — click a power-up button in the HUD
        (Soundwave/Cane Time/Infuriate, cycled since charges are limited)."""
        if not self.config.powerup_points:
            return
        if time.time() - self._last_powerup_time < self.config.powerup_cooldown:
            return
        critical = [
            lane
            for lane, t in enumerate(self._lane_threat)
            if t >= self.config.powerup_threshold and abs(lane - self.input.current_lane) >= 2
        ]
        if not critical:
            return
        self._last_powerup_time = time.time()
        point = self.config.powerup_points[self._powerup_index % len(self.config.powerup_points)]
        self._powerup_index += 1
        sx, sy = self._client_to_screen(point[0], point[1])
        self.input.click(sx, sy)
        write_line(
            f"Не успеваю к дорожке {critical[0]} — применяю спецспособность #{self._powerup_index}"
        )

    def _pick_target_lane(self, aliens: list[Alien]) -> int | None:
        """Chooses which lane to shoot based on decayed per-lane threat.

        Committing to a lane matters: armored aliens take several hits, and
        walking away half-way loses all progress. The bot switches lanes only
        when another lane is clearly more urgent than the one it's clearing
        (or the current lane is empty)."""
        # What we actually see this frame, spread over every lane a wide
        # target (like the alien car) covers.
        seen = [0.0] * len(self._lane_threat)
        for a in aliens:
            for lane in range(a.lane_span[0], a.lane_span[1] + 1):
                seen[lane] = max(seen[lane], min(a.progress, 1.0))

        if self._last_target_lane is not None and seen[self._last_target_lane] == 0.0:
            self._target_empty_streak += 1
        else:
            self._target_empty_streak = 0

        for lane, old in enumerate(self._lane_threat):
            if seen[lane] > 0.0:
                self._lane_threat[lane] = max(seen[lane], old - 0.06)
            elif lane == self._last_target_lane and self._target_empty_streak >= 2:
                # Murray is staring at this lane and it's been empty for
                # several frames — the kill is confirmed, forget the ghost
                # fast instead of shooting air for seconds while fresh spawns
                # wait elsewhere. (A single empty frame can just be a hit
                # alien flashing white, hence the streak.)
                self._lane_threat[lane] = max(0.0, old * 0.5 - 0.02)
            else:
                # Unwatched lanes decay slowly: a hit alien flashing white can
                # drop out of the color mask for a few frames.
                self._lane_threat[lane] = max(0.0, old - 0.06)

        if max(self._lane_threat) <= 0.0:
            return None

        def urgency(lane: int) -> float:
            return self._lane_threat[lane] - 0.04 * abs(lane - self.input.current_lane)

        best = max(range(len(self._lane_threat)), key=urgency)
        current = self._last_target_lane

        if current is not None and self._lane_threat[current] > 0.0:
            # Stay on the current lane unless the challenger is clearly worse off.
            if urgency(best) > urgency(current) + 0.10:
                return best
            return current
        return best

    def _record_incident(self, frame, aliens: list[Alien]) -> None:
        """Black-box recorder: when an alien is about to reach the fence, save
        an annotated frame so the miss can be analyzed afterwards."""
        leaked = [a for a in aliens if a.progress >= 0.85]
        if not leaked or time.time() - self._last_incident_time < 2.0:
            return
        self._last_incident_time = time.time()
        INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
        self._incident_counter += 1
        path = INCIDENT_DIR / f"incident_{self._incident_counter:03d}.png"
        canvas = annotate(frame, self.geometry, aliens)
        cv2.putText(
            canvas,
            f"bot lane: {self.input.current_lane}",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 255),
            3,
        )
        cv2.imwrite(str(path), canvas)
        if self.debug:
            write_line(f"Пришелец у забора — сохранил кадр в {path}", MessageType.WARNING)

    def _resync_when_idle(self) -> None:
        """If a keypress ever gets dropped by the game, our lane counter drifts
        from Murray's real position — and stays wrong forever. While the lawn
        is empty there is nothing to lose, so walk far left (extra presses past
        lane 0 are ignored by the game) and back to the center to restore a
        known position."""
        self._idle_steps += 1
        if self._idle_steps != 10:
            return
        for _ in range(self.input.lane_count - 1):
            self.input.tap(self.input.move_left_key, duration=0.03)
        self.input.current_lane = 0
        self.input.move_to_lane(self.input.lane_count // 2)
        self._last_target_lane = None
        if self.debug:
            write_line("Газон пуст — синхронизировал позицию Мюррея (в центр).")

    def run_forever(self) -> None:
        if not self.game_over.is_calibrated:
            write_line(
                "Шаблон кнопки рестарта не найден — бот не сможет перезапускать забег. "
                "Выполните 'python calibrate.py gameover' на экране результатов.",
                MessageType.WARNING,
            )

        self.window.find()
        write_line(
            f"Окно игры найдено, режим управления: {self.config.control_mode}. "
            "Ctrl+C для остановки."
        )
        self.window.bring_to_foreground()
        time.sleep(0.3)
        # The game pauses with a "click to continue" overlay whenever it loses
        # focus, and only a mouse click dismisses it.
        cx, cy = self.window.center_screen_point()
        self.input.click(cx, cy)
        write_line("Кликнул по центру окна игры, чтобы снять паузу.")
        time.sleep(0.5)

        try:
            while True:
                self.step()
                time.sleep(self.config.step_cooldown)
        except KeyboardInterrupt:
            write_line("Остановлено пользователем.", MessageType.INFO)
