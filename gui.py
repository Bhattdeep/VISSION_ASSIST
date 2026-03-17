# ═══════════════════════════════════════════════════════════════════
# CRITICAL WINDOWS FIX — torch MUST be imported BEFORE PyQt5
# PyQt5 calls SetDefaultDllDirectories() which wipes the DLL search
# path. Import torch first so c10.dll is mapped before Qt touches it.
# ═══════════════════════════════════════════════════════════════════
import sys, os

print("Pre-loading torch (must happen before PyQt5) ...", end=" ", flush=True)
try:
    import torch
    import torchvision
    print(f"OK  ({torch.__version__})")
    _TORCH_OK  = True
    _TORCH_ERR = ""
except Exception as _torch_err:
    print(f"FAILED — {_torch_err}")
    _TORCH_OK  = False
    _TORCH_ERR = str(_torch_err)

# ── safe to import PyQt5 now ─────────────────────────────────────────
import time, threading
from datetime import datetime
from collections import deque

import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSlider, QComboBox,
    QCheckBox, QTextEdit, QProgressBar, QGroupBox, QSplitter,
    QMessageBox, QTabWidget, QLineEdit, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui  import QImage, QPixmap, QFont, QColor, QPalette

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

ZONE_VERY_CLOSE = 0.30
ZONE_CLOSE      = 0.45

# ═══════════════════════════════════════════════════════════════════
# COLOUR PALETTE
# ═══════════════════════════════════════════════════════════════════
P = {
    "bg_dark"  : "#0A0E1A",
    "bg_panel" : "#111827",
    "bg_card"  : "#1A2235",
    "border"   : "#1F2D45",
    "accent"   : "#00D4FF",
    "accent2"  : "#00FF9D",
    "warn"     : "#FF8C00",
    "danger"   : "#FF3B3B",
    "hi"       : "#E8F4FD",
    "mid"      : "#7A9BB5",
    "lo"       : "#3D5A73",
    "purple"   : "#A78BFA",
}

def _sample_depth(depth_map, cx, cy, r=8):
    try:
        h, w = depth_map.shape
        region = depth_map[max(0,cy-r):min(h,cy+r), max(0,cx-r):min(w,cx+r)]
        if region.size > 0:
            return float(np.mean(region))
    except Exception:
        pass
    return 1.0


# ═══════════════════════════════════════════════════════════════════
# ASSISTANT WORKER  — runs Claude API call off the UI thread
# ═══════════════════════════════════════════════════════════════════
class AssistantWorker(QThread):
    response_ready = pyqtSignal(str)   # answer text
    error_occurred = pyqtSignal(str)   # error text

    def __init__(self, api_key, question, detections, distance_cm, depth_ready, history):
        super().__init__()
        self.api_key      = api_key
        self.question     = question
        self.detections   = detections
        self.distance_cm  = distance_cm
        self.depth_ready  = depth_ready
        self.history      = list(history)   # snapshot

    def run(self):
        try:
            import anthropic
        except ImportError:
            self.error_occurred.emit(
                "anthropic package not installed.\nRun:  pip install anthropic"
            )
            return

        # Build scene description
        parts = []
        if self.distance_cm is not None:
            ft = self.distance_cm / 30.48
            parts.append(f"Ultrasonic sensor: nearest object is {self.distance_cm:.0f} cm ({ft:.1f} ft) away.")
        else:
            parts.append("Ultrasonic sensor: not connected or no reading.")

        if self.detections:
            names = [f"{d.class_name} ({d.confidence:.0%})" for d in self.detections[:5]]
            parts.append(f"Camera detections: {', '.join(names)}.")
        else:
            parts.append("Camera detections: no objects detected.")

        parts.append(f"Depth estimation: {'active' if self.depth_ready else 'not active'}.")
        scene = " ".join(parts)

        system = (
            "You are a helpful AI assistant embedded in a wearable vision system for "
            "visually impaired users. Answer questions about the user's environment using "
            "the scene context provided, or answer general questions. Keep responses "
            "brief (1-3 sentences), plain text, no markdown. Prioritise safety.\n\n"
            f"=== CURRENT SCENE ===\n{scene}\n=== END SCENE ==="
        )

        messages = self.history[-10:] + [{"role": "user", "content": self.question}]

        try:
            client   = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model      = "claude-sonnet-4-20250514",
                max_tokens = 300,
                system     = system,
                messages   = messages,
            )
            self.response_ready.emit(response.content[0].text.strip())
        except Exception as exc:
            self.error_occurred.emit(str(exc))


