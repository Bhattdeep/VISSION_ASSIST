"""
ranging.py - Approximate monocular distance estimation in centimeters.

This module intentionally does NOT claim true metric depth. Without a
calibrated stereo setup or hardware distance sensor, the best we can do
from a single RGB camera is a class-size-based estimate.
"""

from __future__ import annotations

import time
from statistics import median
from math import tan, radians
from typing import Optional


# Approximate real-world object dimensions in centimeters for common COCO classes.
OBJECT_SIZE_PRIORS_CM = {
    "person": {"height": 170, "width": 45, "mode": "height", "scale": 0.96},
    "bicycle": {"height": 110, "width": 175, "mode": "width", "scale": 1.00},
    "car": {"height": 150, "width": 180, "mode": "width", "scale": 1.00},
    "motorcycle": {"height": 120, "width": 210, "mode": "width", "scale": 1.02},
    "bus": {"height": 320, "width": 250, "mode": "width", "scale": 1.03},
    "truck": {"height": 320, "width": 250, "mode": "width", "scale": 1.03},
    "train": {"height": 350, "width": 300, "mode": "width", "scale": 1.05},
    "chair": {"height": 90, "width": 45, "mode": "height", "scale": 1.00},
    "couch": {"height": 90, "width": 200, "mode": "width", "scale": 1.02},
    "sofa": {"height": 90, "width": 200, "mode": "width", "scale": 1.02},
    "bed": {"height": 60, "width": 190, "mode": "width", "scale": 1.00},
    "dining table": {"height": 75, "width": 120, "mode": "width", "scale": 1.02},
    "bench": {"height": 85, "width": 140, "mode": "width", "scale": 1.00},
    "tv": {"height": 60, "width": 100, "mode": "width", "scale": 0.98},
    "tvmonitor": {"height": 60, "width": 100, "mode": "width", "scale": 0.98},
    "laptop": {"height": 24, "width": 35, "mode": "width", "scale": 0.95},
    "cell phone": {"height": 15, "width": 7, "mode": "height", "scale": 0.95},
    "book": {"height": 24, "width": 17, "mode": "height", "scale": 0.96},
    "backpack": {"height": 45, "width": 30, "mode": "height", "scale": 1.00},
    "handbag": {"height": 28, "width": 32, "mode": "width", "scale": 1.00},
    "suitcase": {"height": 65, "width": 42, "mode": "height", "scale": 0.98},
    "bottle": {"height": 25, "width": 7, "mode": "height", "scale": 0.98},
    "cup": {"height": 10, "width": 8, "mode": "height", "scale": 0.98},
    "dog": {"height": 60, "width": 85, "mode": "width", "scale": 1.00},
    "cat": {"height": 25, "width": 45, "mode": "width", "scale": 1.00},
    "potted plant": {"height": 55, "width": 35, "mode": "height", "scale": 1.00},
    "stop sign": {"height": 75, "width": 75, "mode": "median", "scale": 1.00},
    "fire hydrant": {"height": 75, "width": 25, "mode": "height", "scale": 0.98},
    "traffic light": {"height": 80, "width": 30, "mode": "height", "scale": 1.00},
    "refrigerator": {"height": 180, "width": 70, "mode": "height", "scale": 0.98},
    "microwave": {"height": 30, "width": 50, "mode": "width", "scale": 1.00},
    "oven": {"height": 60, "width": 60, "mode": "median", "scale": 1.00},
    "sink": {"height": 25, "width": 60, "mode": "width", "scale": 1.00},
    "toilet": {"height": 75, "width": 38, "mode": "height", "scale": 1.00},
    "door": {"height": 200, "width": 85, "mode": "height", "scale": 1.00},
}


