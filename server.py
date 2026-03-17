"""
server.py — Vision Assist WebSocket Server

Bridges the Python vision pipeline with the React frontend.

Architecture
------------
    React UI (browser)
        ↕  WebSocket  ws://localhost:8000/ws
    FastAPI server (this file)
        ↕  direct calls
    Vision pipeline (src/)

Messages  SERVER → CLIENT (JSON)
---------------------------------
    {"type":"frame",      "data":"<base64-jpeg>"}
    {"type":"detections", "data":[{"name":"person","conf":0.92,"depth":0.78,"pos":"left"},...]}
    {"type":"alert",      "message":"Warning! Person ahead.","urgency":"critical"}
    {"type":"stats",      "fps":18.3,"device":"GPU (CUDA)","depth_ready":true,"mode":"upgraded","sensor_on":false}
    {"type":"distance",   "cm":84.2,"zone":"warning"}
    {"type":"assistant",  "answer":"There is a person 84 cm ahead on your left."}
    {"type":"error",      "message":"..."}
    {"type":"status",     "running":true}

Messages  CLIENT → SERVER (JSON)
---------------------------------
    {"type":"start",  "mode":"basic"|"upgraded", "confidence":0.6, "alert_delay":1.5,
                      "voice_enabled":true, "ultrasonic_enabled":false,
                      "ultrasonic_port":"COM3", "ultrasonic_baud":9600}
    {"type":"stop"}
    {"type":"settings","confidence":0.65,"alert_delay":1.2}
    {"type":"depth_overlay","enabled":true}
    {"type":"ask","question":"What is ahead?","api_key":"sk-ant-..."}

Run
---
    pip install fastapi uvicorn websockets opencv-python
    python server.py
    Then open frontend/index.html in your browser.
"""

import sys, os, asyncio, base64, json, time, threading
from collections import deque
from typing import Optional