# ═══════════════════════════════════════════════════════════════════
# PIPELINE WORKER THREAD
# ═══════════════════════════════════════════════════════════════════
class PipelineWorker(QThread):
    frame_ready      = pyqtSignal(np.ndarray, list, object)
    stats_updated    = pyqtSignal(dict)
    alert_triggered  = pyqtSignal(str, str)
    distance_updated = pyqtSignal(float)   # ultrasonic cm
    startup_error    = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config         = config
        self._running       = False
        self._show_depth    = False
        self.voice          = None
        self._last_alert    = 0.0   # instance var so UI can reset it

    def stop(self):              self._running    = False
    def toggle_depth(self):      self._show_depth = not self._show_depth
    def reset_alert_timer(self): self._last_alert = 0.0

    def run(self):
        import torch
        if not _TORCH_OK:
            self.startup_error.emit(
                f"PyTorch failed:\n\n{_TORCH_ERR}\n\n"
                "pip uninstall torch torchvision -y\n"
                "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
            )
            return

        try:
            from detection  import ObjectDetector
            from navigation import Navigator
            from voice      import VoiceEngine, PRIORITY_CRITICAL, PRIORITY_WARNING, PRIORITY_INFO
        except Exception as exc:
            self.startup_error.emit(f"Could not load src modules:\n\n{exc}")
            return

        self._running = True
        device        = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        device_label  = "GPU (CUDA)" if device.type == "cuda" else "CPU"

        self.voice = VoiceEngine(rate=185)
        self.voice.start()

        mode       = self.config.get("mode", "basic")
        model_name = "yolov8x.pt" if mode == "upgraded" else "yolov8n.pt"
        base_dir   = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(base_dir, "models", model_name)

        try:
            detector = ObjectDetector(model_path=model_path,
                                      confidence=self.config.get("confidence", 0.60),
                                      device=device)
        except Exception as exc:
            self.startup_error.emit(
                f"YOLO model load failed:\n  {model_path}\n\n{exc}\n\n"
                "Download:  python -c \"from ultralytics import YOLO; YOLO('yolov8n.pt')\"\n"
                "Then move yolov8n.pt to models/"
            )
            self.voice.stop()
            return

        navigator  = Navigator(frame_width=self.config.get("frame_width", 640),
                               frame_height=self.config.get("frame_height", 480))
        depth_est  = None
        depth_ready = False
        if mode == "upgraded":
            try:
                from depth import DepthEstimator
                depth_est   = DepthEstimator(device=device, frame_skip=3)
                depth_ready = True
            except Exception as exc:
                print(f"[GUI] Depth unavailable: {exc}")

        # ── ultrasonic sensor ────────────────────────────────────────
        sensor = None
        if self.config.get("ultrasonic_enabled") and self.config.get("ultrasonic_port"):
            try:
                from ultrasonic import UltrasonicSensor
                sensor = UltrasonicSensor(
                    port     = self.config["ultrasonic_port"],
                    baudrate = self.config.get("ultrasonic_baud", 9600),
                )
                sensor.start()
            except Exception as exc:
                print(f"[GUI] Ultrasonic unavailable: {exc}")

        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.config["frame_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config["frame_height"])
        if not cap.isOpened():
            self.startup_error.emit("Cannot open camera (index 0).")
            self.voice.stop()
            return

        self._last_alert = 0.0
        fps_buf    = deque(maxlen=20)
        t_prev     = time.time()

        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            t_now = time.time()
            fps_buf.append(1.0 / max(t_now - t_prev, 1e-6))
            t_prev = t_now

            frame     = cv2.resize(frame, (self.config["frame_width"],
                                           self.config["frame_height"]))
            depth_map = depth_est.update(frame) if depth_est else None

            detector.confidence = self.config.get("confidence", 0.60)
            detections = detector.detect(frame)

            advice = (navigator.analyse(detections, depth_map)
                      if depth_map is not None
                      else navigator.analyse_by_area(
                          detections, min_area=self.config.get("min_area", 50_000)))

            # ultrasonic reading
            dist_cm = sensor.distance_cm if sensor else None
            if dist_cm is not None:
                self.distance_updated.emit(dist_cm)

                # fuse ultrasonic + YOLO: override urgency if very close
                if dist_cm < 50 and advice is None:
                    # ultrasonic detects something YOLO missed
                    from voice import PRIORITY_CRITICAL as PC
                    msg = f"Object {dist_cm:.0f} cm ahead. Stop immediately."
                    t_cur = time.time()
                    if (t_cur - self._last_alert) > self.config.get("alert_delay", 1.5):
                        if self.config.get("voice_enabled", True):
                            self.voice.speak(msg, priority=PC)
                        self.alert_triggered.emit(msg, "critical")
                        self._last_alert = t_cur

            t_cur = time.time()
            if advice and (t_cur - self._last_alert) > self.config.get("alert_delay", 1.5):
                if self.config.get("voice_enabled", True):
                    pmap = {"critical": PRIORITY_CRITICAL,
                            "warning" : PRIORITY_WARNING,
                            "info"    : PRIORITY_INFO}
                    self.voice.speak(advice.message,
                                     priority=pmap.get(advice.urgency, PRIORITY_WARNING))
                self.alert_triggered.emit(advice.message, advice.urgency)
                self._last_alert = t_cur

            display = self._render(frame, detections, depth_map, dist_cm)
            self.frame_ready.emit(display, detections, advice)
            self.stats_updated.emit({
                "fps"         : sum(fps_buf) / len(fps_buf),
                "device"      : device_label,
                "depth_ready" : depth_ready and depth_map is not None,
                "mode"        : mode,
                "sensor_on"   : sensor is not None and sensor.is_connected,
            })

        cap.release()
        if sensor:
            sensor.stop()
        if self.voice:
            self.voice.stop()

    def _render(self, frame, detections, depth_map, dist_cm=None):
        disp = frame.copy()

        if self._show_depth and depth_map is not None:
            heat = cv2.applyColorMap(
                (depth_map * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
            disp = cv2.addWeighted(disp, 0.55, heat, 0.45, 0)

        for det in detections:
            dv = _sample_depth(depth_map, det.center_x, det.center_y) \
                 if depth_map is not None else 1.0
            colour = ((60,60,255) if dv <= ZONE_VERY_CLOSE
                      else (40,160,255) if dv <= ZONE_CLOSE
                      else (60,220,100))
            cv2.rectangle(disp, (det.x1,det.y1), (det.x2,det.y2), colour, 2)
            lbl = f"{det.class_name} {det.confidence:.0%}" + (
                f" d={dv:.2f}" if depth_map is not None else "")
            (tw,th),_ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            cv2.rectangle(disp, (det.x1, det.y1-th-8),
                          (det.x1+tw+6, det.y1), colour, -1)
            cv2.putText(disp, lbl, (det.x1+3, det.y1-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255,255,255), 1)

        h, w = disp.shape[:2]
        for x in [w//3, 2*w//3]:
            cv2.line(disp, (x,0), (x,h), (60,80,100), 1)

        # Ultrasonic distance overlay (bottom-left)
        if dist_cm is not None:
            col = ((0,60,255) if dist_cm < 50
                   else (0,140,255) if dist_cm < 150
                   else (60,220,100))
            cv2.rectangle(disp, (6, h-34), (220, h-6), (10,15,30), -1)
            cv2.putText(disp, f"SONAR: {dist_cm:.0f} cm  ({dist_cm/30.48:.1f} ft)",
                        (10, h-12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)

        return disp


# ═══════════════════════════════════════════════════════════════════
# WIDGET HELPERS
# ═══════════════════════════════════════════════════════════════════
def _lbl(text, size=11, bold=False, color=None):
    w = QLabel(text)
    w.setFont(QFont("Consolas", size, QFont.Bold if bold else QFont.Normal))
    if color:
        w.setStyleSheet(f"color:{color};background:transparent;")
    return w

def _card(title=""):
    g = QGroupBox(title)
    g.setStyleSheet(f"""
        QGroupBox{{background:{P['bg_card']};border:1px solid {P['border']};
                   border-radius:8px;margin-top:14px;padding:8px;
                   color:{P['accent']};font:bold 10px Consolas;}}
        QGroupBox::title{{subcontrol-origin:margin;left:12px;padding:0 4px;
                          color:{P['accent']};font:bold 10px Consolas;letter-spacing:1px;}}
    """)
    return g

class AlertBadge(QLabel):
    _C = {"critical":("#FF3B3B","#2A0A0A"),"warning":("#FF8C00","#2A1800"),
          "info":("#00D4FF","#001A2A"),"none":("#3D5A73","#0D1520")}
    _T = {"critical":"🔴  CRITICAL — STOP","warning":"🟠  WARNING — CAUTION",
          "info":"🔵  INFO — NEARBY","none":"●  NO ALERT"}
    def __init__(self):
        super().__init__("●  NO ALERT")
        self.setAlignment(Qt.AlignCenter); self.setFixedHeight(32); self.set_urgency("none")
    def set_urgency(self, u):
        fg,bg = self._C.get(u, self._C["none"])
        self.setText(self._T.get(u,"●  NO ALERT"))
        self.setStyleSheet(f"QLabel{{background:{bg};color:{fg};border:1px solid {fg};"
                           f"border-radius:14px;font:bold 11px Consolas;padding:0 12px;}}")

class DetectionRow(QWidget):
    def __init__(self, name, conf, depth):
        super().__init__(); self.setFixedHeight(40)
        self.setStyleSheet(f"QWidget{{background:{P['bg_panel']};border:1px solid {P['border']};border-radius:6px;}}")
        lo = QHBoxLayout(self); lo.setContentsMargins(8,2,8,2); lo.setSpacing(8)
        nl = QLabel(name[:12]); nl.setFont(QFont("Consolas",10,QFont.Bold))
        nl.setStyleSheet(f"color:{P['hi']};background:transparent;border:none;"); nl.setFixedWidth(88); lo.addWidget(nl)
        cl = QLabel(f"{conf:.0%}"); cl.setFont(QFont("Consolas",9))
        cl.setStyleSheet(f"color:{P['mid']};background:transparent;border:none;"); cl.setFixedWidth(34); lo.addWidget(cl)
        bar_col = P["danger"] if depth<=ZONE_VERY_CLOSE else P["warn"] if depth<=ZONE_CLOSE else P["accent2"]
        bar = QProgressBar(); bar.setRange(0,100); bar.setValue(max(0,min(100,int((1-depth)*100))))
        bar.setTextVisible(False); bar.setFixedHeight(8)
        bar.setStyleSheet(f"QProgressBar{{background:{P['bg_dark']};border:none;border-radius:4px;}}"
                          f"QProgressBar::chunk{{background:{bar_col};border-radius:4px;}}"); lo.addWidget(bar,1)
        if depth < 1.0:
            dl = QLabel(f"{depth:.2f}"); dl.setFont(QFont("Consolas",9))
            dl.setStyleSheet(f"color:{bar_col};background:transparent;border:none;"); dl.setFixedWidth(32); lo.addWidget(dl)


# ═══════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════
class VisionAssistApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Vision Assist v3.0")
        self.setMinimumSize(1200, 700)
        self.resize(1380, 800)
        self._worker        = None
        self._asst_worker   = None
        self._asst_history  = []          # conversation history for assistant
        self._last_dets     = []          # latest detections for assistant context
        self._last_dist_cm  = None        # latest ultrasonic reading
        self._depth_ready   = False
        self._config = {
            "mode": "basic", "confidence": 0.60, "alert_delay": 1.5,
            "min_area": 50_000, "voice_enabled": True,
            "frame_width": 640, "frame_height": 480,
            "ultrasonic_enabled": False, "ultrasonic_port": "COM3",
            "ultrasonic_baud": 9600,
        }
        self._setup_palette()
        self._build_ui()
        self._apply_style()

    def _setup_palette(self):
        pal = QPalette()
        for role, col in [
            (QPalette.Window, P["bg_dark"]), (QPalette.WindowText, P["hi"]),
            (QPalette.Base, P["bg_panel"]),  (QPalette.AlternateBase, P["bg_card"]),
            (QPalette.Text, P["hi"]),        (QPalette.Button, P["bg_card"]),
            (QPalette.ButtonText, P["hi"]),  (QPalette.Highlight, P["accent"]),
            (QPalette.HighlightedText, P["bg_dark"]),
        ]:
            pal.setColor(role, QColor(col))
        self.setPalette(pal)

    # ════════════════════════════════════════════════════════════════
    # UI BUILD
    # ════════════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)
        rl.addWidget(self._mk_header())

        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(2)
        sp.setStyleSheet(f"QSplitter::handle{{background:{P['border']};}}")

        # ── left: video ─────────────────────────────────────────────
        lw = QWidget(); lw.setStyleSheet(f"background:{P['bg_dark']};")
        ll = QVBoxLayout(lw); ll.setContentsMargins(12,12,6,6); ll.setSpacing(6)

        self.video_lbl = QLabel("▶  Press  START  to begin")
        self.video_lbl.setAlignment(Qt.AlignCenter)
        self.video_lbl.setMinimumSize(480,340)
        self.video_lbl.setFont(QFont("Consolas",14))
        self.video_lbl.setStyleSheet(
            f"QLabel{{background:#050810;border:1px solid {P['border']};"
            f"border-radius:10px;color:{P['lo']};font:14px Consolas;}}")
        ll.addWidget(self.video_lbl, 1)

        # ultrasonic distance gauge
        ll.addWidget(self._mk_sonar_gauge())

        self.badge = AlertBadge(); ll.addWidget(self.badge)
        self.alert_msg = QLabel("")
        self.alert_msg.setAlignment(Qt.AlignCenter)
        self.alert_msg.setFont(QFont("Consolas",10))
        self.alert_msg.setStyleSheet(f"color:{P['hi']};background:transparent;")
        self.alert_msg.setWordWrap(True); ll.addWidget(self.alert_msg)
        sp.addWidget(lw)

        # ── right: tabbed panels ─────────────────────────────────────
        rw = QWidget(); rw.setFixedWidth(370)
        rw.setStyleSheet(f"background:{P['bg_panel']};")
        rll = QVBoxLayout(rw); rll.setContentsMargins(6,8,10,6); rll.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:1px solid {P['border']};border-radius:6px;
                              background:{P['bg_panel']};}}
            QTabBar::tab{{background:{P['bg_card']};color:{P['mid']};
                          padding:6px 12px;font:bold 9px Consolas;
                          border:1px solid {P['border']};border-bottom:none;
                          border-top-left-radius:4px;border-top-right-radius:4px;}}
            QTabBar::tab:selected{{background:{P['bg_panel']};color:{P['accent']};
                                   border-bottom:2px solid {P['accent']};}}
            QTabBar::tab:hover{{color:{P['hi']};}}
        """)

        self.tabs.addTab(self._mk_detection_tab(),  "🎯  DETECT")
        self.tabs.addTab(self._mk_assistant_tab(),  "🤖  ASSIST")
        self.tabs.addTab(self._mk_settings_tab(),   "⚙  CONFIG")
        self.tabs.addTab(self._mk_log_tab(),        "📋  LOG")

        rll.addWidget(self.tabs)
        sp.addWidget(rw)
        sp.setSizes([990, 370])
        rl.addWidget(sp, 1)
        rl.addWidget(self._mk_statusbar())

    # ── header ──────────────────────────────────────────────────────
    def _mk_header(self):
        h = QWidget(); h.setFixedHeight(60)
        h.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {P['bg_card']},stop:1 {P['bg_dark']});"
            f"border-bottom:1px solid {P['border']};")
        lo = QHBoxLayout(h); lo.setContentsMargins(16,0,16,0); lo.setSpacing(14)

        t = QLabel("◈  AI VISION ASSIST")
        t.setFont(QFont("Consolas",16,QFont.Bold))
        t.setStyleSheet(f"color:{P['accent']};background:transparent;letter-spacing:2px;")
        lo.addWidget(t)
        s = QLabel("Obstacle detection · Depth sensing · Ultrasonic · AI Assistant")
        s.setFont(QFont("Consolas",8)); s.setStyleSheet(f"color:{P['mid']};background:transparent;")
        lo.addWidget(s); lo.addStretch()

        ml = QLabel("MODE:"); ml.setFont(QFont("Consolas",9,QFont.Bold))
        ml.setStyleSheet(f"color:{P['mid']};background:transparent;"); lo.addWidget(ml)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Basic (no depth)", "Upgraded (depth + GPU)"])
        self.mode_combo.setFixedWidth(195)
        self.mode_combo.currentIndexChanged.connect(
            lambda i: self._config.update({"mode":"upgraded" if i==1 else "basic"}))
        lo.addWidget(self.mode_combo)

        self.start_btn = QPushButton("▶  START")
        self.start_btn.setFixedSize(110,38)
        self.start_btn.setFont(QFont("Consolas",11,QFont.Bold))
        self.start_btn.clicked.connect(self._toggle)
        self.start_btn.setStyleSheet(self._btn(P["accent2"], running=False))
        lo.addWidget(self.start_btn)
        return h

    # ── sonar gauge ─────────────────────────────────────────────────
    def _mk_sonar_gauge(self):
        w = QWidget()
        w.setFixedHeight(44)
        w.setStyleSheet(f"background:{P['bg_card']};border:1px solid {P['border']};"
                        f"border-radius:8px;")
        lo = QHBoxLayout(w); lo.setContentsMargins(12,4,12,4); lo.setSpacing(10)

        icon = QLabel("📡")
        icon.setFont(QFont("Segoe UI Emoji",14)); icon.setFixedWidth(26)
        icon.setStyleSheet("background:transparent;")
        lo.addWidget(icon)

        self.sonar_lbl = QLabel("SONAR: -- cm")
        self.sonar_lbl.setFont(QFont("Consolas",11,QFont.Bold))
        self.sonar_lbl.setStyleSheet(f"color:{P['lo']};background:transparent;")
        lo.addWidget(self.sonar_lbl)

        lo.addStretch()

        self.sonar_bar = QProgressBar()
        self.sonar_bar.setRange(0,400); self.sonar_bar.setValue(0)
        self.sonar_bar.setTextVisible(False); self.sonar_bar.setFixedWidth(120)
        self.sonar_bar.setFixedHeight(10)
        self.sonar_bar.setStyleSheet(
            f"QProgressBar{{background:{P['bg_dark']};border:none;border-radius:5px;}}"
            f"QProgressBar::chunk{{background:{P['lo']};border-radius:5px;}}")
        lo.addWidget(self.sonar_bar)

        self.sonar_zone = QLabel("---")
        self.sonar_zone.setFont(QFont("Consolas",9,QFont.Bold))
        self.sonar_zone.setStyleSheet(f"color:{P['lo']};background:transparent;")
        self.sonar_zone.setFixedWidth(60)
        lo.addWidget(self.sonar_zone)
        return w

    # ── detection tab ───────────────────────────────────────────────
    def _mk_detection_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{P['bg_panel']};")
        lo = QVBoxLayout(w); lo.setContentsMargins(8,8,8,8); lo.setSpacing(6)

        self._dr_widget = QWidget(); self._dr_widget.setStyleSheet("background:transparent;")
        self._dr_lo = QVBoxLayout(self._dr_widget)
        self._dr_lo.setSpacing(3); self._dr_lo.setContentsMargins(0,0,0,0)
        ph = QLabel("No objects detected"); ph.setAlignment(Qt.AlignCenter)
        ph.setFont(QFont("Consolas",9)); ph.setStyleSheet(f"color:{P['lo']};background:transparent;border:none;")
        self._dr_lo.addWidget(ph)

        scroll = QScrollArea(); scroll.setWidget(self._dr_widget)
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea{{background:transparent;border:none;}}")
        lo.addWidget(scroll, 1)

        self.obj_cnt = QLabel("0 objects in frame")
        self.obj_cnt.setFont(QFont("Consolas",9))
        self.obj_cnt.setStyleSheet(f"color:{P['mid']};background:transparent;")
        self.obj_cnt.setAlignment(Qt.AlignRight); lo.addWidget(self.obj_cnt)
        return w

    # ── assistant tab ────────────────────────────────────────────────
    def _mk_assistant_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{P['bg_panel']};")
        lo = QVBoxLayout(w); lo.setContentsMargins(8,8,8,8); lo.setSpacing(6)

        # API key row
        key_card = _card("  ANTHROPIC API KEY")
        klo = QVBoxLayout(key_card); klo.setContentsMargins(6,4,6,4)
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-ant-api03-...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setFont(QFont("Consolas",9))
        self.api_key_input.setStyleSheet(
            f"background:{P['bg_dark']};color:{P['hi']};border:1px solid {P['border']};"
            f"border-radius:4px;padding:4px 8px;")
        klo.addWidget(self.api_key_input)

        show_btn = QPushButton("👁  Show/Hide")
        show_btn.setFixedHeight(24); show_btn.setFont(QFont("Consolas",8))
        show_btn.setStyleSheet(
            f"QPushButton{{background:{P['bg_card']};color:{P['mid']};"
            f"border:1px solid {P['border']};border-radius:4px;}}"
            f"QPushButton:hover{{color:{P['hi']}}};")
        show_btn.clicked.connect(
            lambda: self.api_key_input.setEchoMode(
                QLineEdit.Normal
                if self.api_key_input.echoMode() == QLineEdit.Password
                else QLineEdit.Password))
        klo.addWidget(show_btn)
        lo.addWidget(key_card)

        # Chat history
        chat_card = _card("  CONVERSATION")
        clo = QVBoxLayout(chat_card); clo.setContentsMargins(4,4,4,4)
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setFont(QFont("Consolas",9))
        self.chat_log.setStyleSheet(
            f"QTextEdit{{background:{P['bg_dark']};color:{P['mid']};"
            f"border:none;border-radius:4px;}}")
        clo.addWidget(self.chat_log)
        lo.addWidget(chat_card, 1)

        # Input row
        inp_row = QWidget(); inp_row.setStyleSheet("background:transparent;")
        ilo = QHBoxLayout(inp_row); ilo.setContentsMargins(0,0,0,0); ilo.setSpacing(6)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask anything… e.g. 'What is in front of me?'")
        self.chat_input.setFont(QFont("Consolas",9))
        self.chat_input.setStyleSheet(
            f"background:{P['bg_dark']};color:{P['hi']};border:1px solid {P['border']};"
            f"border-radius:6px;padding:6px 10px;")
        self.chat_input.returnPressed.connect(self._send_question)
        ilo.addWidget(self.chat_input, 1)

        ask_btn = QPushButton("ASK")
        ask_btn.setFixedSize(54, 34); ask_btn.setFont(QFont("Consolas",10,QFont.Bold))
        ask_btn.setStyleSheet(
            f"QPushButton{{background:{P['purple']}22;color:{P['purple']};"
            f"border:1px solid {P['purple']};border-radius:6px;}}"
            f"QPushButton:hover{{background:{P['purple']}44;}}")
        ask_btn.clicked.connect(self._send_question)
        ilo.addWidget(ask_btn)
        lo.addWidget(inp_row)

        # Speak response toggle
        self.speak_reply_chk = QCheckBox("Speak AI responses aloud")
        self.speak_reply_chk.setFont(QFont("Consolas",9))
        self.speak_reply_chk.setChecked(True)
        self.speak_reply_chk.setStyleSheet(f"color:{P['hi']};background:transparent;")
        lo.addWidget(self.speak_reply_chk)

        clr_btn = QPushButton("Clear conversation")
        clr_btn.setFont(QFont("Consolas",8)); clr_btn.setFixedHeight(24)
        clr_btn.clicked.connect(lambda: (self.chat_log.clear(), self._asst_history.clear()))
        clr_btn.setStyleSheet(
            f"QPushButton{{background:{P['bg_card']};color:{P['mid']};"
            f"border:1px solid {P['border']};border-radius:4px;}}"
            f"QPushButton:hover{{color:{P['hi']}}};")
        lo.addWidget(clr_btn)
        return w

    # ── settings tab ────────────────────────────────────────────────
    def _mk_settings_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{P['bg_panel']};")
        lo = QVBoxLayout(w); lo.setContentsMargins(8,8,8,8); lo.setSpacing(8)

        # Detection settings
        det_card = _card("  DETECTION")
        dlo = QGridLayout(det_card); dlo.setSpacing(8); dlo.setContentsMargins(8,4,8,4)

        dlo.addWidget(_lbl("Confidence",9,color=P["mid"]),0,0)
        self.conf_sl = self._mk_slider(30,95,60)
        self.conf_vl = _lbl("60%",9,bold=True,color=P["accent"])
        self.conf_sl.valueChanged.connect(
            lambda v: (self._config.update({"confidence":v/100}), self.conf_vl.setText(f"{v}%")))
        dlo.addWidget(self.conf_sl,0,1); dlo.addWidget(self.conf_vl,0,2)

        dlo.addWidget(_lbl("Alert delay",9,color=P["mid"]),1,0)
        self.delay_sl = self._mk_slider(5,50,15)
        self.delay_vl = _lbl("1.5s",9,bold=True,color=P["accent"])
        def _on_delay_change(v):
            self._config.update({"alert_delay": v / 10})
            self.delay_vl.setText(f"{v/10:.1f}s")
            # Reset timer so new delay takes effect on very next detection
            if self._worker and self._worker.isRunning():
                self._worker.reset_alert_timer()
        self.delay_sl.valueChanged.connect(_on_delay_change)
        dlo.addWidget(self.delay_sl,1,1); dlo.addWidget(self.delay_vl,1,2)

        self.depth_chk = QCheckBox("Depth heatmap overlay")
        self.depth_chk.setFont(QFont("Consolas",9))
        self.depth_chk.setStyleSheet(f"color:{P['hi']};background:transparent;")
        self.depth_chk.stateChanged.connect(
            lambda _: self._worker.toggle_depth() if self._worker else None)
        dlo.addWidget(self.depth_chk,2,0,1,3)

        self.voice_chk = QCheckBox("Voice alerts enabled")
        self.voice_chk.setFont(QFont("Consolas",9)); self.voice_chk.setChecked(True)
        self.voice_chk.setStyleSheet(f"color:{P['hi']};background:transparent;")
        self.voice_chk.stateChanged.connect(
            lambda s: self._config.update({"voice_enabled":bool(s)}))
        dlo.addWidget(self.voice_chk,3,0,1,3)
        lo.addWidget(det_card)

        # Ultrasonic sensor settings
        sonar_card = _card("  ULTRASONIC SENSOR  (HC-SR04 + Arduino)")
        slo = QGridLayout(sonar_card); slo.setSpacing(8); slo.setContentsMargins(8,4,8,4)

        self.sonar_en_chk = QCheckBox("Enable ultrasonic sensor")
        self.sonar_en_chk.setFont(QFont("Consolas",9))
        self.sonar_en_chk.setStyleSheet(f"color:{P['hi']};background:transparent;")
        self.sonar_en_chk.stateChanged.connect(
            lambda s: self._config.update({"ultrasonic_enabled":bool(s)}))
        slo.addWidget(self.sonar_en_chk,0,0,1,3)

        slo.addWidget(_lbl("COM port",9,color=P["mid"]),1,0)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        ports = [f"COM{i}" for i in range(1,13)] + ["/dev/ttyUSB0","/dev/ttyUSB1","/dev/ttyACM0"]
        self.port_combo.addItems(ports)
        self.port_combo.setCurrentText("COM3")
        self.port_combo.setFont(QFont("Consolas",9))
        self.port_combo.currentTextChanged.connect(
            lambda t: self._config.update({"ultrasonic_port":t}))
        slo.addWidget(self.port_combo,1,1,1,2)

        slo.addWidget(_lbl("Baud rate",9,color=P["mid"]),2,0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600","19200","38400","57600","115200"])
        self.baud_combo.setFont(QFont("Consolas",9))
        self.baud_combo.currentTextChanged.connect(
            lambda t: self._config.update({"ultrasonic_baud":int(t)}))
        slo.addWidget(self.baud_combo,2,1,1,2)

        hint = QLabel("Upload arduino/vis_assist_ultrasonic.ino to your Arduino first.")
        hint.setFont(QFont("Consolas",8)); hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{P['lo']};background:transparent;")
        slo.addWidget(hint,3,0,1,3)
        lo.addWidget(sonar_card)
        lo.addStretch()
        return w

    # ── log tab ──────────────────────────────────────────────────────
    def _mk_log_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{P['bg_panel']};")
        lo = QVBoxLayout(w); lo.setContentsMargins(8,8,8,8); lo.setSpacing(6)

        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas",8))
        self.log.setStyleSheet(
            f"QTextEdit{{background:{P['bg_dark']};color:{P['mid']};"
            f"border:none;border-radius:4px;}}")
        lo.addWidget(self.log, 1)

        clr = QPushButton("Clear log"); clr.setFont(QFont("Consolas",8)); clr.setFixedHeight(24)
        clr.clicked.connect(self.log.clear)
        clr.setStyleSheet(
            f"QPushButton{{background:{P['bg_card']};color:{P['mid']};"
            f"border:1px solid {P['border']};border-radius:4px;}}"
            f"QPushButton:hover{{color:{P['hi']}}};")
        lo.addWidget(clr)
        return w

    # ── status bar ───────────────────────────────────────────────────
    def _mk_statusbar(self):
        b = QWidget(); b.setFixedHeight(30)
        b.setStyleSheet(f"background:{P['bg_card']};border-top:1px solid {P['border']};")
        lo = QHBoxLayout(b); lo.setContentsMargins(16,0,16,0); lo.setSpacing(20)

        def _s(txt, w=140):
            l = QLabel(txt); l.setFont(QFont("Consolas",9))
            l.setStyleSheet(f"color:{P['mid']};background:transparent;")
            if w: l.setFixedWidth(w)
            return l

        self.fps_l   = _s("FPS: --", 80)
        self.dep_l   = _s("Depth: --", 100)
        self.dev_l   = _s("Device: --", 130)
        self.mode_l  = _s("Mode: --", 140)
        self.sonar_status_l = _s("Sonar: --", 120)

        for lbl in [self.fps_l, self.dep_l, self.dev_l, self.mode_l, self.sonar_status_l]:
            lo.addWidget(lbl)
        lo.addStretch()

        lo.addWidget(_s("v3.0  |  AI Vision Assist", None))
        return b

    # ── helpers ─────────────────────────────────────────────────────
    def _mk_slider(self, lo, hi, val):
        s = QSlider(Qt.Horizontal); s.setRange(lo,hi); s.setValue(val); s.setFixedHeight(18)
        s.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px;background:{P['border']};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{P['accent']};border:none;"
            f"width:12px;height:12px;margin:-4px 0;border-radius:6px;}}"
            f"QSlider::sub-page:horizontal{{background:{P['accent']};border-radius:2px;}}")
        return s

    def _btn(self, col, running):
        if not running:
            return (f"QPushButton{{background:{col}22;color:{col};"
                    f"border:1px solid {col};border-radius:8px;}}"
                    f"QPushButton:hover{{background:{col}44;}}")
        return (f"QPushButton{{background:{P['danger']}22;color:{P['danger']};"
                f"border:1px solid {P['danger']};border-radius:8px;}}"
                f"QPushButton:hover{{background:{P['danger']}44;}}")

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget{{background:{P['bg_dark']};color:{P['hi']};}}
            QComboBox{{background:{P['bg_card']};color:{P['hi']};
                       border:1px solid {P['border']};border-radius:6px;
                       padding:4px 8px;font:10px Consolas;}}
            QComboBox::drop-down{{border:none;}}
            QComboBox QAbstractItemView{{background:{P['bg_card']};color:{P['hi']};
                selection-background-color:{P['accent']}33;}}
            QScrollBar:vertical{{background:{P['bg_dark']};width:8px;border-radius:4px;}}
            QScrollBar::handle:vertical{{background:{P['border']};border-radius:4px;min-height:30px;}}
        """)

    # ════════════════════════════════════════════════════════════════
    # PIPELINE CONTROL
    # ════════════════════════════════════════════════════════════════
    def _toggle(self):
        if self._worker and self._worker.isRunning(): self._stop()
        else: self._start()

    def _start(self):
        self._worker = PipelineWorker(self._config)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.stats_updated.connect(self._on_stats)
        self._worker.alert_triggered.connect(self._on_alert)
        self._worker.distance_updated.connect(self._on_distance)
        self._worker.startup_error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self.start_btn.setText("■  STOP")
        self.start_btn.setStyleSheet(self._btn(P["danger"], running=True))
        self.mode_combo.setEnabled(False)
        self.video_lbl.setText("⏳  Loading models …")
        self.video_lbl.setPixmap(QPixmap())

    def _stop(self):
        if self._worker:
            self._worker.stop(); self._worker.wait(4000); self._worker = None
        self._reset()

    def _reset(self):
        self.start_btn.setText("▶  START")
        self.start_btn.setStyleSheet(self._btn(P["accent2"], running=False))
        self.mode_combo.setEnabled(True)
        self.video_lbl.setPixmap(QPixmap())
        self.video_lbl.setText("▶  Press  START  to begin")
        self.badge.set_urgency("none"); self.alert_msg.setText("")
        self._clear_rows()
        for lbl in [self.fps_l, self.dev_l, self.dep_l, self.mode_l]:
            lbl.setText(lbl.text().split(":")[0] + ": --")
        self.sonar_status_l.setText("Sonar: --")
        self._update_sonar_gauge(None)

    # ════════════════════════════════════════════════════════════════
    # SIGNAL HANDLERS
    # ════════════════════════════════════════════════════════════════
    def _on_frame(self, frame, detections, advice):
        self._last_dets = detections
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, w*3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.video_lbl.width(), self.video_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_lbl.setPixmap(pix)
        self._update_rows(detections, advice)

    def _on_stats(self, s):
        self._depth_ready = s["depth_ready"]
        self.fps_l.setText(f"FPS: {s['fps']:.1f}")
        self.dev_l.setText(f"Device: {s['device']}")
        on = s["depth_ready"]
        self.dep_l.setText(f"Depth: {'ON ✓' if on else 'OFF'}")
        self.dep_l.setStyleSheet(f"color:{P['accent2'] if on else P['lo']};background:transparent;")
        self.mode_l.setText(f"Mode: {'Upgraded' if s['mode']=='upgraded' else 'Basic'}")
        sensor_on = s.get("sensor_on", False)
        self.sonar_status_l.setText(f"Sonar: {'ON ✓' if sensor_on else 'OFF'}")
        self.sonar_status_l.setStyleSheet(
            f"color:{P['accent2'] if sensor_on else P['lo']};background:transparent;")

    def _on_alert(self, msg, urgency):
        self.badge.set_urgency(urgency)
        self.alert_msg.setText(msg)
        col = {"critical":P["danger"],"warning":P["warn"],"info":P["accent"]}.get(urgency, P["mid"])
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(
            f'<span style="color:{P["lo"]}">[{ts}]</span> '
            f'<span style="color:{col}"><b>{urgency.upper():8}</b></span> '
            f'<span style="color:{P["hi"]}">{msg}</span>')
        sb = self.log.verticalScrollBar(); sb.setValue(sb.maximum())

    def _on_distance(self, dist_cm):
        self._last_dist_cm = dist_cm
        self._update_sonar_gauge(dist_cm)

    def _update_sonar_gauge(self, dist_cm):
        if dist_cm is None:
            self.sonar_lbl.setText("SONAR: -- cm")
            self.sonar_lbl.setStyleSheet(f"color:{P['lo']};background:transparent;")
            self.sonar_bar.setValue(0)
            self.sonar_bar.setStyleSheet(
                f"QProgressBar{{background:{P['bg_dark']};border:none;border-radius:5px;}}"
                f"QProgressBar::chunk{{background:{P['lo']};border-radius:5px;}}")
            self.sonar_zone.setText("---")
            return

        if dist_cm < 50:
            col, zone_txt = P["danger"],  "DANGER"
        elif dist_cm < 150:
            col, zone_txt = P["warn"],    "CLOSE"
        elif dist_cm < 300:
            col, zone_txt = P["accent"],  "CAUTION"
        else:
            col, zone_txt = P["accent2"], "SAFE"

        self.sonar_lbl.setText(f"SONAR: {dist_cm:.0f} cm  ({dist_cm/30.48:.1f} ft)")
        self.sonar_lbl.setStyleSheet(f"color:{col};background:transparent;")
        self.sonar_bar.setValue(min(400, int(dist_cm)))
        self.sonar_bar.setStyleSheet(
            f"QProgressBar{{background:{P['bg_dark']};border:none;border-radius:5px;}}"
            f"QProgressBar::chunk{{background:{col};border-radius:5px;}}")
        self.sonar_zone.setText(zone_txt)
        self.sonar_zone.setStyleSheet(f"color:{col};background:transparent;font:bold 9px Consolas;")

    def _on_error(self, msg):
        self._reset()
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Startup Error"); dlg.setIcon(QMessageBox.Critical)
        dlg.setText("<b>The pipeline could not start.</b>"); dlg.setInformativeText(msg)
        dlg.setStyleSheet(
            f"QMessageBox{{background:{P['bg_panel']};color:{P['hi']};font:10px Consolas;}}"
            f"QLabel{{color:{P['hi']}}};"
            f"QPushButton{{background:{P['bg_card']};color:{P['accent']};"
            f"border:1px solid {P['border']};border-radius:4px;padding:4px 16px;}}")
        dlg.exec_()

    def _on_finished(self):
        self._worker = None
        if "STOP" in self.start_btn.text(): self._reset()

    # ════════════════════════════════════════════════════════════════
    # AI ASSISTANT
    # ════════════════════════════════════════════════════════════════
    def _send_question(self):
        question = self.chat_input.text().strip()
        if not question:
            return

        api_key = self.api_key_input.text().strip()
        if not api_key:
            self.chat_log.append(
                f'<span style="color:{P["danger"]}"><b>⚠ Enter your Anthropic API key in the field above.</b></span>')
            return

        if self._asst_worker and self._asst_worker.isRunning():
            return  # still processing previous question

        # Show user message
        self.chat_log.append(
            f'<span style="color:{P["accent"]}"><b>You:</b></span> '
            f'<span style="color:{P["hi"]}">{question}</span>')
        self.chat_log.append(
            f'<span style="color:{P["lo"]}"><i>Assistant is thinking…</i></span>')
        sb = self.chat_log.verticalScrollBar(); sb.setValue(sb.maximum())
        self.chat_input.clear()

        # Launch worker
        self._asst_worker = AssistantWorker(
            api_key     = api_key,
            question    = question,
            detections  = list(self._last_dets),
            distance_cm = self._last_dist_cm,
            depth_ready = self._depth_ready,
            history     = self._asst_history,
        )
        self._asst_worker.response_ready.connect(
            lambda ans: self._on_asst_response(question, ans))
        self._asst_worker.error_occurred.connect(self._on_asst_error)
        self._asst_worker.start()

    def _on_asst_response(self, question, answer):
        # Remove "thinking…" line
        cursor = self.chat_log.textCursor()
        doc    = self.chat_log.document()
        last   = doc.lastBlock()
        cursor.select(cursor.BlockUnderCursor)
        # Simple approach: append the answer
        self.chat_log.append(
            f'<span style="color:{P["purple"]}"><b>AI:</b></span> '
            f'<span style="color:{P["hi"]}">{answer}</span><br>')
        sb = self.chat_log.verticalScrollBar(); sb.setValue(sb.maximum())

        # Update history
        self._asst_history.append({"role":"user",      "content": question})
        self._asst_history.append({"role":"assistant", "content": answer})
        if len(self._asst_history) > 20:
            self._asst_history = self._asst_history[-20:]

        # Speak if requested and worker voice is available
        if self.speak_reply_chk.isChecked() and self._worker and self._worker.voice:
            try:
                from voice import PRIORITY_INFO
                self._worker.voice.speak(answer, priority=PRIORITY_INFO)
            except Exception:
                pass

    def _on_asst_error(self, err):
        self.chat_log.append(
            f'<span style="color:{P["danger"]}"><b>Error:</b></span> '
            f'<span style="color:{P["warn"]}">{err}</span>')
        sb = self.chat_log.verticalScrollBar(); sb.setValue(sb.maximum())

    # ════════════════════════════════════════════════════════════════
    # DETECTION ROWS
    # ════════════════════════════════════════════════════════════════
    def _clear_rows(self):
        while self._dr_lo.count():
            item = self._dr_lo.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        ph = QLabel("No objects detected"); ph.setAlignment(Qt.AlignCenter)
        ph.setFont(QFont("Consolas",9)); ph.setStyleSheet(f"color:{P['lo']};background:transparent;border:none;")
        self._dr_lo.addWidget(ph); self.obj_cnt.setText("0 objects in frame")

    def _update_rows(self, detections, advice):
        while self._dr_lo.count():
            item = self._dr_lo.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not detections:
            ph = QLabel("No objects detected"); ph.setAlignment(Qt.AlignCenter)
            ph.setFont(QFont("Consolas",9)); ph.setStyleSheet(f"color:{P['lo']};background:transparent;border:none;")
            self._dr_lo.addWidget(ph); self.obj_cnt.setText("0 objects in frame")
            self.badge.set_urgency("none"); self.alert_msg.setText(""); return
        adv_depth = advice.depth_value if advice else 0.9
        for det in detections[:8]:
            depth = adv_depth if (advice and advice.object_name==det.class_name) else 0.9
            self._dr_lo.addWidget(DetectionRow(det.class_name, det.confidence, depth))
        n = len(detections)
        self.obj_cnt.setText(f"{n} object{'s' if n!=1 else ''} in frame")

    def closeEvent(self, event):
        self._stop(); super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("AI Vision Assist")
    app.setStyle("Fusion")
    win = VisionAssistApp()
    win.show()
    sys.exit(app.exec_())