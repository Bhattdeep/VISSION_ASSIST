"""
depth.py — MiDaS depth estimation wrapper.

torch is imported lazily inside __init__ so that importing this
module at the top of gui.py does not trigger DLL loading.
"""

from __future__ import annotations
from typing import Optional, Any

import cv2
import numpy as np


class DepthEstimator:
    """
    Wraps Intel MiDaS DPT_Hybrid for monocular depth estimation.

    Depth convention: normalised [0, 1] via cv2.NORM_MINMAX.
    Lower value  = object is CLOSER (consistent with original codebase).

    Parameters
    ----------
    device     : torch.device or None (auto-detected).
    frame_skip : Run depth inference every N frames (default 3).
    """

    def __init__(
        self,
        device     : Any = None,
        frame_skip : int = 3,
    ):
        # ── ALL torch imports happen here, not at module level ─────
        import torch

        self.frame_skip = frame_skip
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        print(f"[Depth] Loading MiDaS DPT_Hybrid on {self.device} ...")
        self._model = torch.hub.load(
            "intel-isl/MiDaS", "DPT_Hybrid", verbose=False
        )
        self._model.to(self.device)
        self._model.eval()

        _transforms       = torch.hub.load("intel-isl/MiDaS", "transforms", verbose=False)
        self._transform   = _transforms.dpt_transform
        self._torch       = torch          # keep reference for inference

        self._depth_map   : Optional[np.ndarray] = None
        self._frame_count : int = 0
        print("[Depth] MiDaS ready.")

    # ------------------------------------------------------------------ #

    def update(self, frame) -> Optional[np.ndarray]:
        """
        Feed a BGR frame. Inference runs every frame_skip frames;
        cached depth map returned on other frames.
        """
        self._frame_count += 1
        if self._frame_count % self.frame_skip != 0:
            return self._depth_map

        height, width = frame.shape[:2]
        torch = self._torch

        try:
            img         = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            batch       = self._transform(img).to(self.device)

            with torch.no_grad():
                pred = self._model(batch)
                pred = torch.nn.functional.interpolate(
                    pred.unsqueeze(1),
                    size=(height, width),
                    mode="bicubic",
                    align_corners=False,
                ).squeeze()

            raw = pred.detach().cpu().float().numpy()
            if raw is not None and raw.size > 0:
                self._depth_map = cv2.normalize(
                    raw, None, 0, 1, cv2.NORM_MINMAX
                ).astype(np.float32)

        except Exception as exc:
            print(f"[Depth] Inference error: {exc}")

        return self._depth_map

    def sample(self, depth_map: np.ndarray, cx: int, cy: int, radius: int = 8) -> float:
        """Mean depth in a small patch around (cx, cy). Returns 1.0 on error."""
        try:
            h, w = depth_map.shape
            region = depth_map[
                max(0, cy - radius): min(h, cy + radius),
                max(0, cx - radius): min(w, cx + radius),
            ]
            if region.size > 0:
                return float(np.mean(region))
        except Exception:
            pass
        return 1.0

    @property
    def current_map(self) -> Optional[np.ndarray]:
        return self._depth_map
