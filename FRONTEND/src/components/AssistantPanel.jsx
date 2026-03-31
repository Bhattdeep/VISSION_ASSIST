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
  const [listening, setListening] = useState(false)
  const [speechState, setSpeechState] = useState('')
  const [handsFree, setHandsFree] = useState(false)
  const chatEndRef = useRef(null)
  const recognitionRef = useRef(null)
  const onAskRef = useRef(onAsk)
  const apiKeyRef = useRef(apiKey)
  const busyRef = useRef(busy)
  const autoListenTimerRef = useRef(null)
  const lastAutoReplyRef = useRef(null)
  const RecognitionCtor = typeof window !== 'undefined'
    ? (window.SpeechRecognition || window.webkitSpeechRecognition || null)
    : null

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  useEffect(() => {
    onAskRef.current = onAsk
  }, [onAsk])

  useEffect(() => {
    apiKeyRef.current = apiKey
  }, [apiKey])

  useEffect(() => {
    busyRef.current = busy
  }, [busy])

  useEffect(() => () => {
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
      autoListenTimerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!RecognitionCtor) return undefined

    const recognition = new RecognitionCtor()
    recognition.lang = 'en-US'
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      setListening(true)
      setSpeechState('Listening… speak your question now.')
    }

    recognition.onresult = (event) => {
      let transcript = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        transcript += event.results[i][0].transcript
      }
      setQuestion(transcript.trim())

      const lastResult = event.results[event.results.length - 1]
      if (lastResult?.isFinal) {
        const finalText = transcript.trim()
        if (finalText && !busyRef.current) {
          setSpeechState(`Heard: "${finalText}"`)
          onAskRef.current(finalText, apiKeyRef.current.trim())
          setQuestion('')
        }
      }
    }

    recognition.onerror = (event) => {
      setListening(false)
      setSpeechState(`Microphone error: ${event.error}`)
    }

    recognition.onend = () => {
      setListening(false)
      setSpeechState((prev) => prev || 'Ready for voice input.')
    }

    recognitionRef.current = recognition
    return () => {
      recognitionRef.current?.stop()
      recognitionRef.current = null
    }
  }, [RecognitionCtor])

  useEffect(() => {
    if (!handsFree || listening || busy || !RecognitionCtor) return
    if (messages.length === 0) return

    const lastMsg = messages[messages.length - 1]
    if (!lastMsg || (lastMsg.role !== 'ai' && lastMsg.role !== 'error')) return

    const key = `${messages.length}:${lastMsg.role}:${lastMsg.text}`
    if (lastAutoReplyRef.current === key) return
    lastAutoReplyRef.current = key

    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
    }
    autoListenTimerRef.current = setTimeout(() => {
      if (!busyRef.current && !listening) {
        try {
          recognitionRef.current?.start()
        } catch (err) {
          setSpeechState('Could not restart voice input automatically. Press MIC to continue.')
        }
      }
    }, 1400)
  }, [messages, handsFree, listening, busy, RecognitionCtor])

  useEffect(() => {
    if (!handsFree || listening || busy || !RecognitionCtor) return
    if (messages.length !== 0) return

    setSpeechState('Hands-free mode on. Listening will start automatically.')
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
    }
    autoListenTimerRef.current = setTimeout(() => {
      if (!busyRef.current && !listening) {
        try {
          recognitionRef.current?.start()
        } catch (err) {
          setSpeechState('Press MIC to begin voice input.')
        }
      }
    }, 800)
  }, [handsFree, listening, busy, RecognitionCtor, messages.length])

  useEffect(() => {
    if (handsFree) return
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
      autoListenTimerRef.current = null
    }
  }, [handsFree])

  const handleSend = () => {
    if (!question.trim() || busy) return
    onAsk(question.trim(), apiKey.trim())
    setQuestion('')
  }

  const handleMic = () => {
    if (!RecognitionCtor) {
      setSpeechState('Browser speech recognition is not available here. Use Chrome or Edge.')
      return
    }
    if (busy) return

    if (listening) {
      recognitionRef.current?.stop()
      return
    }

    setSpeechState('')
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current)
      autoListenTimerRef.current = null
    }
    recognitionRef.current?.start()
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
          placeholder="Gemini API key from Google AI Studio (optional if set on server)"
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
      <div className="px-3 pb-2 font-mono text-[8px] text-txt3 border-b border-border">
        Uses Gemini free-tier friendly requests. You can paste a key here or set `GEMINI_API_KEY` on the server.
      </div>
      <div className="px-3 py-2 font-mono text-[8px] text-txt3 border-b border-border">
        {speechState || (RecognitionCtor ? 'Press MIC to ask by voice.' : 'Voice input is available in browsers with the Web Speech API.')}
      </div>
      <div className="px-3 py-2 border-b border-border">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={handsFree}
            onChange={(e) => setHandsFree(e.target.checked)}
          />
          <span className="font-mono text-[9px] text-txt2">
            Hands-free follow-up mode
          </span>
        </label>
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
          className={`hud-btn text-[9px] px-3 whitespace-nowrap ${
            listening ? 'hud-btn-cyan' : 'hud-btn-cyan'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
          onClick={handleMic}
          disabled={busy}
        >
          {listening ? 'STOP' : 'MIC'}
        </button>
        <button
          className="hud-btn hud-btn-cyan text-[9px] px-3 whitespace-nowrap
                     disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={handleSend}
          disabled={busy || !question.trim()}
        >
          ASK
        </button>
      </div>
    </div>
  )
}
