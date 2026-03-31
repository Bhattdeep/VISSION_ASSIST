"""
obstacle_detection.py — Basic obstacle detection (no depth estimation).

Pipeline
--------
Camera → YOLOv8 detection → bounding-box area proxy → voice alert

This script is lightweight and runs comfortably on CPU.  Use
obstacle_detection_upgraded.py for depth-aware, GPU-accelerated mode.

Controls
--------
  Q  — quit
"""

import sys
import os
import time
import cv2

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from detection  import ObjectDetector
from navigation import Navigator
from voice      import VoiceEngine, PRIORITY_WARNING, PRIORITY_CRITICAL
from alerts     import AlertSuppressor


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
MODEL_PATH   = os.path.join("models", "yolov8n.pt")   # nano model — fast
CONFIDENCE   = 0.50
MIN_AREA     = 50_000   # px²  — objects smaller than this are ignored
ALERT_DELAY  = 3.0      # seconds between successive voice alerts
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
SHOW_WINDOW  = True


def main():
    # ── Voice ───────────────────────────────
    voice = VoiceEngine(rate=150)
    voice.start()

    # ── Camera ──────────────────────────────
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        voice.stop()
        return

    # ── Model & Navigator ───────────────────
    detector  = ObjectDetector(model_path=MODEL_PATH, confidence=CONFIDENCE)
    navigator = Navigator(frame_width=FRAME_WIDTH, frame_height=FRAME_HEIGHT)
    alert_guard = AlertSuppressor(min_repeat_gap_sec=max(6.0, ALERT_DELAY * 2.0))

    last_alert_time = 0.0

    print("\n[INFO] Basic obstacle detection running.  Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame capture failed — retrying …")
            time.sleep(0.05)
            continue

        # Resize to configured dimensions
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        # ── Detection ───────────────────────
        detections = detector.detect(frame)

        # ── Navigation ──────────────────────
        advice = navigator.analyse_by_area(detections, min_area=MIN_AREA)

        # Draw bounding boxes
        for det in detections:
            est_cm = getattr(det, "estimated_distance_cm", None)
            colour = (0, 0, 255) if est_cm is not None and est_cm <= 120 else (
                (0, 165, 255) if est_cm is not None and est_cm <= 220 else (0, 255, 0)
            )
            cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), colour, 2)
            label = f"{det.class_name} {det.confidence:.0%}"
            if est_cm is not None:
                label += f" ~{est_cm:.0f}cm"
            cv2.putText(
                frame, label, (det.x1, det.y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 1
            )

        current_time = time.time()
        if (
            advice
            and (current_time - last_alert_time) > ALERT_DELAY
            and alert_guard.should_emit(
                advice.fingerprint,
                advice.urgency,
                advice.distance_cm,
                current_time,
            )
        ):
            priority = (
                PRIORITY_CRITICAL if advice.urgency == "critical"
                else PRIORITY_WARNING
            )
            print(f"[ALERT] {advice.message}")
            voice.speak(advice.message, priority=priority)
            last_alert_time = current_time

            # Overlay the alert on frame
            cv2.putText(
                frame, advice.message, (10, FRAME_HEIGHT - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2
            )

        # ── Display ─────────────────────────
        if SHOW_WINDOW:
            cv2.imshow("Vision Assist — Basic", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    # ── Cleanup ─────────────────────────────
    cap.release()
    cv2.destroyAllWindows()
    voice.stop()
    print("[INFO] Stopped.")


if __name__ == "__main__":
    main()