# ── src imports ──────────────────────────────────────────────────────
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import cv2
import numpy as np
import torch

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# ════════════════════════════════════════════════════════════════════
# PIPELINE  (runs in a background thread)
# ════════════════════════════════════════════════════════════════════
class Pipeline:
    """Runs the vision pipeline in a background thread and pushes
    events into a thread-safe queue consumed by the WebSocket handler."""

    def __init__(self):
        self._thread     : Optional[threading.Thread] = None
        self._running    = False
        self._config     = {}
        self._show_depth = False
        self.queue       = asyncio.Queue()
        self._loop       : Optional[asyncio.AbstractEventLoop] = None
        self.voice       = None
        self._last_alert = 0.0   # initialised here so reset_alert_timer() is always safe

    def start(self, config: dict, loop: asyncio.AbstractEventLoop):
        if self._running:
            return
        self._config   = config
        self._loop     = loop
        self._running  = True
        self._thread   = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.voice:
            try: self.voice.stop()
            except: pass

    def update_settings(self, settings: dict):
        self._config.update(settings)
        # Reset alert timer so new delay/confidence takes effect immediately
        self._last_alert = 0.0

    def toggle_depth(self, enabled: bool):
        self._show_depth = enabled

    def reset_alert_timer(self):
        self._last_alert = 0.0

    # ── push event to the async queue ───────────────────────────────
    def _push(self, event: dict):
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self.queue.put(event), self._loop
            )

    # ── pipeline thread ─────────────────────────────────────────────
    def _run(self):
        from detection  import ObjectDetector
        from navigation import Navigator
        from voice      import VoiceEngine, PRIORITY_CRITICAL, PRIORITY_WARNING, PRIORITY_INFO

        device       = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        device_label = "GPU (CUDA)" if device.type == "cuda" else "CPU"

        # Voice
        self.voice = VoiceEngine(rate=185)
        self.voice.start()

        # YOLO
        mode       = self._config.get("mode", "basic")
        model_name = "yolov8x.pt" if mode == "upgraded" else "yolov8n.pt"
        model_path = os.path.join(os.path.dirname(__file__), "models", model_name)

        try:
            detector = ObjectDetector(model_path=model_path,
                                      confidence=self._config.get("confidence", 0.60),
                                      device=device)
        except Exception as exc:
            self._push({"type": "error", "message": f"YOLO load failed: {exc}"})
            self.voice.stop()
            self._running = False
            return

        navigator = Navigator(frame_width=640, frame_height=480)

        # MiDaS
        depth_est   = None
        depth_ready = False
        if mode == "upgraded":
            try:
                from depth import DepthEstimator
                depth_est   = DepthEstimator(device=device, frame_skip=3)
                depth_ready = True
            except Exception as exc:
                self._push({"type": "error", "message": f"MiDaS unavailable: {exc}"})

        # Ultrasonic
        sensor = None
        if self._config.get("ultrasonic_enabled") and self._config.get("ultrasonic_port"):
            try:
                from ultrasonic import UltrasonicSensor
                sensor = UltrasonicSensor(
                    port=self._config["ultrasonic_port"],
                    baudrate=self._config.get("ultrasonic_baud", 9600),
                )
                sensor.start()
            except Exception as exc:
                self._push({"type":"error","message":f"Sensor: {exc}"})

        # Camera
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            self._push({"type":"error","message":"Cannot open camera."})
            self.voice.stop()
            self._running = False
            return

        self._last_alert = 0.0   # reset at start of each run
        self._push({"type":"status","running":True})

        fps_buf = deque(maxlen=20)
        t_prev  = time.time()

        PMAP = {"critical": PRIORITY_CRITICAL, "warning": PRIORITY_WARNING, "info": PRIORITY_INFO}

        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.03)
                continue

            t_now = time.time()
            fps_buf.append(1.0 / max(t_now - t_prev, 1e-6))
            t_prev = t_now

            frame = cv2.resize(frame, (640, 480))

            # Depth
            depth_map = depth_est.update(frame) if depth_est else None

            # Detection
            detector.confidence = self._config.get("confidence", 0.60)
            detections = detector.detect(frame)

            # Navigation
            if depth_map is not None:
                advice = navigator.analyse(detections, depth_map)
            else:
                advice = navigator.analyse_by_area(detections)

            # Sonar
            dist_cm = sensor.distance_cm if sensor else None
            if dist_cm is not None:
                from ultrasonic import ZONE_DANGER, ZONE_WARNING
                zone = ("danger" if dist_cm < ZONE_DANGER
                        else "warning" if dist_cm < ZONE_WARNING
                        else "safe")
                self._push({"type":"distance","cm":round(dist_cm,1),"zone":zone})

                if dist_cm < 50 and advice is None:
                    msg = f"Object {dist_cm:.0f} cm ahead. Stop immediately."
                    t_cur = time.time()
                    if (t_cur - self._last_alert) > self._config.get("alert_delay", 1.5):
                        if self._config.get("voice_enabled", True):
                            self.voice.speak(msg, priority=PRIORITY_CRITICAL)
                        self._push({"type":"alert","message":msg,"urgency":"critical"})
                        self._last_alert = t_cur

            # Alert
            t_cur = time.time()
            if advice and (t_cur - self._last_alert) > self._config.get("alert_delay", 1.5):
                if self._config.get("voice_enabled", True):
                    self.voice.speak(advice.message,
                                     priority=PMAP.get(advice.urgency, PRIORITY_WARNING))
                self._push({"type":"alert","message":advice.message,"urgency":advice.urgency})
                self._last_alert = t_cur

            # Render frame
            disp = self._render(frame, detections, depth_map, dist_cm)

            # Encode to JPEG base64
            _, buf = cv2.imencode(".jpg", disp, [cv2.IMWRITE_JPEG_QUALITY, 75])
            b64 = base64.b64encode(buf).decode("ascii")
            self._push({"type":"frame","data":b64})

            # Detection list
            det_list = []
            for d in detections[:8]:
                dv = 0.0
                if depth_map is not None:
                    from navigation import Navigator as _N
                    dv = _N._sample_depth(depth_map, d.center_x, d.center_y)
                det_list.append({
                    "name": d.class_name, "conf": round(d.confidence, 2),
                    "depth": round(dv, 2), "pos": navigator._horizontal_zone(d.center_x),
                    "area": d.area,
                })
            self._push({"type":"detections","data":det_list})

            # Stats
            self._push({"type":"stats",
                        "fps": round(sum(fps_buf)/len(fps_buf), 1),
                        "device": device_label,
                        "depth_ready": depth_est.ever_ready if depth_est else False,
                        "mode": mode,
                        "sensor_on": sensor is not None and sensor.is_connected})

        cap.release()
        if sensor: sensor.stop()
        if self.voice: self.voice.stop()
        self._push({"type":"status","running":False})

    def _render(self, frame, detections, depth_map, dist_cm=None):
        from navigation import ZONE_VERY_CLOSE, ZONE_CLOSE
        disp = frame.copy()

        if self._show_depth and depth_map is not None:
            heat = cv2.applyColorMap(
                (depth_map * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
            disp = cv2.addWeighted(disp, 0.55, heat, 0.45, 0)

        for det in detections:
            dv = 0.0
            if depth_map is not None:
                from navigation import Navigator as _N
                dv = _N._sample_depth(depth_map, det.center_x, det.center_y)
            col = ((60,60,255) if dv >= ZONE_VERY_CLOSE
                   else (40,160,255) if dv >= ZONE_CLOSE
                   else (60,220,100))
            cv2.rectangle(disp, (det.x1,det.y1),(det.x2,det.y2), col, 2)
            lbl = f"{det.class_name} {det.confidence:.0%}"
            if depth_map is not None: lbl += f" {dv:.2f}"
            (tw,th),_ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            cv2.rectangle(disp,(det.x1,det.y1-th-8),(det.x1+tw+6,det.y1),col,-1)
            cv2.putText(disp,lbl,(det.x1+3,det.y1-4),
                        cv2.FONT_HERSHEY_SIMPLEX,0.48,(255,255,255),1)

        h,w = disp.shape[:2]
        for x in [w//3, 2*w//3]:
            cv2.line(disp,(x,0),(x,h),(60,80,100),1)

        if dist_cm is not None:
            col = (0,60,255) if dist_cm<50 else (0,140,255) if dist_cm<150 else (60,220,100)
            cv2.rectangle(disp,(6,h-34),(230,h-6),(10,15,30),-1)
            cv2.putText(disp,f"SONAR: {dist_cm:.0f}cm ({dist_cm/30.48:.1f}ft)",
                        (10,h-12),cv2.FONT_HERSHEY_SIMPLEX,0.52,col,2)
        return disp


# ════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ════════════════════════════════════════════════════════════════════
app      = FastAPI()
pipeline = Pipeline()

# Serve the frontend folder as static files
_FRONTEND = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")

@app.get("/")
async def index():
    return FileResponse(os.path.join(_FRONTEND, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_event_loop()
    pipeline.queue = asyncio.Queue()

    # Task: forward pipeline events to the WebSocket client
    async def sender():
        while True:
            try:
                event = await asyncio.wait_for(pipeline.queue.get(), timeout=1.0)
                await ws.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

    sender_task = asyncio.create_task(sender())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t   = msg.get("type")

            if t == "start":
                config = {k: msg[k] for k in msg if k != "type"}
                pipeline.start(config, loop)

            elif t == "stop":
                pipeline.stop()

            elif t == "settings":
                settings = {k: msg[k] for k in msg if k != "type"}
                pipeline.update_settings(settings)
                pipeline.reset_alert_timer()

            elif t == "depth_overlay":
                pipeline.toggle_depth(msg.get("enabled", False))

            elif t == "ask":
                question = msg.get("question", "")
                api_key  = msg.get("api_key", "")
                # Run AI call in thread to not block event loop
                async def ask_ai():
                    try:
                        import anthropic
                        client = anthropic.Anthropic(api_key=api_key)
                        # Build scene context from latest state
                        response = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=300,
                            system=(
                                "You are a helpful AI assistant in a wearable vision system "
                                "for visually impaired users. Give brief, clear spoken responses "
                                "(1-3 sentences, no markdown). Always prioritise safety."
                            ),
                            messages=[{"role":"user","content":question}]
                        )
                        answer = response.content[0].text.strip()
                        await ws.send_text(json.dumps({"type":"assistant","answer":answer}))
                        if pipeline.voice and pipeline._config.get("voice_enabled", True):
                            from voice import PRIORITY_INFO
                            pipeline.voice.speak(answer, priority=PRIORITY_INFO)
                    except Exception as exc:
                        await ws.send_text(json.dumps({"type":"assistant","answer":f"Error: {exc}"}))
                asyncio.create_task(ask_ai())

    except WebSocketDisconnect:
        pass
    finally:
        pipeline.stop()
        sender_task.cancel()


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  AI Vision Assist — Web Server")
    print("  Open:  http://localhost:8000")
    print("="*55 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")