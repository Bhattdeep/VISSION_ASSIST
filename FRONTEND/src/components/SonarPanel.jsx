import React from 'react'

const ZONE_COLORS = {
  danger:  '#FF2D55',
  warning: '#FFB300',
  caution: '#3D8EFF',
  safe:    '#00FF88',
}

const ZONE_LABELS = {
  danger:  'DANGER',
  warning: 'CLOSE',
  caution: 'CAUTION',
  safe:    'SAFE',
}

export default function SonarPanel({ distance, zone }) {
  const color    = ZONE_COLORS[zone] || '#2A4A60'
  const label    = ZONE_LABELS[zone] || 'NO SIGNAL'
  const barWidth = distance != null
    ? Math.min(100, Math.max(0, 100 - (distance / 400) * 100))
    : 0

  return (
    <div className="hud-panel h-full flex flex-col">
      <div className="panel-label">SONAR / ULTRASONIC</div>

      <div className="flex-1 flex flex-col items-center justify-center gap-6 p-4">

        {/* Radar visualisation */}
        <div className="relative w-36 h-36">
          {/* Concentric circles */}
          {[1, 0.67, 0.33].map((scale, i) => (
            <div
              key={i}
              className="absolute inset-0 rounded-full border border-cyan/20"
              style={{ transform: `scale(${scale})` }}
            />
          ))}

          {/* Crosshair */}
          <div className="absolute inset-0">
            <div className="absolute top-1/2 left-0 right-0 h-px bg-cyan/15 -translate-y-px" />
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-cyan/15 -translate-x-px" />
          </div>

          {/* Sweep */}
          <div
            className="absolute inset-0 rounded-full animate-radar-sweep"
            style={{
              background: 'conic-gradient(from 0deg, rgba(0,240,255,0) 0deg, rgba(0,240,255,0.35) 60deg, rgba(0,240,255,0) 60deg)',
            }}
          />

          {/* Object dot */}
          {distance != null && (
            <div
              className="absolute rounded-full animate-pulse-fast"
              style={{
                width:  10,
                height: 10,
                background: color,
                boxShadow:  `0 0 10px ${color}`,
                top:  `${50 - (barWidth / 100) * 42}%`,
                left: '50%',
                transform: 'translate(-50%, -50%)',
              }}
            />
          )}

          {/* Center dot */}
          <div
            className="absolute top-1/2 left-1/2 w-2 h-2 rounded-full bg-cyan -translate-x-1/2 -translate-y-1/2"
            style={{ boxShadow: '0 0 8px #00F0FF' }}
          />
        </div>

        {/* Distance readout */}
        <div className="text-center w-full">
          <div
            className="font-mono font-normal leading-none"
            style={{
              fontSize: 48,
              color:       distance != null ? color : '#2A4A60',
              textShadow:  distance != null ? `0 0 20px ${color}` : 'none',
              transition:  'color 0.3s ease',
            }}
          >
            {distance != null ? Math.round(distance) : '---'}
            <span className="text-xl opacity-50 ml-1">cm</span>
          </div>

          {distance != null && (
            <div className="font-mono text-[11px] text-txt2 mt-1">
              {(distance / 30.48).toFixed(1)} ft
            </div>
          )}

          <div
            className="font-mono text-[9px] tracking-[3px] mt-3"
            style={{
              color,
              textShadow: `0 0 8px ${color}`,
            }}
          >
            {label}
          </div>
        </div>

        {/* Distance bar */}
        <div className="w-full">
          <div className="flex justify-between font-mono text-[8px] text-txt3 mb-1.5 tracking-wider">
            <span>NEAR</span>
            <span>FAR</span>
          </div>
          <div className="h-1.5 bg-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${barWidth}%`,
                background: `linear-gradient(90deg, ${color}66, ${color})`,
                boxShadow:  `0 0 6px ${color}`,
              }}
            />
          </div>
          {distance != null && (
            <div className="font-mono text-[8px] text-txt3 mt-1 text-center tracking-wider">
              {distance.toFixed(0)}cm / 400cm MAX RANGE
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
