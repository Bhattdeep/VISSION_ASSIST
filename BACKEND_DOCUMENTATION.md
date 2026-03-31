# Backend Documentation

## Purpose

This project's backend is the Python runtime that:

1. Captures frames from the camera.
2. Runs object detection with YOLO.
3. Optionally runs depth estimation with MiDaS.
4. Estimates obstacle distance and urgency.
5. Produces alerts, voice guidance, and assistant answers.
6. Streams everything to the frontend through FastAPI + WebSocket.

For backend work, the most important file is [server.py](/C:/VISSION_ASSIST/server.py). The `src/` folder contains the domain modules that the server orchestrates.

## Backend File Map

- [server.py](/C:/VISSION_ASSIST/server.py): FastAPI app, WebSocket API, pipeline lifecycle, frame streaming.
- [src/detection.py](/C:/VISSION_ASSIST/src/detection.py): YOLO wrapper and `Detection` model.
- [src/navigation.py](/C:/VISSION_ASSIST/src/navigation.py): converts detections + depth into user-facing advice.
- [src/ranging.py](/C:/VISSION_ASSIST/src/ranging.py): approximate monocular distance estimation and smoothing.
- [src/depth.py](/C:/VISSION_ASSIST/src/depth.py): MiDaS depth model loading and cached inference.
- [src/voice.py](/C:/VISSION_ASSIST/src/voice.py): thread-safe text-to-speech queue.
- [src/alerts.py](/C:/VISSION_ASSIST/src/alerts.py): alert repetition suppression.
- [src/assistant_llm.py](/C:/VISSION_ASSIST/src/assistant_llm.py): scene-to-prompt conversion and Gemini HTTP call.
- [src/speech_input.py](/C:/VISSION_ASSIST/src/speech_input.py): Windows speech recognition helper for the GUI.

## Architecture

```text
Browser React UI
    |
    | WebSocket JSON messages
    v
FastAPI server (server.py)
    |
    | starts/stops
    v
Pipeline thread
    |
    +--> YOLO detector
    +--> MiDaS depth estimator (upgraded mode only)
    +--> Navigation engine
    +--> Distance estimator + smoother
    +--> Alert suppressor
    +--> Voice engine
    |
    v
Events pushed into asyncio queue
    |
    v
WebSocket sender task
    |
    v
Frontend updates video, detections, stats, alerts
```

## Runtime Lifecycle

### 1. Server startup

