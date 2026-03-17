"""
obstacle_detection_upgraded.py — Full AI Vision Assist pipeline.

Pipeline
--------
Camera → YOLOv8x detection → MiDaS depth estimation →
depth-aware navigation analysis → priority voice alerts

Features
--------
  • GPU acceleration via CUDA (falls back to CPU automatically)
  • MiDaS DPT_Hybrid depth estimation (runs every N frames)
  • YOLOv8x for higher-accuracy object detection
  • Priority voice queue (critical alerts pre-empt lower-priority ones)
  • Depth heat-map overlay for visual debugging
  • Per-object depth readout on bounding boxes

Controls
--------
  Q  — quit
  D  — toggle depth heat-map overlay
  H  — toggle on-screen help
"""

import sys
import os
import time

import cv2
import numpy as np

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from detection  import ObjectDetector
from depth      import DepthEstimator
from navigation import Navigator, ZONE_VERY_CLOSE, ZONE_CLOSE
from voice      import VoiceEngine, PRIORITY_CRITICAL, PRIORITY_WARNING, PRIORITY_INFO


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
MODEL_PATH    = os.path.join("models", "yolov8x.pt")  # large model — accurate
CONFIDENCE    = 0.60
ALERT_DELAY   = 1.2      # seconds between successive voice alerts
FRAME_SKIP    = 3         # run depth every N frames
FRAME_WIDTH   = 640
FRAME_HEIGHT  = 480
SHOW_WINDOW   = True


def draw_depth_overlay(frame, depth_map):
    """Blend a colour-mapped depth heat-map onto the frame."""
    if depth_map is None:
        return frame
    coloured = cv2.applyColorMap(
        (depth_map * 255).astype(np.uint8), cv2.COLORMAP_INFERNO
    )
    return cv2.addWeighted(frame, 0.6, coloured, 0.4, 0)


def draw_detections(frame, detections, depth_map):
    """Draw bounding boxes annotated with class, confidence and depth."""
    for det in detections:
        # Box colour based on depth
        depth_val = 1.0
        if depth_map is not None:
            from navigation import Navigator as _Nav
            depth_val = _Nav._sample_depth(depth_map, det.center_x, det.center_y)

        if   depth_val <= ZONE_VERY_CLOSE:  colour = (0,   0, 255)   # red   — very close
        elif depth_val <= ZONE_CLOSE:       colour = (0, 165, 255)   # orange — close
        else:                               colour = (0, 255,   0)   # green  — far

        cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), colour, 2)

        label = f"{det.class_name}  {det.confidence:.0%}  d={depth_val:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)
        cv2.rectangle(
            frame,
            (det.x1, det.y1 - th - 10),
            (det.x1 + tw + 4, det.y1),
            colour, -1
        )
        cv2.putText(
            frame, label,
            (det.x1 + 2, det.y1 - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1
        )

    return frame


def draw_hud(frame, advice, depth_available: bool, show_help: bool):
    """Draw heads-up display: alert banner + status indicators."""
    h, w = frame.shape[:2]

    # Status bar
    depth_status = "Depth: ON " if depth_available else "Depth: OFF"
    cv2.putText(
        frame, depth_status, (w - 140, 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
        (0, 200, 0) if depth_available else (0, 100, 200), 1
    )

    # Zone dividers
    for x in [w // 3, 2 * w // 3]:
        cv2.line(frame, (x, 0), (x, h), (200, 200, 200), 1)
    for label, x in [("LEFT", 10), ("CENTER", w // 3 + 10), ("RIGHT", 2 * w // 3 + 10)]:
        cv2.putText(frame, label, (x, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    # Alert banner
    if advice:
        banner_colour = (0, 0, 200) if advice.urgency == "critical" else (0, 120, 200)
        cv2.rectangle(frame, (0, h - 45), (w, h), banner_colour, -1)
        cv2.putText(
            frame, advice.message, (10, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2
        )

    # Help overlay
    if show_help:
        lines = ["Q — quit", "D — toggle depth overlay", "H — toggle help"]
        for i, line in enumerate(lines):
            cv2.putText(
                frame, line, (10, 40 + i * 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1
            )

    return frame


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    # ── Voice ───────────────────────────────
    voice = VoiceEngine(rate=185)
    voice.start()

    # ── Camera ──────────────────────────────
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        voice.stop()
        return

    # ── Models ──────────────────────────────
    detector  = ObjectDetector(model_path=MODEL_PATH, confidence=CONFIDENCE)
    depth_est = DepthEstimator(frame_skip=FRAME_SKIP)
    navigator = Navigator(frame_width=FRAME_WIDTH, frame_height=FRAME_HEIGHT)

    last_alert_time = 0.0
    show_depth      = False
    show_help       = True

    print("\n[INFO] Upgraded Vision Assist running.  Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame capture failed — retrying …")
            time.sleep(0.05)
            continue

        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        # ── Depth ───────────────────────────
        depth_map = depth_est.update(frame)

        # ── Detection ───────────────────────
        detections = detector.detect(frame)

        # ── Navigation ──────────────────────
        advice = navigator.analyse(detections, depth_map)

        # ── Voice alert ─────────────────────
        current_time = time.time()
        if advice and (current_time - last_alert_time) > ALERT_DELAY:
            priority_map = {
                "critical": PRIORITY_CRITICAL,
                "warning" : PRIORITY_WARNING,
                "info"    : PRIORITY_INFO,
            }
            priority = priority_map.get(advice.urgency, PRIORITY_WARNING)
            print(
                f"[ALERT] depth={advice.depth_value:.3f} | "
                f"urgency={advice.urgency} | {advice.message}"
            )
            voice.speak(advice.message, priority=priority)
            last_alert_time = current_time

        # ── Render ──────────────────────────
        if SHOW_WINDOW:
            display = frame.copy()

            if show_depth and depth_map is not None:
                display = draw_depth_overlay(display, depth_map)

            display = draw_detections(display, detections, depth_map)
            display = draw_hud(display, advice, depth_map is not None, show_help)

            cv2.imshow("Vision Assist — Upgraded", display)

            key = cv2.waitKey(1) & 0xFF
            if   key == ord("q"):
                break
            elif key == ord("d"):
                show_depth = not show_depth
                print(f"[INFO] Depth overlay: {'ON' if show_depth else 'OFF'}")
            elif key == ord("h"):
                show_help = not show_help

    # ── Cleanup ─────────────────────────────
    cap.release()
    cv2.destroyAllWindows()
    voice.stop()
    print("[INFO] Stopped.")


if __name__ == "__main__":
    main()
