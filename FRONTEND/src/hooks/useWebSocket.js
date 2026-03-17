import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = `ws://${window.location.host}/ws`

export function useWebSocket(onMessage) {
  const wsRef     = useRef(null)
  const [connected, setConnected] = useState(false)

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    let reconnectTimer = null

    const connect = () => {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setConnected(true)
        clearTimeout(reconnectTimer)
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer = setTimeout(connect, 2000)
      }

      ws.onerror = () => ws.close()

      ws.onmessage = (e) => {
        try {
          onMessage(JSON.parse(e.data))
        } catch (err) {
          console.error('[WS] Parse error:', err)
        }
      }

      wsRef.current = ws
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])  // eslint-disable-line

  return { send, connected }
}
