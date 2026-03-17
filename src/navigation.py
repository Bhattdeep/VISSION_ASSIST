"""
navigation.py — Obstacle position analysis and navigation message generation.

Fixes in this version
---------------------
1. Narrower center zone: 40% left / 20% center / 40% right instead of
   equal thirds.  Prevents objects that are clearly off-centre from
   being reported as "ahead".

2. _compose_message always names the direction, even for critical urgency.
   Old: "Person very close ahead. Turn left or right."  ← position lost
   New: "Person very close on your left. Move right."   ← always clear

3. analyse_by_area uses tiered area thresholds for urgency:
   - area > 80,000 px  → critical   (object filling ~25% of 640×480 frame)
   - area > 25,000 px  → warning    (object ~8% of frame)
   - area > 10,000 px  → info       (object ~3% of frame, mention but no shout)
   Old threshold was 50,000 which silently dropped many real detections.

4. analyse_by_area picks the CLOSEST object (largest area) and the most
   URGENT one separately, then returns whichever is higher priority.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from detection import Detection


# ── MiDaS depth thresholds (normalised, lower = closer) ─────────────
ZONE_VERY_CLOSE = 0.30   # critical
ZONE_CLOSE      = 0.45   # warning
ZONE_MEDIUM     = 0.65   # info / heads-up

# ── Area thresholds for basic (no-depth) mode ───────────────────────
AREA_CRITICAL = 80_000   # ~25% of a 640×480 frame  → stop immediately
AREA_WARNING  = 25_000   # ~8%  of frame             → caution
AREA_INFO     = 10_000   # ~3%  of frame             → heads-up


@dataclass
class NavigationAdvice:
    object_name : str
    depth_value : float          # depth (0-1) or area (px) depending on mode
    h_position  : str            # "left" | "center" | "right"
    urgency     : str            # "critical" | "warning" | "info"
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

        best: Optional[NavigationAdvice] = None

        for det in detections:
            depth_val = self._sample_depth(depth_map, det.center_x, det.center_y)

            if depth_val > ZONE_MEDIUM:
                continue

            h_pos   = self._horizontal_zone(det.center_x)
            urgency = self._urgency_depth(depth_val)
            msg     = self._compose_message(det.class_name, h_pos, urgency)

            advice = NavigationAdvice(
                object_name = det.class_name,
                depth_value = depth_val,
                h_position  = h_pos,
                urgency     = urgency,
                message     = msg,
            )

            if best is None or self._priority(advice) < self._priority(best):
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
            elif (self._priority(advice) == self._priority(best)
                  and det.area > best.depth_value):
                # Same urgency — keep the larger (closer) object
                best = advice

        return best

    # ── zone detection ───────────────────────────────────────────────
    def _horizontal_zone(self, cx: int) -> str:
        """
        40 / 20 / 40 split so that objects clearly to the side are
        never misreported as "center".

        For a 640-px frame:
            left   : cx  <  256   (0–40%)
            center : cx  <= 384   (40–60%)
            right  : cx  >  384   (60–100%)
        """
        left_edge  = int(self.frame_width * 0.40)
        right_edge = int(self.frame_width * 0.60)

        if cx < left_edge:
            return "left"
        if cx > right_edge:
            return "right"
        return "center"

    # ── urgency ─────────────────────────────────────────────────────
    @staticmethod
    def _urgency_depth(depth_val: float) -> str:
        if depth_val <= ZONE_VERY_CLOSE:
            return "critical"
        if depth_val <= ZONE_CLOSE:
            return "warning"
        return "info"

    @staticmethod
    def _urgency_area(area: int) -> str:
        if area >= AREA_CRITICAL:
            return "critical"
        if area >= AREA_WARNING:
            return "warning"
        return "info"

    # ── message composition ──────────────────────────────────────────
    @staticmethod
    def _compose_message(name: str, position: str, urgency: str) -> str:
        """
        Always produces a message that contains BOTH where the object
        is AND what direction the user should move.

        Examples
        --------
            critical + left   → "Person very close on your left!  Move right."
            warning  + right  → "Person on your right.  Move left."
            info     + center → "Person ahead.  Slow down."
        """
        # --- Direction the user should move ---
        if position == "left":
            direction = "Move right."
        elif position == "right":
            direction = "Move left."
        else:
            direction = "Slow down or turn."

        # --- Where the object is ---
        if position == "center":
            location = "ahead"
        else:
            location = f"on your {position}"

        # --- Urgency prefix ---
        n = name.capitalize()
        if urgency == "critical":
            prefix = f"Warning! {n} very close {location}!"
        elif urgency == "warning":
            prefix = f"{n} {location}."
        else:
            prefix = f"{n} nearby {location}."

        return f"{prefix}  {direction}"

    # ── priority (lower = more urgent) ──────────────────────────────
    @staticmethod
    def _priority(advice: NavigationAdvice) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(advice.urgency, 3)

    # ── depth sampler ────────────────────────────────────────────────
    @staticmethod
    def _sample_depth(depth_map, cx: int, cy: int, radius: int = 10) -> float:
        import numpy as np
        try:
            h, w = depth_map.shape
            y0 = max(0, cy - radius);  y1 = min(h, cy + radius)
            x0 = max(0, cx - radius);  x1 = min(w, cx + radius)
            region = depth_map[y0:y1, x0:x1]
            if region.size > 0:
                return float(np.mean(region))
        except Exception:
            pass
        return 1.0