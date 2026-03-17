import React from 'react'

function Chip({ label, value, color }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-mono text-[8px] text-txt3 tracking-[2px]">{label}</span>
      <span
        className="font-mono text-[10px]"
        style={{ color, textShadow: `0 0 6px ${color}` }}
      >
        {value ?? '--'}
      </span>
    </div>
  )
}

export default function StatusBar({ fps, device, depthReady, mode, sensorOn, running }) {
  return (
    <div className="flex items-center gap-5 px-4 py-1.5 bg-bg1 border-t border-border flex-shrink-0">
      <Chip
        label="FPS"
        value={fps != null ? fps.toFixed(1) : '--'}
        color={fps > 15 ? '#00FF88' : fps > 8 ? '#FFB300' : '#FF2D55'}
      />
      <Chip label="DEVICE" value={device || '--'} color="#00F0FF" />
      <Chip
        label="DEPTH"
        value={depthReady ? 'ACTIVE' : 'OFF'}
        color={depthReady ? '#00FF88' : '#2A4A60'}
      />
      <Chip
        label="MODE"
        value={mode?.toUpperCase() || '--'}
        color="#00F0FF"
      />
      <Chip
        label="SONAR"
        value={sensorOn ? 'ACTIVE' : 'OFF'}
        color={sensorOn ? '#00FF88' : '#2A4A60'}
      />
      <Chip
        label="STATUS"
        value={running ? 'RUNNING' : 'IDLE'}
        color={running ? '#00FF88' : '#2A4A60'}
      />

      <div className="flex-1" />

      <span className="font-mono text-[8px] text-txt3 tracking-[2px]">
        AI VISION ASSIST  v3.0
      </span>
    </div>
  )
}