When [server.py](/C:/VISSION_ASSIST/server.py) is run directly, it starts Uvicorn on port `8000` at [server.py:426](/C:/VISSION_ASSIST/server.py#L426).

### 2. WebSocket connection

When the frontend connects to `/ws`, the backend accepts the socket, creates a fresh asyncio queue, and launches a sender coroutine that forwards pipeline events to the client at [server.py:356](/C:/VISSION_ASSIST/server.py#L356).

### 3. Pipeline start

When the client sends:

```json
{"type":"start","mode":"basic","confidence":0.6,"alert_delay":1.5}
```

the WebSocket handler calls `pipeline.start(config, loop)` at [server.py:381](/C:/VISSION_ASSIST/server.py#L381).

### 4. Background processing loop

The pipeline thread:

1. Loads voice.
2. Loads YOLO.
3. Optionally loads MiDaS.
4. Optionally starts an ultrasonic sensor.
5. Opens the camera.
6. Loops over frames until stopped.

This happens inside `Pipeline._run()` starting at [server.py:117](/C:/VISSION_ASSIST/server.py#L117).

### 5. Event fan-out

Each loop iteration can emit:

- `frame`
- `detections`
- `alert`
- `stats`
- `distance`
- `error`
- `status`

Events are added to the asyncio queue through `_push()` at [server.py:109](/C:/VISSION_ASSIST/server.py#L109).

### 6. Stop / disconnect

Stopping or disconnecting sets `_running = False`, stops voice, releases the camera, and emits `{"type":"status","running":false}` at [server.py:89](/C:/VISSION_ASSIST/server.py#L89) and [server.py:419](/C:/VISSION_ASSIST/server.py#L419).

## Data Contracts

### Client to server

Defined in the docstring at [server.py:25](/C:/VISSION_ASSIST/server.py#L25):

- `start`
- `stop`
- `settings`
- `depth_overlay`
- `ask`

### Server to client

Defined in the docstring at [server.py:14](/C:/VISSION_ASSIST/server.py#L14):

- `frame`
- `detections`
- `alert`
- `stats`
- `distance`
- `assistant`
- `error`
- `status`

## Detailed Walkthrough

## 1. server.py

### What this file does

This file is both:

1. The API server.
2. The application orchestrator.

It does not implement the detection or navigation algorithms itself. Instead, it wires together the modules in `src/`.

### Line-by-line explanation

#### Header and imports

- [server.py:1](/C:/VISSION_ASSIST/server.py#L1) starts a long module docstring that explains the server role and message format.
- [server.py:14](/C:/VISSION_ASSIST/server.py#L14) documents outbound messages.
- [server.py:25](/C:/VISSION_ASSIST/server.py#L25) documents inbound messages.
- [server.py:42](/C:/VISSION_ASSIST/server.py#L42) imports standard library modules for async work, encoding, timing, and threading.
- [server.py:47](/C:/VISSION_ASSIST/server.py#L47) builds the absolute `src/` path.
- [server.py:48](/C:/VISSION_ASSIST/server.py#L48) injects `src/` into `sys.path` so local modules like `detection` and `navigation` can be imported directly.
- [server.py:51](/C:/VISSION_ASSIST/server.py#L51) imports OpenCV, NumPy, and Torch.
- [server.py:55](/C:/VISSION_ASSIST/server.py#L55) imports FastAPI and WebSocket classes.
- [server.py:58](/C:/VISSION_ASSIST/server.py#L58) imports Uvicorn for running the HTTP server.

#### Pipeline class state

- [server.py:63](/C:/VISSION_ASSIST/server.py#L63) defines `Pipeline`, the core runtime controller.
- [server.py:67](/C:/VISSION_ASSIST/server.py#L67) begins the constructor.
- [server.py:68](/C:/VISSION_ASSIST/server.py#L68) stores the worker thread handle.
- [server.py:69](/C:/VISSION_ASSIST/server.py#L69) tracks whether the loop should keep running.
- [server.py:70](/C:/VISSION_ASSIST/server.py#L70) stores runtime config sent by the client.
- [server.py:71](/C:/VISSION_ASSIST/server.py#L71) tracks whether depth overlay should be drawn in rendered frames.
- [server.py:72](/C:/VISSION_ASSIST/server.py#L72) creates an asyncio queue used to move events from the worker thread to the WebSocket task.
- [server.py:73](/C:/VISSION_ASSIST/server.py#L73) stores the owning event loop reference.
- [server.py:74](/C:/VISSION_ASSIST/server.py#L74) holds the TTS engine instance.
- [server.py:75](/C:/VISSION_ASSIST/server.py#L75) tracks the last alert timestamp for cooldown behavior.
- [server.py:76](/C:/VISSION_ASSIST/server.py#L76) caches the most recent detections for LLM questions.
- [server.py:77](/C:/VISSION_ASSIST/server.py#L77) caches the last sonar distance.
- [server.py:78](/C:/VISSION_ASSIST/server.py#L78) records whether depth has successfully produced any map yet.

#### Pipeline control methods

- [server.py:80](/C:/VISSION_ASSIST/server.py#L80) defines `start()`.
- [server.py:81](/C:/VISSION_ASSIST/server.py#L81) prevents double-starting the pipeline.
- [server.py:83](/C:/VISSION_ASSIST/server.py#L83) stores the new config.
- [server.py:84](/C:/VISSION_ASSIST/server.py#L84) stores the main asyncio loop so thread-safe queue writes are possible.
- [server.py:85](/C:/VISSION_ASSIST/server.py#L85) marks the pipeline as running.
- [server.py:86](/C:/VISSION_ASSIST/server.py#L86) creates a daemon thread targeting `_run`.
- [server.py:87](/C:/VISSION_ASSIST/server.py#L87) starts the thread.

- [server.py:89](/C:/VISSION_ASSIST/server.py#L89) defines `stop()`.
- [server.py:90](/C:/VISSION_ASSIST/server.py#L90) tells the main loop to exit.
- [server.py:91](/C:/VISSION_ASSIST/server.py#L91) clears cached detections.
- [server.py:92](/C:/VISSION_ASSIST/server.py#L92) clears cached distance.
- [server.py:93](/C:/VISSION_ASSIST/server.py#L93) resets depth state.
- [server.py:94](/C:/VISSION_ASSIST/server.py#L94) checks whether voice exists.
- [server.py:95](/C:/VISSION_ASSIST/server.py#L95) attempts to stop voice cleanly.

- [server.py:98](/C:/VISSION_ASSIST/server.py#L98) defines `update_settings()`.
- [server.py:99](/C:/VISSION_ASSIST/server.py#L99) merges partial config from the client into the current config.
- [server.py:101](/C:/VISSION_ASSIST/server.py#L101) resets the cooldown so new settings apply immediately.

- [server.py:103](/C:/VISSION_ASSIST/server.py#L103) toggles depth overlay rendering.
- [server.py:106](/C:/VISSION_ASSIST/server.py#L106) explicitly resets the alert timer.

#### Queue bridge

- [server.py:110](/C:/VISSION_ASSIST/server.py#L110) defines `_push()`.
- [server.py:111](/C:/VISSION_ASSIST/server.py#L111) ensures the main event loop still exists.
- [server.py:112](/C:/VISSION_ASSIST/server.py#L112) uses `asyncio.run_coroutine_threadsafe(...)` because the worker thread cannot `await` directly.
- [server.py:113](/C:/VISSION_ASSIST/server.py#L113) schedules `queue.put(event)` on the main loop.

#### Pipeline bootstrap inside `_run()`

- [server.py:117](/C:/VISSION_ASSIST/server.py#L117) begins the background pipeline.
- [server.py:118](/C:/VISSION_ASSIST/server.py#L118) imports `ObjectDetector` lazily, so the server can import faster before the pipeline starts.
- [server.py:119](/C:/VISSION_ASSIST/server.py#L119) imports `Navigator`.
- [server.py:120](/C:/VISSION_ASSIST/server.py#L120) imports voice engine and priority constants.
- [server.py:121](/C:/VISSION_ASSIST/server.py#L121) imports `AlertSuppressor`.
- [server.py:123](/C:/VISSION_ASSIST/server.py#L123) chooses GPU if CUDA is available, otherwise CPU.
- [server.py:124](/C:/VISSION_ASSIST/server.py#L124) builds a frontend-friendly device label string.

- [server.py:127](/C:/VISSION_ASSIST/server.py#L127) creates the voice engine.
- [server.py:128](/C:/VISSION_ASSIST/server.py#L128) starts the voice worker thread.

- [server.py:131](/C:/VISSION_ASSIST/server.py#L131) reads the requested mode from config.
- [server.py:132](/C:/VISSION_ASSIST/server.py#L132) maps mode to YOLO weights.
- [server.py:133](/C:/VISSION_ASSIST/server.py#L133) resolves the model path.
- [server.py:135](/C:/VISSION_ASSIST/server.py#L135) begins safe YOLO loading.
- [server.py:136](/C:/VISSION_ASSIST/server.py#L136) creates `ObjectDetector`.
- [server.py:137](/C:/VISSION_ASSIST/server.py#L137) passes the current confidence threshold.
- [server.py:138](/C:/VISSION_ASSIST/server.py#L138) forces detector device alignment with the pipeline.
- [server.py:139](/C:/VISSION_ASSIST/server.py#L139) catches model load failure.
- [server.py:140](/C:/VISSION_ASSIST/server.py#L140) sends the error to the client.
- [server.py:141](/C:/VISSION_ASSIST/server.py#L141) stops voice because the pipeline cannot proceed.
- [server.py:142](/C:/VISSION_ASSIST/server.py#L142) marks the pipeline as not running.
- [server.py:143](/C:/VISSION_ASSIST/server.py#L143) exits the thread early.

- [server.py:145](/C:/VISSION_ASSIST/server.py#L145) creates the `Navigator`.

#### Optional depth and ultrasonic setup

- [server.py:148](/C:/VISSION_ASSIST/server.py#L148) initializes `depth_est` to `None`.
- [server.py:150](/C:/VISSION_ASSIST/server.py#L150) only enables MiDaS in upgraded mode.
- [server.py:152](/C:/VISSION_ASSIST/server.py#L152) imports `DepthEstimator` lazily.
- [server.py:153](/C:/VISSION_ASSIST/server.py#L153) creates the depth estimator with frame skipping.
- [server.py:155](/C:/VISSION_ASSIST/server.py#L155) catches MiDaS failure and reports it without crashing the whole pipeline.

- [server.py:159](/C:/VISSION_ASSIST/server.py#L159) initializes the optional ultrasonic sensor reference.
- [server.py:160](/C:/VISSION_ASSIST/server.py#L160) only tries sonar when enabled and a port exists.
- [server.py:162](/C:/VISSION_ASSIST/server.py#L162) imports `UltrasonicSensor`.
- [server.py:163](/C:/VISSION_ASSIST/server.py#L163) constructs the sensor.
- [server.py:167](/C:/VISSION_ASSIST/server.py#L167) starts reading from the sensor.
- [server.py:168](/C:/VISSION_ASSIST/server.py#L168) treats sonar startup as optional by sending an error instead of aborting.

#### Camera and per-run state

- [server.py:172](/C:/VISSION_ASSIST/server.py#L172) opens camera index `0`.
- [server.py:173](/C:/VISSION_ASSIST/server.py#L173) fixes width to `640`.
- [server.py:174](/C:/VISSION_ASSIST/server.py#L174) fixes height to `480`.
- [server.py:175](/C:/VISSION_ASSIST/server.py#L175) validates that the camera opened successfully.
- [server.py:176](/C:/VISSION_ASSIST/server.py#L176) notifies the frontend if camera access fails.
- [server.py:177](/C:/VISSION_ASSIST/server.py#L177) stops voice on failure.
- [server.py:181](/C:/VISSION_ASSIST/server.py#L181) resets alert timing for a fresh session.
- [server.py:182](/C:/VISSION_ASSIST/server.py#L182) creates the duplicate-alert guard.
- [server.py:183](/C:/VISSION_ASSIST/server.py#L183) scales repeat suppression based on `alert_delay`.
- [server.py:185](/C:/VISSION_ASSIST/server.py#L185) announces that processing has started.
- [server.py:187](/C:/VISSION_ASSIST/server.py#L187) creates an FPS rolling buffer.
- [server.py:188](/C:/VISSION_ASSIST/server.py#L188) saves the previous timestamp for FPS calculation.
- [server.py:190](/C:/VISSION_ASSIST/server.py#L190) maps navigation urgencies to voice priorities.
