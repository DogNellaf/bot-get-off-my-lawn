from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Alien:
    x: int          # blob centroid, client-area pixels
    y: int
    area: int
    lane: int       # 0..lane_count-1
    progress: float  # 0.0 = back fence, 1.0 = front fence (about to score)
    # Wide targets (e.g. the alien car) cover several lanes at once.
    lane_span: Tuple[int, int] = (0, 0)


class FieldGeometry:
    """Maps a point on the 3D-perspective lawn to a lane index.

    The lawn is a trapezoid (lanes converge toward the back), defined by its
    four corners: top-left, top-right, bottom-right, bottom-left.
    """

    def __init__(self, corners: List[List[int]], lane_count: int):
        (self.tlx, self.tly), (self.trx, self.try_), (self.brx, self.bry), (self.blx, self.bly) = (
            tuple(c) for c in corners
        )
        self.lane_count = lane_count
        self.top_y = (self.tly + self.try_) / 2
        self.bottom_y = (self.bry + self.bly) / 2

    def progress(self, y: float) -> float:
        return (y - self.top_y) / max(1.0, self.bottom_y - self.top_y)

    def contains(self, x: float, y: float, margin: float = 0.02) -> bool:
        t = self.progress(y)
        if t < -margin or t > 1 + margin:
            return False
        left = self.tlx + (self.blx - self.tlx) * t
        right = self.trx + (self.brx - self.trx) * t
        return left <= x <= right

    def lane_of(self, x: float, y: float) -> int:
        t = min(1.0, max(0.0, self.progress(y)))
        left = self.tlx + (self.blx - self.tlx) * t
        right = self.trx + (self.brx - self.trx) * t
        frac = (x - left) / max(1.0, right - left)
        return min(self.lane_count - 1, max(0, int(frac * self.lane_count)))

    def lane_width_at(self, y: float) -> float:
        t = min(1.0, max(0.0, self.progress(y)))
        left = self.tlx + (self.blx - self.tlx) * t
        right = self.trx + (self.brx - self.trx) * t
        return (right - left) / self.lane_count

    def lane_center_at(self, lane: int, t: float) -> Tuple[int, int]:
        """Client-area point at the center of `lane` at progress t (0=back, 1=front)."""
        left = self.tlx + (self.blx - self.tlx) * t
        right = self.trx + (self.brx - self.trx) * t
        x = left + (right - left) * (lane + 0.5) / self.lane_count
        y = self.top_y + (self.bottom_y - self.top_y) * t
        return int(x), int(y)


class AlienVision:
    """Finds aliens by their distinctive blue color inside the lawn trapezoid."""

    def __init__(
        self,
        geometry: FieldGeometry,
        hsv_lower: List[int],
        hsv_upper: List[int],
        min_blob_area: int,
        max_blob_area: int = 60000,
    ):
        self.geometry = geometry
        self.hsv_lower = np.array(hsv_lower, dtype=np.uint8)
        self.hsv_upper = np.array(hsv_upper, dtype=np.uint8)
        self.min_blob_area = min_blob_area
        self.max_blob_area = max_blob_area

    def mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)
        # Fuse an alien's head/body/hands into one blob and drop speckles.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def detect(self, frame: np.ndarray) -> List[Alien]:
        mask = self.mask(frame)
        n, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        aliens: List[Alien] = []
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            # Too small = speckle noise; too big = a screen-wide element like
            # the blue sky on transition screens, not an alien.
            if area < self.min_blob_area or area > self.max_blob_area:
                continue
            cx, cy = centroids[i]
            # Use the blob's bottom edge for lane mapping: an alien's feet sit
            # on the lawn, its body leans over neighbouring rows visually.
            bottom_y = int(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT])
            if not self.geometry.contains(cx, bottom_y):
                continue
            # A regular walker belongs to exactly one lane (its centroid's) —
            # even when its body grazes a boundary line. Only genuinely wide
            # targets like the alien car (1.4+ lane widths) spread their
            # threat over the lanes they cover.
            left = int(stats[i, cv2.CC_STAT_LEFT])
            width = int(stats[i, cv2.CC_STAT_WIDTH])
            lane = self.geometry.lane_of(cx, bottom_y)
            if width >= 1.4 * self.geometry.lane_width_at(bottom_y):
                lane_lo = self.geometry.lane_of(left + width * 0.25, bottom_y)
                lane_hi = self.geometry.lane_of(left + width * 0.75, bottom_y)
            else:
                lane_lo = lane_hi = lane
            aliens.append(
                Alien(
                    x=int(cx),
                    y=bottom_y,
                    area=area,
                    lane=lane,
                    progress=self.geometry.progress(bottom_y),
                    lane_span=(lane_lo, lane_hi),
                )
            )
        return aliens


