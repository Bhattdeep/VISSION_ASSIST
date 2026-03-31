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
from ranging import DistanceEstimator, DistanceSmoother


# ── Fixed fallback thresholds (used when no depth map available) ─────
ZONE_VERY_CLOSE = 0.70
ZONE_CLOSE      = 0.50
ZONE_MEDIUM     = 0.30

# ── Area thresholds for basic mode ───────────────────────────────────
AREA_CRITICAL = 80_000
AREA_WARNING  = 25_000
AREA_INFO     = 10_000

# Approximate distance thresholds for monocular camera ranging
DISTANCE_CRITICAL_CM = 120.0
DISTANCE_WARNING_CM  = 220.0
DISTANCE_INFO_CM     = 400.0


@dataclass
class NavigationAdvice:
    object_name : str
    depth_value : float
    h_position  : str       # "left" | "center" | "right"
    urgency     : str       # "critical" | "warning" | "info"
    message     : str
    distance_cm : Optional[float] = None
    fingerprint : str = ""


class Navigator:

    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width  = frame_width
        self.frame_height = frame_height
        self.distance_estimator = DistanceEstimator(
            frame_width=frame_width,
            frame_height=frame_height,
        )
        self.distance_smoother = DistanceSmoother()

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

            h_pos   = self._horizontal_zone(det.center_x)
            det.h_position = h_pos
            distance_cm = self._estimate_distance_cm(
                det,
                h_pos,
                depth_value=dv,
                p_far=p45,
                p_mid=p70,
                p_near=p90,
            )
            det.estimated_distance_cm = distance_cm
            if distance_cm is not None:
                urgency = self._urgency_distance(distance_cm)
                if urgency is None:
                    continue
            else:
                # Skip objects that are far away when only relative depth is available
                if dv < p45:
                    continue
                urgency = self._urgency_depth(dv, p70, p90)
            det.urgency = urgency
            msg = self._compose_message(det.class_name, h_pos, urgency, distance_cm)

            advice = NavigationAdvice(
                object_name = det.class_name,
                depth_value = dv,
                h_position  = h_pos,
                urgency     = urgency,
                message     = msg,
                distance_cm = distance_cm,
                fingerprint = self._fingerprint(det.class_name, h_pos, urgency),
            )

            if best is None or self._sort_key(advice) < self._sort_key(best):
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
            h_pos   = self._horizontal_zone(det.center_x)
            det.h_position = h_pos
            distance_cm = self._estimate_distance_cm(det, h_pos)
            det.estimated_distance_cm = distance_cm
            if distance_cm is not None:
                urgency = self._urgency_distance(distance_cm)
                if urgency is None:
                    continue
            else:
                if det.area < min_area:
                    continue
                urgency = self._urgency_area(det.area)
            det.urgency = urgency
            msg = self._compose_message(det.class_name, h_pos, urgency, distance_cm)

            advice = NavigationAdvice(
                object_name = det.class_name,
                depth_value = float(det.area),
                h_position  = h_pos,
                urgency     = urgency,
                message     = msg,
                distance_cm = distance_cm,
                fingerprint = self._fingerprint(det.class_name, h_pos, urgency),
            )

            if best is None or self._sort_key(advice) < self._sort_key(best):
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

    @staticmethod
    def _urgency_distance(distance_cm: float) -> Optional[str]:
        if distance_cm <= DISTANCE_CRITICAL_CM:
            return "critical"
        if distance_cm <= DISTANCE_WARNING_CM:
            return "warning"
        if distance_cm <= DISTANCE_INFO_CM:
            return "info"
        return None

    # ── message composition ─────────────────────────────────────────
    @staticmethod
    def _compose_message(
        name: str,
        position: str,
        urgency: str,
        distance_cm: Optional[float] = None,
    ) -> str:
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

        if distance_cm is not None:
            rounded = DistanceEstimator.rounded_cm(distance_cm, step=10)
            distance_phrase = f" about {rounded} centimeters away"
        else:
            distance_phrase = ""

        if urgency == "critical":
            if distance_phrase:
                return f"Warning! {n}{distance_phrase} {location}. {action}"
            return f"Warning! {n} very close {location}. {action}"
        elif urgency == "warning":
            if distance_phrase:
                return f"{n}{distance_phrase} {location}. {action}"
            return f"{n} {location}. {action}"
        else:
            if distance_phrase:
                return f"{n}{distance_phrase} {location}. {action}"
            return f"{n} nearby {location}. {action}"

    # ── priority ────────────────────────────────────────────────────
    @staticmethod
    def _priority(advice: NavigationAdvice) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(advice.urgency, 3)

    @classmethod
    def _sort_key(cls, advice: NavigationAdvice):
        secondary = advice.distance_cm if advice.distance_cm is not None else -advice.depth_value
        return (cls._priority(advice), secondary)

    @staticmethod
    def _fingerprint(name: str, position: str, urgency: str) -> str:
        return f"{name.lower()}:{position}:{urgency}"

    def _estimate_distance_cm(
        self,
        det: Detection,
        h_pos: str,
        depth_value: Optional[float] = None,
        p_far: Optional[float] = None,
        p_mid: Optional[float] = None,
        p_near: Optional[float] = None,
    ) -> Optional[float]:
        raw_cm = self.distance_estimator.estimate_detection_cm(det)
        raw_cm = self.distance_estimator.apply_depth_hint(
            raw_cm,
            depth_value,
            p_far,
            p_mid,
            p_near,
        )
        if raw_cm is None:
            return None

        key = self.distance_estimator.track_key(det, h_pos)
        return self.distance_smoother.update(key, raw_cm)

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