class DistanceEstimator:
    """
    Estimate object distance from a monocular camera using class priors and
    a simple pinhole-camera model.
    """

    def __init__(
        self,
        frame_width: int = 640,
        frame_height: int = 480,
        horizontal_fov_deg: float = 62.0,
        vertical_fov_deg: float = 49.0,
    ):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.horizontal_fov_deg = horizontal_fov_deg
        self.vertical_fov_deg = vertical_fov_deg

        self.focal_x_px = frame_width / (2.0 * tan(radians(horizontal_fov_deg) / 2.0))
        self.focal_y_px = frame_height / (2.0 * tan(radians(vertical_fov_deg) / 2.0))

    def estimate_detection_cm(self, detection) -> Optional[float]:
        name = getattr(detection, "class_name", "").lower().strip()
        priors = OBJECT_SIZE_PRIORS_CM.get(name)
        if not priors:
            return None

        width_px = max(1, int(getattr(detection, "bbox_width", 0) or 0))
        height_px = max(1, int(getattr(detection, "bbox_height", 0) or 0))
        height_est = None
        width_est = None
        if priors.get("height") and height_px > 0:
            height_est = (priors["height"] * self.focal_y_px) / height_px

        if priors.get("width") and width_px > 0:
            width_est = (priors["width"] * self.focal_x_px) / width_px

        mode = priors.get("mode", "median")
        if mode == "height" and height_est is not None:
            base = height_est if width_est is None else (height_est * 0.78 + width_est * 0.22)
        elif mode == "width" and width_est is not None:
            base = width_est if height_est is None else (width_est * 0.78 + height_est * 0.22)
        else:
            estimates = [v for v in (height_est, width_est) if v is not None]
            if not estimates:
                return None
            base = float(median(estimates))

        if base is None:
            return None

        cm = float(base) * float(priors.get("scale", 1.0))

        # Keep outputs within a sane operating range for the app.
        return max(15.0, min(2500.0, cm))

    @staticmethod
    def rounded_cm(distance_cm: Optional[float], step: int = 10) -> Optional[int]:
        if distance_cm is None:
            return None
        step = max(1, int(step))
        return int(step * round(float(distance_cm) / step))

    @staticmethod
    def apply_depth_hint(
        distance_cm: Optional[float],
        depth_value: Optional[float],
        p_far: Optional[float],
        p_mid: Optional[float],
        p_near: Optional[float],
    ) -> Optional[float]:
        if distance_cm is None or depth_value is None:
            return distance_cm

        factor = 1.0
        if p_near is not None and depth_value >= p_near:
            factor = 0.85
        elif p_mid is not None and depth_value >= p_mid:
            factor = 0.94
        elif p_far is not None and depth_value < p_far:
            factor = 1.08

        return max(15.0, min(2500.0, distance_cm * factor))

    def track_key(self, detection, position: str = "center") -> str:
        cx = int(getattr(detection, "center_x", 0) / max(1, self.frame_width // 5))
        cy = int(getattr(detection, "center_y", 0) / max(1, self.frame_height // 4))
        hbin = int(getattr(detection, "bbox_height", 0) / 60)
        return f"{getattr(detection, 'class_name', 'obj').lower()}:{position}:{cx}:{cy}:{hbin}"


class DistanceSmoother:
    def __init__(self, alpha: float = 0.38, ttl_sec: float = 1.8):
        self.alpha = alpha
        self.ttl_sec = ttl_sec
        self._state = {}

    def update(self, key: str, raw_cm: Optional[float], now: Optional[float] = None) -> Optional[float]:
        if raw_cm is None:
            return None

        now = now or time.time()
        self._state = {
            k: v for k, v in self._state.items()
            if (now - v["time"]) <= self.ttl_sec
        }

        prev = self._state.get(key)
        if prev is None:
            self._state[key] = {"distance": float(raw_cm), "time": now}
            return float(raw_cm)

        prev_cm = float(prev["distance"])
        delta = float(raw_cm) - prev_cm
        max_step = max(18.0, prev_cm * 0.22)
        if delta > max_step:
            bounded = prev_cm + max_step
        elif delta < -max_step:
            bounded = prev_cm - max_step
        else:
            bounded = float(raw_cm)

        smooth = (self.alpha * bounded) + ((1.0 - self.alpha) * prev_cm)
        self._state[key] = {"distance": smooth, "time": now}
        return smooth
