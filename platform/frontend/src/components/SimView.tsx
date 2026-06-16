import { useEffect, useRef, useState } from 'react'

const HEALTH_URL = '/sim/health'
const STREAM_URL = '/sim/stream'

export default function SimView() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [status, setStatus] = useState<'waiting' | 'live' | 'error'>('waiting')
  const [fps, setFps] = useState(0)
  const [res, setRes] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let cancelled = false

    async function waitAndStream() {
      // Poll health
      while (!cancelled) {
        try {
          const r = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(1500) })
          if (r.ok) break
        } catch {}
        await new Promise(r => setTimeout(r, 2000))
      }
      if (cancelled) return
      startStream()
    }

    async function startStream() {
      const abort = new AbortController()
      abortRef.current = abort
      setStatus('live')

      try {
        const resp = await fetch(STREAM_URL, { signal: abort.signal })
        const reader = resp.body!.getReader()

        let buf = new Uint8Array(0)
        const SOI = [0xFF, 0xD8]
        const EOI = [0xFF, 0xD9]
        let frameCount = 0
        let lastFpsTick = performance.now()

        function concat(a: Uint8Array, b: Uint8Array) {
          const c = new Uint8Array(a.length + b.length)
          c.set(a); c.set(b, a.length); return c
        }

        function indexOf(h: Uint8Array, n: number[], from = 0) {
          outer: for (let i = from; i <= h.length - n.length; i++) {
            for (let j = 0; j < n.length; j++) if (h[i+j] !== n[j]) continue outer
            return i
          }
          return -1
        }

        while (!abort.signal.aborted) {
          const { done, value } = await reader.read()
          if (done) break
          buf = concat(buf, value)

          let start = indexOf(buf, SOI)
          while (start !== -1) {
            const end = indexOf(buf, EOI, start + 2)
            if (end === -1) break
            const jpeg = buf.slice(start, end + 2)
            buf = buf.slice(end + 2)

            const blob = new Blob([jpeg], { type: 'image/jpeg' })
            const url = URL.createObjectURL(blob)
            const img = new Image()
            img.onload = () => {
              const canvas = canvasRef.current
              if (!canvas) { URL.revokeObjectURL(url); return }
              canvas.width = img.naturalWidth
              canvas.height = img.naturalHeight
              canvas.getContext('2d')!.drawImage(img, 0, 0)
              URL.revokeObjectURL(url)
              frameCount++
              setRes(`${img.naturalWidth}×${img.naturalHeight}`)
              const now = performance.now()
              if (now - lastFpsTick >= 1000) {
                setFps(Math.round(frameCount / ((now - lastFpsTick) / 1000)))
                frameCount = 0; lastFpsTick = now
              }
            }
            img.src = url
            start = indexOf(buf, SOI)
          }
          if (buf.length > 500_000) buf = buf.slice(-100_000)
        }
      } catch {
        if (!cancelled) { setStatus('error'); setTimeout(() => { if (!cancelled) waitAndStream() }, 3000) }
      }
    }

    waitAndStream()
    return () => { cancelled = true; abortRef.current?.abort() }
  }, [])

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-3 h-8 bg-gray-900 border-b border-gray-800 flex-shrink-0 text-xs">
        <div className={`w-2 h-2 rounded-full ${status === 'live' ? 'bg-green-400' : status === 'error' ? 'bg-red-400' : 'bg-yellow-400 animate-pulse'}`} />
        <span className="text-gray-500">{status === 'live' ? 'Isaac Sim 实时视图' : status === 'error' ? '连接失败' : '等待 Isaac Sim...'}</span>
        {status === 'live' && <>
          <span className="ml-auto text-gray-600">FPS <span className="text-gray-300">{fps}</span></span>
          <span className="text-gray-600">{res}</span>
        </>}
      </div>
      {/* Canvas */}
      <div className="flex-1 bg-black flex items-center justify-center relative overflow-hidden">
        <canvas ref={canvasRef}
          className="max-w-full max-h-full object-contain"
          style={{ display: status === 'live' ? 'block' : 'none' }} />
        {status !== 'live' && (
          <div className="flex flex-col items-center gap-3 text-gray-600">
            <div className="w-8 h-8 border-2 border-gray-700 border-t-green-400 rounded-full animate-spin" />
            <span className="text-sm">{status === 'error' ? '重新连接中...' : '等待 Isaac Sim 启动...'}</span>
          </div>
        )}
      </div>
    </div>
  )
}
