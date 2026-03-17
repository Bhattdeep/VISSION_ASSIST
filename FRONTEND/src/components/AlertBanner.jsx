import React from 'react'

const URGENCY_CONFIG = {
  critical: {
    label:       'CRITICAL — STOP IMMEDIATELY',
    dotClass:    'bg-red animate-pulse-fast',
    dotGlow:     '#FF2D55',
    textColor:   'text-red',
    borderColor: 'border-red',
    bgColor:     'bg-red/5',
  },
  warning: {
    label:       'WARNING — PROCEED WITH CAUTION',
    dotClass:    'bg-amber animate-pulse-slow',
    dotGlow:     '#FFB300',
    textColor:   'text-amber',
    borderColor: 'border-amber',
    bgColor:     'bg-amber/5',
  },
  info: {
    label:       'NOTICE — OBJECT NEARBY',
    dotClass:    'bg-blue',
    dotGlow:     '#3D8EFF',
    textColor:   'text-blue',
    borderColor: 'border-blue',
    bgColor:     'bg-blue/5',
  },
  none: {
    label:       'NO ALERT — PATH CLEAR',
    dotClass:    'bg-txt3',
    dotGlow:     'transparent',
    textColor:   'text-txt3',
    borderColor: 'border-border',
    bgColor:     'bg-transparent',
  },
}

export default function AlertBanner({ alert }) {
  const urgency = alert?.urgency || 'none'
  const cfg = URGENCY_CONFIG[urgency] || URGENCY_CONFIG.none

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 rounded-sm border
                  ${cfg.borderColor} ${cfg.bgColor} ${cfg.textColor}
                  ${alert?.urgency ? 'animate-alert-pop' : ''}`}
    >
      {/* Pulsing dot */}
      <div
        className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dotClass}`}
        style={{ boxShadow: `0 0 8px ${cfg.dotGlow}` }}
      />

      <div className="flex-1 min-w-0">
        <div className="font-mono text-[8px] tracking-[2px] opacity-60 mb-0.5">
          {cfg.label}
        </div>
        <div className="font-body text-[13px] font-light tracking-wide truncate">
          {alert?.message || 'System nominal. Area is clear.'}
        </div>
      </div>

      {/* Urgency badge */}
      {urgency !== 'none' && (
        <div
          className={`font-mono text-[9px] tracking-[2px] px-2 py-1 border rounded-sm
                      flex-shrink-0 ${cfg.borderColor}`}
        >
          {urgency.toUpperCase()}
        </div>
      )}
    </div>
  )
}
