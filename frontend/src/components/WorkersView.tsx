import { useState, useEffect } from 'react'
import type { Worker } from '../types'
import { fetchRayStatus, type RayStatus } from '../api'

interface Props {
  workers:     Worker[]
  onOpenModal: (id: number) => void
  onRefresh:   () => void
}

interface SystemInfo { local_ip: string; cpu_count: number; mem_gb: number; gpu_count: number }

function useSystemInfo(): SystemInfo {
  const [info, setInfo] = useState<SystemInfo>(
    { local_ip: '...', cpu_count: 0, mem_gb: 0, gpu_count: 0 }
  )
  useEffect(() => {
    fetch('/api/system/info')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.local_ip) setInfo(d) })
      .catch(() => {})
  }, [])
  return info
}

function useRayStatus() {
  const [ray, setRay] = useState<RayStatus | null>(null)
  useEffect(() => {
    const fetch_ = () => fetchRayStatus().then(setRay).catch(() => {})
    fetch_()
    const t = setInterval(fetch_, 5000)
    return () => clearInterval(t)
  }, [])
  return ray
}

function SimPlaceholder({ online }: { online: boolean }) {
  return (
    <div className="sim-preview h-48 bg-[#060810] relative overflow-hidden" style={{ aspectRatio: 'unset' }}>
      <div className="sim-grid" />
      <div className="scanlines" />
      {online ? (
        <div className="relative z-10 flex flex-col items-center justify-center gap-2">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="opacity-30">
            <rect x="8" y="16" width="32" height="20" rx="3" stroke="#d4a857" strokeWidth="1.5" />
            <rect x="20" y="36" width="8" height="5" stroke="#d4a857" strokeWidth="1.5" />
            <rect x="14" y="41" width="20" height="2" rx="1" stroke="#d4a857" strokeWidth="1.5" />
            <circle cx="16" cy="24" r="2.5" stroke="#d4a857" strokeWidth="1.5" />
            <circle cx="32" cy="24" r="2.5" stroke="#d4a857" strokeWidth="1.5" />
            <path d="M20 26 L24 23 L28 26" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span className="text-[10px] text-ink-600 font-mono">ISAAC SIM READY</span>
        </div>
      ) : (
        <div className="relative z-10 flex flex-col items-center justify-center gap-2">
          <i className="fas fa-plug text-ink-700 text-xl" />
          <span className="text-[10px] text-ink-700 font-mono">OFFLINE</span>
        </div>
      )}
    </div>
  )
}

