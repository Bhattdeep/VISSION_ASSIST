import React from 'react'

export default function Header({ connected, running, mode, onModeChange, onToggle }) {
  return (
    <header className="flex items-center gap-4 px-4 py-2 bg-bg1 border-b border-border flex-shrink-0 z-10">

      {/* Logo */}
      <div className="flex items-center gap-3">
        <svg width="30" height="30" viewBox="0 0 30 30" fill="none">
          <circle cx="15" cy="15" r="14" stroke="#00F0FF" strokeWidth="1.5" strokeOpacity="0.4" />
          <circle cx="15" cy="15" r="6"  stroke="#00F0FF" strokeWidth="1.5" />
          <line x1="15" y1="1"  x2="15" y2="9"  stroke="#00F0FF" strokeWidth="1.5" strokeOpacity="0.6" />
          <line x1="15" y1="21" x2="15" y2="29" stroke="#00F0FF" strokeWidth="1.5" strokeOpacity="0.6" />
          <line x1="1"  y1="15" x2="9"  y2="15" stroke="#00F0FF" strokeWidth="1.5" strokeOpacity="0.6" />
          <line x1="21" y1="15" x2="29" y2="15" stroke="#00F0FF" strokeWidth="1.5" strokeOpacity="0.6" />
          <circle cx="15" cy="15" r="2.5" fill="#00F0FF"
            style={{ filter: 'drop-shadow(0 0 5px #00F0FF)' }} />
        </svg>
        <div>
          <h1 className="font-display font-bold text-lg text-cyan leading-none tracking-[3px]"
            style={{ textShadow: '0 0 20px rgba(0,240,255,0.5)' }}>
            AI VISION ASSIST
          </h1>
          <p className="font-mono text-[8px] text-txt3 tracking-[2px] mt-0.5">
            OBSTACLE DETECTION · DEPTH SENSING · AI GUIDANCE
          </p>
        </div>
      </div>

      <div className="flex-1" />

      {/* Connection indicator */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full transition-colors duration-300 ${
            connected ? 'bg-green' : 'bg-red animate-pulse-fast'
          }`}
          style={{
            boxShadow: connected ? '0 0 8px #00FF88' : '0 0 8px #FF2D55',
          }}
        />
        <span className="font-mono text-[9px] text-txt2 tracking-widest">
          {connected ? 'LINKED' : 'OFFLINE'}
        </span>
      </div>

      {/* Mode selector */}
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9px] text-txt3 tracking-[2px]">MODE</span>
        <select
          value={mode}
          onChange={(e) => onModeChange(e.target.value)}
          disabled={running}
          className="text-[10px] w-44 disabled:opacity-50"
        >
          <option value="basic">BASIC  (no depth)</option>
          <option value="upgraded">UPGRADED  (depth + GPU)</option>
        </select>
      </div>

      {/* Start / Stop */}
      <button
        onClick={onToggle}
        disabled={!connected}
        className={`hud-btn min-w-[110px] text-center disabled:opacity-40 ${
          running ? 'hud-btn-red' : 'hud-btn-green'
        }`}
      >
        {running ? '■  STOP' : '▶  START'}
      </button>
    </header>
  )
}
