import React, { useState, useCallback } from 'react'
import { useWebSocket }    from './hooks/useWebSocket'
import Header              from './components/Header'
import VideoPanel          from './components/VideoPanel'
import AlertBanner         from './components/AlertBanner'
import DetectionPanel      from './components/DetectionPanel'
import SonarPanel          from './components/SonarPanel'
import AssistantPanel      from './components/AssistantPanel'
import SettingsPanel       from './components/SettingsPanel'
import LogPanel            from './components/LogPanel'
import StatusBar           from './components/StatusBar'

const TABS = [
  { id: 'detect',  label: '🎯  DETECT' },
  { id: 'sonar',   label: '📡  SONAR'  },
  { id: 'assist',  label: '🤖  ASSIST' },
  { id: 'config',  label: '⚙  CONFIG' },
  { id: 'log',     label: '📋  LOG'    },
]

export default function App() {
  // ── Pipeline state ────────────────────────────────────────────────
  const [frame,      setFrame]      = useState(null)
  const [detections, setDetections] = useState([])
  const [alert,      setAlert]      = useState(null)
  const [distance,   setDistance]   = useState(null)
  const [distZone,   setDistZone]   = useState(null)
  const [stats,      setStats]      = useState({})
  const [running,    setRunning]    = useState(false)

  // ── UI state ──────────────────────────────────────────────────────
  const [mode,       setMode]       = useState('basic')
  const [depthOn,    setDepthOn]    = useState(false)
  const [activeTab,  setActiveTab]  = useState('detect')
  const [chatMsgs,   setChatMsgs]   = useState([])
  const [aiBusy,     setAiBusy]     = useState(false)
  const [logEntries, setLogEntries] = useState([])

  const [config, setConfig] = useState({
    confidence:          0.60,
    alert_delay:         1.5,
    voice_enabled:       true,
    ultrasonic_enabled:  false,
    ultrasonic_port:     'COM3',
    ultrasonic_baud:     9600,
  })

  // ── Helpers ───────────────────────────────────────────────────────
  const addLog = useCallback((type, message) => {
    const time = new Date().toLocaleTimeString('en', { hour12: false })
    setLogEntries((prev) => [...prev.slice(-300), { type, message, time }])
  }, [])

  // ── WebSocket message handler ─────────────────────────────────────
  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'frame':
        setFrame(msg.data)
        break

      case 'detections':
        setDetections(msg.data)
        break

      case 'alert':
        setAlert({ message: msg.message, urgency: msg.urgency })
        addLog(msg.urgency, msg.message)
        setTimeout(() => setAlert(null), 4500)
        break

      case 'stats':
        setStats(msg)
        break

      case 'distance':
        setDistance(msg.cm)
        setDistZone(msg.zone)
        break

      case 'status':
        setRunning(msg.running)
        if (!msg.running) {
          setFrame(null)
          setDetections([])
          setDistance(null)
          setDistZone(null)
          setStats({})
        }
        break

      case 'assistant':
        setChatMsgs((p) => [...p, { role: 'ai', text: msg.answer }])
        setAiBusy(false)
        break

      case 'error':
        addLog('error', msg.message)
        setChatMsgs((p) => [...p, { role: 'error', text: msg.message }])
        setAiBusy(false)
        break

      default:
        break
    }
  }, [addLog])

  const { send, connected } = useWebSocket(handleMessage)

  // ── Handlers ──────────────────────────────────────────────────────
  const handleToggle = () => {
    if (running) {
      send({ type: 'stop' })
    } else {
      send({ type: 'start', mode, ...config })
    }
  }

  const handleSettings = (updates) => {
    const next = { ...config, ...updates }
    setConfig(next)
    if (running) send({ type: 'settings', ...next })
  }

  const handleDepthToggle = (val) => {
    setDepthOn(val)
    send({ type: 'depth_overlay', enabled: val })
  }

  const handleAsk = useCallback((question, apiKey) => {
    setChatMsgs((p) => [...p, { role: 'user', text: question }])
    setAiBusy(true)
    send({ type: 'ask', question, api_key: apiKey })
    setActiveTab('assist')
  }, [send])

  // ── Right panel content ───────────────────────────────────────────
  const renderPanel = () => {
    switch (activeTab) {
      case 'detect':
        return <DetectionPanel detections={detections} />
      case 'sonar':
        return <SonarPanel distance={distance} zone={distZone} />
      case 'assist':
        return <AssistantPanel onAsk={handleAsk} messages={chatMsgs} busy={aiBusy} />
      case 'config':
        return (
          <SettingsPanel
            config={config}
            onChange={handleSettings}
            onDepthToggle={handleDepthToggle}
            depthOn={depthOn}
          />
        )
      case 'log':
        return (
          <LogPanel
            entries={logEntries}
            onClear={() => setLogEntries([])}
          />
        )
      default:
        return null
    }
  }

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-bg">
      <Header
        connected={connected}
        running={running}
        mode={mode}
        onModeChange={setMode}
        onToggle={handleToggle}
      />

      {/* Body */}
      <div className="flex flex-1 gap-2 p-2 min-h-0 overflow-hidden">

        {/* Left — video + alert */}
        <div className="flex flex-col flex-1 gap-2 min-w-0">
          <AlertBanner alert={alert} />
          <VideoPanel
            frame={frame}
            running={running}
            fps={stats.fps}
            device={stats.device}
            depthReady={stats.depth_ready}
            mode={stats.mode}
          />
        </div>

        {/* Right — tabbed panels */}
        <div className="flex flex-col w-[340px] flex-shrink-0 min-h-0">
          {/* Tab bar */}
          <div className="flex bg-bg1 border border-border border-b-0 rounded-t-sm overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.id}
                className={`hud-tab ${activeTab === t.id ? 'active' : ''}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="flex-1 min-h-0 border border-border border-t-0 rounded-b-sm overflow-hidden">
            {renderPanel()}
          </div>
        </div>
      </div>

      <StatusBar
        fps={stats.fps}
        device={stats.device}
        depthReady={stats.depth_ready}
        mode={stats.mode}
        sensorOn={stats.sensor_on}
        running={running}
      />
    </div>
  )
}
