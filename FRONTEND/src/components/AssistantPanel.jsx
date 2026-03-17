import React, { useState, useRef, useEffect } from 'react'

function ChatBubble({ msg }) {
  const isUser = msg.role === 'user'
  const isErr  = msg.role === 'error'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}>
      <div
        className="max-w-[85%] px-3 py-2 rounded-sm text-[12px] leading-relaxed font-light"
        style={{
          background: isErr  ? 'rgba(255,45,85,0.06)'
                    : isUser ? 'rgba(0,240,255,0.06)'
                    : 'rgba(0,255,136,0.06)',
          borderLeft: `2px solid ${isErr ? '#FF2D55' : isUser ? '#00B8CC' : '#00FF88'}`,
          color: isErr ? '#FF2D55' : '#C8E8F8',
        }}
      >
        {!isUser && (
          <div className="font-mono text-[8px] tracking-[2px] mb-1.5 opacity-60"
            style={{ color: isErr ? '#FF2D55' : '#00FF88' }}>
            {isErr ? 'SYSTEM ERROR' : 'AI ASSISTANT'}
          </div>
        )}
        {msg.text}
      </div>
    </div>
  )
}

export default function AssistantPanel({ onAsk, messages, busy }) {
  const [question, setQuestion] = useState('')
  const [apiKey,   setApiKey]   = useState('')
  const [showKey,  setShowKey]  = useState(false)
  const chatEndRef = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const handleSend = () => {
    if (!question.trim() || !apiKey.trim() || busy) return
    onAsk(question.trim(), apiKey.trim())
    setQuestion('')
  }

  const suggestions = [
    'What is in front of me?',
    'Is it safe to walk forward?',
    'Describe my surroundings.',
    'How far is the nearest object?',
  ]

  return (
    <div className="hud-panel flex flex-col min-h-0 h-full">
      <div className="panel-label">AI ASSISTANT</div>

      {/* API Key */}
      <div className="flex gap-2 p-2 border-b border-border">
        <input
          type={showKey ? 'text' : 'password'}
          className="hud-input flex-1 text-[10px]"
          placeholder="Anthropic API key  sk-ant-..."
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <button
          className="hud-btn hud-btn-cyan text-[9px] px-2.5 py-1 whitespace-nowrap"
          onClick={() => setShowKey((s) => !s)}
        >
          {showKey ? 'HIDE' : 'SHOW'}
        </button>
      </div>

      {/* Chat log */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="font-mono text-[9px] tracking-[2px] text-txt3 text-center">
              ASK ABOUT YOUR ENVIRONMENT
            </div>
            <div className="flex flex-col gap-1.5 w-full">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setQuestion(s)}
                  className="text-left text-[10px] font-light text-txt3 px-3 py-1.5
                             border border-border rounded-sm hover:border-cyan/40
                             hover:text-txt2 transition-all duration-150"
                >
                  "{s}"
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => <ChatBubble key={i} msg={m} />)}

        {busy && (
          <div className="flex justify-start animate-fade-in">
            <div className="px-3 py-2 bg-green/5 border-l-2 border-green rounded-sm">
              <div className="font-mono text-[8px] tracking-[2px] text-green/60 mb-1">
                AI ASSISTANT
              </div>
              <div className="flex gap-1 items-center">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-green animate-pulse-slow"
                    style={{
                      animationDelay: `${i * 0.2}s`,
                      boxShadow: '0 0 6px #00FF88',
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2 p-2 border-t border-border">
        <input
          type="text"
          className="hud-input flex-1 text-[10px]"
          placeholder='e.g. "What is in front of me?"'
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <button
          className="hud-btn hud-btn-cyan text-[9px] px-3 whitespace-nowrap
                     disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={handleSend}
          disabled={busy || !question.trim() || !apiKey.trim()}
        >
          ASK
        </button>
      </div>
    </div>
  )
}
