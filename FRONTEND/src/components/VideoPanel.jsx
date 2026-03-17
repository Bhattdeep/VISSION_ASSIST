import React from 'react'

function StatChip({ label, value, color }) {
  return (
    <div className="flex flex-col items-end">
      <span className="font-mono text-[7px] text-txt3 tracking-[2px]">{label}</span>
      <span
        className="font-mono text-[11px] leading-tight"
        style={{ color, textShadow: `0 0 8px ${color}` }}
      >
        {typeof value === 'number' && value % 1 !== 0 ? value.toFixed(1) : value ?? '--'}
      </span>
    </div>
  )
}

export default function VideoPanel({ frame, running, fps, device, depthReady, mode }) {
  return (
    <div className="hud-panel flex flex-col flex-1 min-h-0 overflow-hidden">
      {/* Label row */}
      <div className="panel-label">
        VISUAL FEED
        <div className="ml-auto flex items-center gap-5">
          <StatChip
            label="FPS"
            value={fps}
            color={fps > 15 ? '#00FF88' : fps > 8 ? '#FFB300' : '#FF2D55'}
          />
          <StatChip label="DEVICE" value={device} color="#00F0FF" />
          <StatChip
            label="DEPTH"
            value={depthReady ? 'ON' : 'OFF'}
            color={depthReady ? '#00FF88' : '#2A4A60'}
          />
        </div>
      </div>

      {/* Video area */}
      <div className="relative flex-1 bg-black overflow-hidden">
        {frame ? (
          <>
            <img
              src={`data:image/jpeg;base64,${frame}`}
              alt="Live feed"
              className="w-full h-full object-contain"
            />
            {/* Animated scan line */}
            <div
              className="absolute left-0 right-0 h-px pointer-events-none animate-scan-line"
              style={{
                background: 'linear-gradient(90deg, transparent, #00F0FF, transparent)',
                opacity: 0.6,
              }}
            />
            {/* Mode badge */}
            <div className="absolute top-2 left-1/2 -translate-x-1/2 font-mono text-[9px]
                            tracking-[2px] text-cyan opacity-70"
              style={{ textShadow: '0 0 8px #00F0FF' }}>
              {mode?.toUpperCase()} · LIVE
            </div>
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
            <div className="text-4xl opacity-20 font-mono text-cyan">◉</div>
            <div className="font-mono text-[10px] tracking-[3px] text-txt3">
              {running ? 'INITIALIZING PIPELINE…' : 'PRESS START TO BEGIN'}
            </div>
            {running && (
              <div className="flex gap-1.5 mt-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-cyan animate-pulse-slow"
                    style={{ animationDelay: `${i * 0.2}s`, boxShadow: '0 0 6px #00F0FF' }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Corner brackets */}
        {['tl', 'tr', 'bl', 'br'].map((pos) => (
          <div
            key={pos}
            className="absolute w-5 h-5 opacity-60"
            style={{
              ...(pos.includes('t') ? { top: 8 } : { bottom: 8 }),
              ...(pos.includes('l') ? { left: 8 } : { right: 8 }),
              borderColor: '#00F0FF',
              borderStyle: 'solid',
              borderWidth: pos === 'tl' ? '2px 0 0 2px'
                         : pos === 'tr' ? '2px 2px 0 0'
                         : pos === 'bl' ? '0 0 2px 2px'
                         : '0 2px 2px 0',
            }}
          />
        ))}
      </div>
    </div>
  )
}
