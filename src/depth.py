"""
depth.py — MiDaS depth estimation wrapper.

Fixes in this version
----------------------
1. Falls back through model variants: DPT_Hybrid → DPT_Large → MiDaS_small
   so the system works even if the preferred model fails to load.

2. Per-frame NORM_MINMAX is kept (correct for relative depth within a scene),
   but the Navigator now uses PERCENTILE thresholds instead of fixed values
   so "is this object close?" is answered relative to the scene, not globally.

3. depth_map is always the latest successfully computed map.  The _ever_ready
   flag lets the server report "depth active" correctly even on skipped frames.

Depth convention
----------------
MiDaS outputs DISPARITY (inverse depth).  After cv2.normalize → [0, 1]:
    value near 1.0  = object is VERY CLOSE
    value near 0.0  = object is VERY FAR
"""

from __future__ import annotations
from typing import Optional, Any

import cv2
import numpy as np


class DepthEstimator:

    def __init__(self, device: Any = None, frame_skip: int = 3):
        import torch

        self.frame_skip  = frame_skip
        self.device      = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self._model      = None
        self._transform  = None
        self._torch      = torch
        self._depth_map  : Optional[np.ndarray] = None
        self._frame_count = 0
        self.ever_ready  = False   # True once first map is computed

        self._load_model()

    # ── model loading with fallback chain ───────────────────────────
    def _load_model(self):
        import torch

        # Try models in order of quality; fall back gracefully
        candidates = [
            ("intel-isl/MiDaS", "DPT_Hybrid",  "dpt_transform"),
            ("intel-isl/MiDaS", "DPT_Large",   "dpt_transform"),
            ("intel-isl/MiDaS", "MiDaS_small", "small_transform"),
        ]

        for repo, name, tfm_name in candidates:
            try:
                print(f"[Depth] Trying {name} …")
                self._model = torch.hub.load(repo, name, verbose=False)
                self._model.to(self.device)
                self._model.eval()

                transforms = torch.hub.load(repo, "transforms", verbose=False)
                self._transform = getattr(transforms, tfm_name)

                print(f"[Depth] Loaded {name} on {self.device}")
                return
            except Exception as exc:
                print(f"[Depth] {name} failed: {exc}")

        raise RuntimeError("[Depth] All MiDaS model variants failed to load.")

    # ── inference ───────────────────────────────────────────────────
    def update(self, frame) -> Optional[np.ndarray]:
        """
        Run inference every frame_skip frames; return cached map otherwise.
        Never returns None after the first successful inference.
        """
        self._frame_count += 1
        if self._frame_count % self.frame_skip != 0:
            return self._depth_map          # cached — never None after first run

        h, w   = frame.shape[:2]
        torch  = self._torch

        try:
            img   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            batch = self._transform(img).to(self.device)

            with torch.no_grad():
                pred = self._model(batch)
                pred = torch.nn.functional.interpolate(
                    pred.unsqueeze(1),
                    size=(h, w),
                    mode="bicubic",
                    align_corners=False,
                ).squeeze()

            raw = pred.detach().cpu().float().numpy()

            if raw.size > 0:
                # Normalise to [0, 1] — higher = closer (disparity convention)
                self._depth_map = cv2.normalize(
                    raw, None, 0, 1, cv2.NORM_MINMAX
                ).astype(np.float32)
                self.ever_ready = True

        except Exception as exc:
            print(f"[Depth] Inference error: {exc}")

        return self._depth_map

    # ── utilities ───────────────────────────────────────────────────
    @staticmethod
    def sample(depth_map: np.ndarray, cx: int, cy: int, radius: int = 12) -> float:
        """Mean disparity in a patch — higher = closer. Returns 0.0 on error."""
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

    @staticmethod
    def scene_percentiles(depth_map: np.ndarray):
        """
        Return (p25, p50, p75) of the depth map for percentile-based thresholds.
        Using scene percentiles makes thresholds robust even when the whole
        scene is at a similar depth (e.g. a blank wall close-up).
        """
        try:
            flat = depth_map.ravel()
            return (
                float(np.percentile(flat, 25)),
                float(np.percentile(flat, 50)),
                float(np.percentile(flat, 75)),
            )
        except Exception:
            return (0.25, 0.50, 0.75)

    @property
    def current_map(self) -> Optional[np.ndarray]:
        return self._depth_map