def annotate(frame: np.ndarray, geometry: FieldGeometry, aliens: List[Alien]) -> np.ndarray:
    """Draws the field trapezoid, lane centerlines and detected aliens —
    used by debug captures and the incident recorder."""
    canvas = frame.copy()
    corners = np.array(
        [
            [geometry.tlx, geometry.tly],
            [geometry.trx, geometry.try_],
            [geometry.brx, geometry.bry],
            [geometry.blx, geometry.bly],
        ]
    )
    cv2.polylines(canvas, [corners], True, (0, 255, 0), 2)
    for lane in range(geometry.lane_count):
        x0, y0 = geometry.lane_center_at(lane, 0.0)
        x1, y1 = geometry.lane_center_at(lane, 1.0)
        cv2.line(canvas, (x0, y0), (x1, y1), (0, 200, 200), 1)
        cv2.putText(canvas, str(lane), (x1 - 8, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 200), 2)
    for a in aliens:
        cv2.circle(canvas, (a.x, a.y), 8, (0, 0, 255), -1)
        cv2.putText(
            canvas,
            f"L{a.lane} p{a.progress:.2f}",
            (a.x + 12, a.y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
    return canvas


class PauseDetector:
    """Detects the 'click here to continue' overlay that the game shows
    whenever its window loses focus mid-run.

    The overlay is a big dark TV screen with bright white text sitting over
    the middle of the lawn — during normal play that area is green grass, on
    the results screen it's a hedge, so 'very dark with a chunk of white
    pixels' is a reliable signature."""

    def __init__(self, check_rect: Tuple[int, int, int, int] = (800, 430, 480, 180)):
        self.check_rect = check_rect

    def is_paused(self, frame: np.ndarray) -> bool:
        x, y, w, h = self.check_rect
        if frame.shape[0] < y + h or frame.shape[1] < x + w:
            return False
        gray = cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
        white_ratio = np.count_nonzero(gray > 200) / gray.size
        # Measured: pause overlay ~ mean 78 / 15% white; gameplay 0-2% white;
        # the bright white shop cards are excluded by the mean cap.
        return float(np.mean(gray)) < 100 and white_ratio > 0.08

    def click_point(self) -> Tuple[int, int]:
        x, y, w, h = self.check_rect
        return x + w // 2, y + h // 2


class GameOverDetector:
    """Finds the restart button ('Play Again') via template matching and
    reports where it is, so the bot can click it."""

    def __init__(self, template_path: Path, match_threshold: float = 0.8):
        self.template_path = template_path
        self.match_threshold = match_threshold
        self.template = None
        if template_path.exists():
            self.template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)

    @property
    def is_calibrated(self) -> bool:
        return self.template is not None

    def find_restart_button(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """Returns the button center in client-area coordinates, or None."""
        if self.template is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        th, tw = self.template.shape
        if gray.shape[0] < th or gray.shape[1] < tw:
            return None
        result = cv2.matchTemplate(gray, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < self.match_threshold:
            return None
        return max_loc[0] + tw // 2, max_loc[1] + th // 2
