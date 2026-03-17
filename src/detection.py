"""
detection.py — YOLOv8 object detection wrapper.

Heavy imports (torch, ultralytics) are deferred until ObjectDetector
is actually instantiated, so importing this module at the top level
of gui.py does NOT trigger DLL loading on Windows.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Any


# ------------------------------------------------------------------ #
# Pure-Python dataclass — zero torch dependency                       #
# ------------------------------------------------------------------ #

@dataclass
class Detection:
    """One detected object in a frame."""
    class_name : str
    confidence : float
    x1         : int
    y1         : int
    x2         : int
    y2         : int
    center_x   : int = field(init=False)
    center_y   : int = field(init=False)
    area       : int = field(init=False)

    def __post_init__(self):
        self.center_x = (self.x1 + self.x2) // 2
        self.center_y = (self.y1 + self.y2) // 2
        self.area     = (self.x2 - self.x1) * (self.y2 - self.y1)


# ------------------------------------------------------------------ #
# Detector — torch / ultralytics imported lazily inside __init__      #
# ------------------------------------------------------------------ #

class ObjectDetector:
    """
    Wraps a YOLOv8 model for frame-level object detection.

    torch and ultralytics are imported inside __init__ so that simply
    importing this module (e.g. in gui.py) does not load any DLLs.

    Parameters
    ----------
    model_path  : Path to the .pt weights file.
    device      : torch.device or None (auto-detected inside __init__).
    confidence  : Minimum confidence threshold (0-1).
    """

    def __init__(
        self,
        model_path : str   = "models/yolov8x.pt",
        device     : Any   = None,
        confidence : float = 0.60,
    ):
        # ── ALL heavy imports happen here, not at module level ─────
        import torch
        from ultralytics import YOLO

        self.confidence = confidence
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        print(f"[Detection] Loading YOLO from '{model_path}' on {self.device} ...")
        self._model = YOLO(model_path)
        self._model.to(self.device)
        print("[Detection] YOLO ready.")

    def detect(self, frame) -> List[Detection]:
        """
        Run inference on a BGR numpy frame.
        Returns Detection objects filtered by confidence threshold.
        """
        results = self._model(frame, verbose=False)
        out: List[Detection] = []

        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < self.confidence:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_id   = int(box.cls[0])
                class_name = self._model.names[class_id]
                out.append(Detection(
                    class_name=class_name, confidence=conf,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))

        return out

    @property
    def model(self):
        return self._model
