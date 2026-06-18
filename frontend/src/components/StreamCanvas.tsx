import { useEffect, useRef, useState, useCallback } from 'react'

interface StreamInfo {
  worker_id:       number
  host:            string
  http_port:       number
  livestream_port: number
  signaling_url:   string
  ready_url:       string
}

interface Props {
  workerId: number
  className?: string
}

type Status = 'connecting' | 'live' | 'error'

/**
 * WebRTC stream viewer for Isaac Sim native streaming.
 * Connects to the Kit signaling WebSocket, exchanges SDP offer/answer,
 * then renders the incoming H.264 video track in a <video> element.
 */
export default function StreamCanvas({ workerId, className = '' }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const pcRef    = useRef<RTCPeerConnection | null>(null)
  const wsRef    = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<Status>('connecting')
  const [fps, setFps]       = useState(0)
  const [res, setRes]       = useState('')

  const stop = useCallback(() => {
    wsRef.current?.close()
    pcRef.current?.close()
    wsRef.current = null
    pcRef.current = null
  }, [])

  const connect = useCallback(async () => {
    stop()
    setStatus('connecting')

    let info: StreamInfo
    try {
      const r = await fetch(`/api/workers/${workerId}/stream`)
      if (!r.ok) throw new Error('no stream info')
      info = await r.json()
    } catch {
      setStatus('error')
      return
    }

    // Wait for Isaac Sim to be ready (poll up to 60 s)
    for (let i = 0; i < 60; i++) {
      try {
        const r = await fetch(info.ready_url)
        const j = await r.json()
        if (j.ready || j.status === 'ok') break
      } catch { /* not up yet */ }
      await new Promise(res => setTimeout(res, 1000))
    }

    const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
    pcRef.current = pc

    pc.ontrack = (ev) => {
      if (!videoRef.current) return
      videoRef.current.srcObject = ev.streams[0]
      setStatus('live')

      // FPS counter via requestVideoFrameCallback (if available)
      const vid = videoRef.current
      if ('requestVideoFrameCallback' in vid) {
        let count = 0, last = performance.now()
        const tick = () => {
          count++
          const now = performance.now()
          if (now - last >= 1000) {
            setFps(Math.round(count / ((now - last) / 1000)))
            setRes(`${vid.videoWidth}×${vid.videoHeight}`)
            count = 0; last = now
          }
          ;(vid as any).requestVideoFrameCallback(tick)
        }
        ;(vid as any).requestVideoFrameCallback(tick)
      }
    }

    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {
        setStatus('error')
      }
    }

    // Add transceiver: we only receive video from Isaac Sim
    pc.addTransceiver('video', { direction: 'recvonly' })

    const ws = new WebSocket(info.signaling_url)
    wsRef.current = ws

    ws.onerror = () => setStatus('error')
    ws.onclose = () => { if (status !== 'live') setStatus('error') }

    ws.onmessage = async (ev) => {
      let msg: any
      try { msg = JSON.parse(ev.data) } catch { return }

      if (msg.type === 'offer') {
        await pc.setRemoteDescription(new RTCSessionDescription(msg))
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        ws.send(JSON.stringify(pc.localDescription))
      } else if (msg.type === 'answer') {
        await pc.setRemoteDescription(new RTCSessionDescription(msg))
      } else if (msg.type === 'candidate' && msg.candidate) {
        await pc.addIceCandidate(new RTCIceCandidate(msg.candidate))
      }
    }

    ws.onopen = async () => {
      // Some Isaac Sim versions expect the client to send the offer
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      ws.send(JSON.stringify(pc.localDescription))
    }

    pc.onicecandidate = (ev) => {
      if (ev.candidate && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'candidate', candidate: ev.candidate }))
      }
    }
  }, [workerId, stop])

  useEffect(() => {
    connect()
    return stop
  }, [connect, stop])

  // Retry on error after 5 s
  useEffect(() => {
    if (status !== 'error') return
    const t = setTimeout(connect, 5000)
    return () => clearTimeout(t)
  }, [status, connect])

  return (
    <div className={`relative w-full h-full flex items-center justify-center bg-[#060810] ${className}`}>
      <div className="sim-grid" />

      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="max-w-full max-h-full object-contain relative z-1"
        style={{ display: status === 'live' ? 'block' : 'none' }}
      />
      <div className="scanlines" />

      {status !== 'live' && (
        <div className="relative z-10 flex flex-col items-center gap-2">
          {status === 'connecting'
            ? <div className="w-6 h-6 border-2 border-ink-700 border-t-gold rounded-full animate-spin" />
            : <i className="fas fa-circle-exclamation text-ink-500 text-xl" />
          }
          <span className="text-[10px] text-ink-500">
            {status === 'connecting' ? '连接流媒体...' : '重新连接中...'}
          </span>
        </div>
      )}

      {status === 'live' && (
        <div className="stream-hud">
          <span className="rec-dot" />
          <span className="text-[#e6c98a] font-semibold">LIVE</span>
          <span className="text-ink-500">|</span>
          <span className="text-sky2">{fps} FPS</span>
          {res && <><span className="text-ink-500">|</span><span className="text-ink-300">{res}</span></>}
        </div>
      )}
    </div>
  )
}
