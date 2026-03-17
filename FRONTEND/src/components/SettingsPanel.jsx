import React from 'react'

function Toggle({ label, value, onChange, description }) {
  return (
    <div
      className="flex items-center gap-3 cursor-pointer group"
      onClick={() => onChange(!value)}
    >
      <div className={`hud-toggle ${value ? 'on' : 'off'}`} />
      <div>
        <div className={`font-mono text-[9px] tracking-[1.5px] transition-colors duration-150
                         ${value ? 'text-txt' : 'text-txt3'} group-hover:text-txt2`}>
          {label}
        </div>
        {description && (
          <div className="font-mono text-[8px] text-txt3 mt-0.5">{description}</div>
        )}
      </div>
    </div>
  )
}

function SliderRow({ label, value, displayValue, min, max, onChange }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="font-mono text-[9px] tracking-[2px] text-txt3">{label}</span>
        <span className="font-mono text-[11px] text-cyan"
          style={{ textShadow: '0 0 8px #00F0FF' }}>
          {displayValue}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}

export default function SettingsPanel({
  config, onChange, onDepthToggle, depthOn,
}) {
  return (
    <div className="hud-panel flex flex-col h-full overflow-y-auto">
      <div className="panel-label">CONFIGURATION</div>

      <div className="p-3 flex flex-col gap-5">

        {/* Detection */}
        <section>
          <div className="font-mono text-[8px] tracking-[3px] text-cyan2 mb-3">
            DETECTION SETTINGS
          </div>
          <div className="flex flex-col gap-4">
            <SliderRow
              label="CONFIDENCE THRESHOLD"
              value={Math.round(config.confidence * 100)}
              displayValue={`${Math.round(config.confidence * 100)}%`}
              min={30} max={95}
              onChange={(v) => onChange({ confidence: v / 100 })}
            />
            <SliderRow
              label="ALERT INTERVAL"
              value={Math.round(config.alert_delay * 10)}
              displayValue={`${config.alert_delay?.toFixed(1)}s`}
              min={5} max={80}
              onChange={(v) => onChange({ alert_delay: v / 10 })}
            />
          </div>
        </section>

        <div className="h-px bg-border" />

        {/* Display */}
        <section>
          <div className="font-mono text-[8px] tracking-[3px] text-cyan2 mb-3">
            DISPLAY OPTIONS
          </div>
          <div className="flex flex-col gap-3">
            <Toggle
              label="VOICE ALERTS"
              value={config.voice_enabled}
              onChange={(v) => onChange({ voice_enabled: v })}
              description="Speak obstacle warnings aloud"
            />
            <Toggle
              label="DEPTH HEATMAP OVERLAY"
              value={depthOn}
              onChange={onDepthToggle}
              description="Show MiDaS depth map on video"
            />
          </div>
        </section>

        <div className="h-px bg-border" />

        {/* Ultrasonic */}
        <section>
          <div className="font-mono text-[8px] tracking-[3px] text-cyan2 mb-3">
            ULTRASONIC SENSOR
          </div>
          <div className="flex flex-col gap-3">
            <Toggle
              label="ENABLE SENSOR"
              value={config.ultrasonic_enabled}
              onChange={(v) => onChange({ ultrasonic_enabled: v })}
              description="HC-SR04 via Arduino serial"
            />

            {config.ultrasonic_enabled && (
              <div className="animate-fade-in flex flex-col gap-2 pl-2 border-l border-border">
                <div>
                  <div className="font-mono text-[8px] tracking-[2px] text-txt3 mb-1">
                    COM PORT
                  </div>
                  <input
                    type="text"
                    className="hud-input text-[10px]"
                    placeholder="COM3 or /dev/ttyUSB0"
                    value={config.ultrasonic_port || 'COM3'}
                    onChange={(e) => onChange({ ultrasonic_port: e.target.value })}
                  />
                </div>
                <div className="font-mono text-[8px] text-txt3 leading-relaxed">
                  Upload arduino/vis_assist_ultrasonic.ino to your board first.
                </div>
              </div>
            )}
          </div>
        </section>

        <div className="h-px bg-border" />

        {/* Info */}
        <section className="font-mono text-[8px] text-txt3 leading-relaxed">
          <div className="tracking-[2px] text-cyan2 mb-2">SYSTEM INFO</div>
          <div>Backend: ws://localhost:8000</div>
          <div>Frontend: Vite + React 18 + Tailwind CSS</div>
          <div className="mt-1 text-[7px] tracking-[1px] opacity-60">
            AI Vision Assist v3.0
          </div>
        </section>
      </div>
    </div>
  )
}
