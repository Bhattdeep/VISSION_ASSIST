import React from 'react'

const POS_COLORS = {
  left:   '#3D8EFF',
  center: '#00F0FF',
  right:  '#3D8EFF',
}

function DetectionRow({ det, index }) {
  const distanceCm = typeof det.distance_cm === 'number' ? det.distance_cm : null
  const depthPct = distanceCm != null
    ? Math.max(0, Math.min(100, Math.round(100 - Math.min(distanceCm, 400) / 4)))
    : det.depth > 0
      ? Math.round(det.depth * 100)
      : Math.min(100, Math.round((det.area || 0) / 1200))

  const clamped = Math.min(100, Math.max(0, depthPct))

  const barColor = distanceCm != null
                 ? distanceCm <= 120 ? '#FF2D55'
                   : distanceCm <= 220 ? '#FFB300'
                   : '#00FF88'
                 : clamped >= 70 ? '#FF2D55'
                 : clamped >= 50 ? '#FFB300'
                 : '#00FF88'

  const posColor = POS_COLORS[det.pos] || '#5A8AAA'

  return (
    <div
      className="flex items-center gap-2 px-2 py-1.5 bg-bg border border-border
                 rounded-sm animate-fade-in"
      style={{
        borderLeft: `2px solid ${barColor}`,
        animationDelay: `${index * 0.04}s`,
      }}
    >
      {/* Object name */}
      <div className="w-20 flex-shrink-0">
        <div className="font-mono text-[11px] text-txt capitalize">{det.name}</div>
        <div className="font-mono text-[8px] text-txt3 mt-0.5">
          {(det.conf * 100).toFixed(0)}% CONF
        </div>
      </div>

      {/* Proximity bar */}
      <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${clamped}%`,
            background: `linear-gradient(90deg, ${barColor}88, ${barColor})`,
            boxShadow: `0 0 4px ${barColor}66`,
          }}
        />
      </div>

      {/* Depth value */}
      <div
        className="font-mono text-[10px] w-14 text-right flex-shrink-0"
        style={{ color: barColor }}
      >
        {distanceCm != null ? `${Math.round(distanceCm)}cm` : det.depth > 0 ? det.depth.toFixed(2) : '---'}
      </div>

      {/* Position */}
      <div
        className="font-mono text-[9px] w-10 text-center flex-shrink-0 tracking-wide"
        style={{ color: posColor }}
      >
        {det.pos?.toUpperCase() || '---'}
      </div>
    </div>
  )
}

export default function DetectionPanel({ detections }) {
  return (
    <div className="hud-panel flex flex-col min-h-0 h-full">
      <div className="panel-label">
        DETECTIONS
        <span className="ml-auto font-mono text-[9px] text-txt2">
          {detections.length} OBJECT{detections.length !== 1 ? 'S' : ''}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
        {detections.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-6">
            <div className="font-mono text-[28px] text-txt3 opacity-20">◎</div>
            <div className="font-mono text-[9px] tracking-[3px] text-txt3">
              NO OBJECTS DETECTED
            </div>
          </div>
        ) : (
          detections.map((det, i) => (
            <DetectionRow key={`${det.name}-${i}`} det={det} index={i} />
          ))
        )}
      </div>
    </div>
  )
}
