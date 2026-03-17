import React, { useRef, useEffect } from 'react'

const TYPE_COLORS = {
  critical: '#FF2D55',
  warning:  '#FFB300',
  info:     '#3D8EFF',
  error:    '#FF2D55',
}

const TYPE_BADGES = {
  critical: 'CRIT',
  warning:  'WARN',
  info:     'INFO',
  error:    'ERR ',
}

export default function LogPanel({ entries, onClear }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries])

  return (
    <div className="hud-panel flex flex-col min-h-0 h-full">
      <div className="panel-label">
        ALERT LOG
        <span className="ml-auto font-mono text-[9px] text-txt2">
          {entries.length} ENTRIES
        </span>
        <button
          onClick={onClear}
          className="hud-btn hud-btn-cyan text-[8px] px-2 py-0.5 ml-2"
        >
          CLEAR
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 font-mono text-[9px] flex flex-col gap-1">
        {entries.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="tracking-[2px] text-txt3">NO EVENTS LOGGED</div>
          </div>
        ) : (
          entries.map((e, i) => (
            <div
              key={i}
              className="flex gap-2 items-baseline leading-relaxed animate-fade-in"
            >
              <span className="text-txt3 flex-shrink-0 w-[54px]">{e.time}</span>
              <span
                className="flex-shrink-0 w-10 tracking-wide"
                style={{ color: TYPE_COLORS[e.type] || '#5A8AAA' }}
              >
                {TYPE_BADGES[e.type] || e.type?.toUpperCase().slice(0, 4) || '----'}
              </span>
              <span className="text-txt leading-relaxed">{e.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