export default function WorkersView({ workers, onOpenModal, onRefresh }: Props) {
  const anyOnline = workers.some(w => w.online)
  const sys        = useSystemInfo()
  const rayStatus  = useRayStatus()

  const dockerCmd = `docker run -d --runtime=nvidia --network=host \\
  --gpus='"device=1"' \\
  -e RAY_HEAD_IP=${sys.local_ip} \\
  -e RAY_HEAD_PORT=6379 \\
  -v /home/disk/lrx:/home/disk/lrx \\
  lw_benchhub:latest \\
  bash -c "ray start --address=${sys.local_ip}:6379 --num-gpus=1"`

  return (
    <div className="overflow-y-auto p-5 space-y-5">
      {/* Ray cluster overview */}
      <div className="form-section">
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <span className="tag text-ink-400">Ray 集群</span>
          <span className={`chip ${rayStatus?.online ? 'chip-run' : 'chip-fail'}`}>
            {rayStatus?.online ? '在线' : rayStatus === null ? '查询中...' : '离线'}
          </span>
          <span className="font-mono text-[11px] text-ink-500">{sys.local_ip}:8265</span>
          <a href={`http://${sys.local_ip}:8265`} target="_blank" rel="noreferrer" className="btn-sm">
            Ray Dashboard <i className="fas fa-arrow-up-right-from-square ml-1 text-[9px]" />
          </a>
        </div>
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: '节点数', value: rayStatus ? String(rayStatus.nodes) : '—',                         icon: 'fa-server' },
            { label: 'CPU 核', value: rayStatus ? `${rayStatus.cpu_used}/${rayStatus.cpu_total}` : '—',  icon: 'fa-microchip' },
            { label: 'GPU 数', value: rayStatus ? `${rayStatus.gpu_used}/${rayStatus.gpu_total}` : '—',  icon: 'fa-gpu' },
            { label: '内存',   value: rayStatus ? `${rayStatus.mem_total_gb} GB` : '—',                  icon: 'fa-memory' },
          ].map(s => (
            <div key={s.label} className="bg-ink-950 rounded-lg p-3 border border-ink-800">
              <div className="flex items-center gap-1.5 text-ink-500 text-[10px] mb-1">
                <i className={`fas ${s.icon} text-[10px]`} />
                {s.label}
              </div>
              <div className="num text-lg font-bold text-ink-200">{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Worker cards */}
      {workers.length === 0 && (
        <div className="text-center text-ink-600 py-12">
          <i className="fas fa-server text-3xl mb-3 block" />
          暂无注册 Worker
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {workers.map(w => (
          <div key={w.id} className={`form-section p-0 overflow-hidden rounded-lg ${w.busy ? 'busy' : ''}`}
               style={w.busy ? { borderColor: 'rgba(212,168,87,.35)' } : {}}>
            {/* Header */}
            <div className="px-3 py-2 bg-ink-800 flex items-center justify-between border-b border-ink-700">
              <div className="flex items-center gap-2">
                <i className="fas fa-server text-ink-500 text-[11px]" />
                <span className="text-xs font-medium text-ink-200">Worker #{w.id}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-ink-500">RTX 4090</span>
                <span className={`chip ${w.busy ? 'chip-run' : w.online ? 'chip-pend' : 'chip-fail'}`}>
                  {w.busy ? '运行中' : w.online ? '空闲' : '离线'}
                </span>
              </div>
            </div>

            {/* Sim preview */}
            <div className="relative">
              <SimPlaceholder online={w.online} />
              {w.online && (
                <>
                  <div className="stream-hud">
                    <span className="rec-dot" />
                    <span className="text-ink-300">REC</span>
                    <span className="text-ink-500">– FPS</span>
                    <span className="text-ink-500">1920×1080</span>
                  </div>
                  <div className="stream-hud-r">{w.host}:{w.livestream_port}</div>
                </>
              )}
              <button className="expand-btn" onClick={() => onOpenModal(w.id)} title="展开预览">
                ⛶
              </button>
            </div>

            {/* Stats bar */}
            <div className="p-3 space-y-2">
              <div>
                <div className="flex justify-between text-[10px] text-ink-500 mb-0.5">
                  <span>GPU 利用率</span>
                  <span className="num">{w.busy ? '~60%' : '~5%'}</span>
                </div>
                <div className="level-bar">
                  <div className="level-fill transition-all duration-700" style={{ width: w.busy ? '60%' : '5%', background: '#d4a857' }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-[10px] text-ink-500 mb-0.5">
                  <span>VRAM</span>
                  <span className="num">{w.busy ? '~45%' : '~10%'}</span>
                </div>
                <div className="level-bar">
                  <div className="level-fill transition-all duration-700" style={{ width: w.busy ? '45%' : '10%', background: '#7c3aed' }} />
                </div>
              </div>

              {w.busy && (
                <div className="pt-1 space-y-0.5">
                  <div className="text-[10px] text-ink-400 truncate">{w.status}</div>
                  <div className="text-[10px] text-ink-500 truncate font-mono">{w.actor}</div>
                </div>
              )}

              {!w.busy && (
                <div className="flex gap-1.5 mt-1">
                  <button className="btn-sm flex-1" onClick={() => onOpenModal(w.id)}>
                    <i className="fas fa-plus mr-1" />分配任务
                  </button>
                  <button
                    className="btn-sm text-red-400 border-red-400/30 hover:bg-red-400/10"
                    title="从 Ray 集群移除 Worker（需在 worker 机器上执行 ray stop）"
                    onClick={() => {
                      alert('请在 worker 机器上执行 ray stop 以移除该节点')
                    }}
                  >
                    <i className="fas fa-trash" />
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Scale-out section */}
      <div className="form-section">
        <div className="flex items-center gap-2 mb-3">
          <span className="tag text-ink-400">扩展节点</span>
          <span className="chip chip-env">Docker</span>
        </div>
        <pre className="bg-ink-950 border border-ink-800 rounded-lg p-3 text-[11px] text-success font-mono overflow-x-auto leading-6 whitespace-pre">
{dockerCmd}
        </pre>
      </div>
    </div>
  )
}
