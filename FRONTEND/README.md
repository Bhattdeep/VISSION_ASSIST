# AI Vision Assist — React Frontend

A production-grade React 18 + Vite + Tailwind CSS dashboard for the
Vision Assist pipeline. Connects to the Python FastAPI backend via WebSocket.

## Project Structure

```
vision-assist-ui/
├── index.html                      ← Vite entry point
├── package.json
├── vite.config.js                  ← proxies /ws → ws://localhost:8000
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.jsx                    ← ReactDOM.createRoot
    ├── App.jsx                     ← root component, all state lives here
    ├── styles/
    │   └── globals.css             ← Tailwind + custom HUD CSS variables
    ├── hooks/
    │   └── useWebSocket.js         ← auto-reconnecting WebSocket hook
    └── components/
        ├── Header.jsx              ← logo, mode selector, start/stop
        ├── VideoPanel.jsx          ← live MJPEG feed with HUD overlays
        ├── AlertBanner.jsx         ← critical / warning / info / none badge
        ├── DetectionPanel.jsx      ← per-object rows with proximity bars
        ├── SonarPanel.jsx          ← animated radar + distance readout
        ├── AssistantPanel.jsx      ← Claude AI chat with API key input
        ├── SettingsPanel.jsx       ← sliders, toggles, sensor config
        ├── LogPanel.jsx            ← colour-coded alert history
        └── StatusBar.jsx           ← FPS, device, depth, mode, sonar chips
```

## Quick Start

### 1. Start the Python backend

```powershell
cd C:\vis-assist
env\Scripts\activate
python server.py
```

### 2. Install frontend dependencies

```powershell
cd vision-assist-ui
npm install
```

### 3. Start the dev server

```powershell
npm run dev
```

Open **http://localhost:5173** in your browser.

### 4. Build for production

```powershell
npm run build
# Output goes to dist/
# Python server can serve it statically
```

## WebSocket Protocol

All communication goes over `ws://localhost:8000/ws`.

### Server → Client

| `type`        | Payload                                                    |
|---------------|------------------------------------------------------------|
| `frame`       | `data: <base64-jpeg>`                                      |
| `detections`  | `data: [{name, conf, depth, pos, area}]`                   |
| `alert`       | `message: string, urgency: "critical"│"warning"│"info"`   |
| `stats`       | `fps, device, depth_ready, mode, sensor_on`                |
| `distance`    | `cm: float, zone: "danger"│"warning"│"caution"│"safe"`     |
| `assistant`   | `answer: string`                                           |
| `status`      | `running: bool`                                            |
| `error`       | `message: string`                                          |

### Client → Server

| `type`          | Payload                                               |
|-----------------|-------------------------------------------------------|
| `start`         | `mode, confidence, alert_delay, voice_enabled, ...`  |
| `stop`          | _(none)_                                              |
| `settings`      | any subset of config keys                             |
| `depth_overlay` | `enabled: bool`                                       |
| `ask`           | `question: string, api_key: string`                   |

## Design System

The UI uses a **tactical HUD** aesthetic:
- Font: **Share Tech Mono** (labels) + **Rajdhani** (display) + **Exo 2** (body)
- Palette: deep navy backgrounds, cyan/green/amber/red accents with glow
- Corner bracket panels via CSS `::before`/`::after`
- Animated radar sweep, scan-line overlay, pulsing alert dots
