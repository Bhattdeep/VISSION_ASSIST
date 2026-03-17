"""
navigation.py — Obstacle position analysis and navigation message generation.

Depth convention (MiDaS)
-------------------------
After cv2.NORM_MINMAX normalisation:
    value near 1.0 = object is VERY CLOSE  (high disparity)
    value near 0.0 = object is VERY FAR    (low disparity)

Percentile-based thresholds (new)
-----------------------------------
Instead of fixed values (0.30 / 0.50 / 0.70), we compute thresholds
relative to the SCENE's 75th percentile so they adapt when everything
in the frame is at similar depth.

    critical : object_depth  >= scene_p75 * 0.95   (top of scene depth)
    warning  : object_depth  >= scene_p75 * 0.70
    info     : object_depth  >= scene_p75 * 0.45
    ignore   : object_depth  <  scene_p75 * 0.45

This means "closest objects in the scene" always trigger an alert, which
is the correct behaviour for obstacle avoidance.

Zone split (30 / 40 / 30)
--------------------------
    left   : cx  <  30% of frame width
    center : cx  30%–70%   (wide enough to absorb YOLO jitter)
    right  : cx  >  70% of frame width
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from detection import Detection


# ── Fixed fallback thresholds (used when no depth map available) ─────
ZONE_VERY_CLOSE = 0.70
ZONE_CLOSE      = 0.50
ZONE_MEDIUM     = 0.30

# ── Area thresholds for basic mode ───────────────────────────────────
AREA_CRITICAL = 80_000
AREA_WARNING  = 25_000
AREA_INFO     = 10_000


@dataclass
class NavigationAdvice:
    object_name : str
    depth_value : float
    h_position  : str       # "left" | "center" | "right"
    urgency     : str       # "critical" | "warning" | "info"
    message     : str


class Navigator:

    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width  = frame_width
        self.frame_height = frame_height

    # ── depth-aware analysis (upgraded mode) ────────────────────────
    def analyse(
        self,
        detections : List[Detection],
        depth_map,
    ) -> Optional[NavigationAdvice]:

        if depth_map is None or not detections:
            return None

        # Compute adaptive thresholds from this frame's depth distribution
        try:
            flat   = depth_map.ravel()
            p45    = float(np.percentile(flat, 45))
            p70    = float(np.percentile(flat, 70))
            p90    = float(np.percentile(flat, 90))
        except Exception:
            p45, p70, p90 = ZONE_MEDIUM, ZONE_CLOSE, ZONE_VERY_CLOSE

        # Guard: if the scene is totally flat, use fixed fallbacks
        if (p90 - p45) < 0.10:
            p45, p70, p90 = ZONE_MEDIUM, ZONE_CLOSE, ZONE_VERY_CLOSE

        best: Optional[NavigationAdvice] = None

        for det in detections:
            dv = self._sample_depth(depth_map, det.center_x, det.center_y)

            # Skip objects that are far away
            if dv < p45:
                continue

            h_pos   = self._horizontal_zone(det.center_x)
            urgency = self._urgency_depth(dv, p70, p90)
            msg     = self._compose_message(det.class_name, h_pos, urgency)

            advice = NavigationAdvice(
                object_name = det.class_name,
                depth_value = dv,
                h_position  = h_pos,
                urgency     = urgency,
                message     = msg,
            )

            if best is None or self._priority(advice) < self._priority(best):
                best = advice
            elif self._priority(advice) == self._priority(best) and dv > best.depth_value:
                best = advice

        return best

    # ── area-based analysis (basic mode, no depth) ──────────────────
    def analyse_by_area(
        self,
        detections : List[Detection],
        min_area   : int = AREA_INFO,
    ) -> Optional[NavigationAdvice]:

        best: Optional[NavigationAdvice] = None

        for det in detections:
            if det.area < min_area:
                continue

            h_pos   = self._horizontal_zone(det.center_x)
            urgency = self._urgency_area(det.area)
            msg     = self._compose_message(det.class_name, h_pos, urgency)

            advice = NavigationAdvice(
                object_name = det.class_name,
                depth_value = float(det.area),
                h_position  = h_pos,
                urgency     = urgency,
                message     = msg,
            )

            if best is None or self._priority(advice) < self._priority(best):
                best = advice
            elif self._priority(advice) == self._priority(best) and det.area > best.depth_value:
                best = advice

        return best

    # ── horizontal zone ─────────────────────────────────────────────
    def _horizontal_zone(self, cx: int) -> str:
        left_edge  = int(self.frame_width * 0.30)
        right_edge = int(self.frame_width * 0.70)
        if cx < left_edge:
            return "left"
        if cx > right_edge:
            return "right"
        return "center"

    # ── urgency ─────────────────────────────────────────────────────
    @staticmethod
    def _urgency_depth(dv: float, p_warn: float, p_crit: float) -> str:
        if dv >= p_crit:
            return "critical"
        if dv >= p_warn:
            return "warning"
        return "info"

    @staticmethod
    def _urgency_area(area: int) -> str:
        if area >= AREA_CRITICAL:
            return "critical"
        if area >= AREA_WARNING:
            return "warning"
        return "info"

    # ── message composition ─────────────────────────────────────────
    @staticmethod
    def _compose_message(name: str, position: str, urgency: str) -> str:
        n = name.capitalize()

        if position == "center":
            location = "directly ahead"
            action   = "Move left or right to avoid."
        elif position == "left":
            location = "on your left"
            action   = "Move right."
        else:
            location = "on your right"
            action   = "Move left."

        if urgency == "critical":
            return f"Warning! {n} very close {location}. {action}"
        elif urgency == "warning":
            return f"{n} {location}. {action}"
        else:
            return f"{n} nearby {location}. {action}"

    # ── priority ────────────────────────────────────────────────────
    @staticmethod
    def _priority(advice: NavigationAdvice) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(advice.urgency, 3)

    # ── depth sampler ───────────────────────────────────────────────
    @staticmethod
    def _sample_depth(depth_map, cx: int, cy: int, radius: int = 12) -> float:
        try:
            h, w   = depth_map.shape
            region = depth_map[
                max(0, cy - radius): min(h, cy + radius),
                max(0, cx - radius): min(w, cx + radius),
            ]
            if region.size > 0:
                return float(np.mean(region))
        except Exception:
            pass
        return 0.0