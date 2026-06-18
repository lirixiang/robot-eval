import { useEffect, useRef, useState } from 'react'

interface Props {
  workerId: number
  className?: string
}

type Status = 'connecting' | 'live' | 'error'

export default function StreamCanvas({ workerId, className = '' }: Props) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [status, setStatus] = useState<Status>('connecting')

  useEffect(() => {
    const img = imgRef.current
    if (!img) return

    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const src = `/api/workers/${workerId}/mjpeg`

    const start = () => {
      setStatus('connecting')
      img.src = src
    }

    img.onload = () => setStatus('live')
    img.onerror = () => {
      setStatus('error')
      retryTimer = setTimeout(start, 3000)
    }

    start()

    return () => {
      if (retryTimer) clearTimeout(retryTimer)
      img.src = ''
    }
  }, [workerId])

  return (
    <div className={`relative w-full h-full flex items-center justify-center bg-[#060810] ${className}`}>
      <div className="sim-grid" />

      <img
        ref={imgRef}
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
          <span className="text-sky2">MJPEG</span>
        </div>
      )}
    </div>
  )
}
