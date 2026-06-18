import type { Worker, Job } from '../types'

interface Props {
  worker:    Worker
  activeJob: Job | null
  onOpenModal: (id: number) => void
  onAssign?:   () => void
}

export default function WorkerCard({ worker, activeJob, onOpenModal, onAssign }: Props) {
  const job = worker.busy && activeJob ? activeJob.config : null
  const gpuPct  = worker.busy ? 70 + Math.round(worker.id * 4) : 3
  const vramPct = worker.busy ? 58 + Math.round(worker.id * 3) : 6

  return (
    <div className={`worker-card ${worker.busy ? 'busy' : ''}`}>
      {/* Sim preview */}
      <div
        className="sim-preview cursor-pointer"
        onClick={() => onOpenModal(worker.id)}
      >
        <div className="sim-grid" />
        {/* Placeholder SVG — StreamCanvas in WorkersView handles full preview */}
        <svg viewBox="0 0 280 158" className="absolute inset-0 w-full h-full"
             style={{ opacity: worker.busy ? 0.7 : 0.35 }}>
          <rect x="0" y="130" width="280" height="28" fill="#0a0e16"/>
          <line x1="0" y1="130" x2="280" y2="130" stroke="#1f2535" strokeWidth="1"/>
          <rect x="110" y="110" width="60" height="20" rx="3" fill="#141923" stroke="#2a3142" strokeWidth="1"/>
          {worker.busy ? (
            <>
              <line x1="140" y1="110" x2="140" y2="65" stroke="#7dd3fc" strokeWidth="3" strokeLinecap="round"/>
              <circle cx="140" cy="65" r="5" fill="#7dd3fc"/>
              <line x1="140" y1="65" x2="172" y2="45" stroke="#7dd3fc" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="172" cy="45" r="4" fill="#a78bfa"/>
              <line x1="172" y1="45" x2="165" y2="58" stroke="#d4a857" strokeWidth="2" strokeLinecap="round"/>
              <line x1="172" y1="45" x2="179" y2="58" stroke="#d4a857" strokeWidth="2" strokeLinecap="round"/>
              <rect x="169" y="52" width="6" height="6" rx="1" fill="#d4a857" opacity=".9"/>
            </>
          ) : (
            <>
              <line x1="140" y1="110" x2="140" y2="75" stroke="#2a3142" strokeWidth="3" strokeLinecap="round"/>
              <circle cx="140" cy="75" r="5" fill="#2a3142"/>
            </>
          )}
        </svg>
        <div className="stream-hud" style={{ display: worker.busy ? 'flex' : 'none' }}>
          <span className="rec-dot" />
          <span className="text-[#e6c98a]">REC</span>
          <span className="text-ink-500 text-[10px]">worker-{worker.id}</span>
        </div>
        <button
          className="expand-btn"
          onClick={e => { e.stopPropagation(); onOpenModal(worker.id) }}
        >
          <i className="fas fa-expand text-[9px] mr-1" />全屏
        </button>
      </div>

      {/* Card body */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-medium text-white">worker-{worker.id}</span>
            {worker.busy
              ? <span className="chip chip-run">运行中</span>
              : worker.online
                ? <span className="chip">空闲</span>
                : <span className="chip chip-fail">离线</span>
            }
          </div>
          <span className="text-[10px] text-ink-500 num">GPU {worker.id}</span>
        </div>

        {job && (
          <div className="text-[11px] text-ink-400 mb-2">
            <span className="text-violet">{worker.actor}</span>
            {' · '}{String(job.arena_env_args?.environment ?? '')}
            {' · '}{String(job.arena_env_args?.embodiment ?? '')}
          </div>
        )}

        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-ink-500 w-8">GPU</span>
          <div className="level-bar flex-1">
            <div className="level-fill" style={{
              width: `${gpuPct}%`,
              background: worker.busy ? 'linear-gradient(90deg,#a78bfa,#7c3aed)' : '#2a3142'
            }} />
          </div>
          <span className={`num text-[10px] ${worker.busy ? 'text-violet' : 'text-ink-500'}`}>{gpuPct}%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-ink-500 w-8">VRAM</span>
          <div className="level-bar flex-1">
            <div className="level-fill" style={{
              width: `${vramPct}%`,
              background: worker.busy ? 'linear-gradient(90deg,#7dd3fc,#38bdf8)' : '#1c2230'
            }} />
          </div>
          <span className={`num text-[10px] ${worker.busy ? 'text-sky2' : 'text-ink-500'}`}>{vramPct}%</span>
        </div>

        {!worker.busy && worker.online && onAssign && (
          <button className="btn-primary w-full mt-3 text-[11px] py-1.5" onClick={onAssign}>
            <i className="fas fa-play mr-1.5 text-[10px]" />分配任务
          </button>
        )}
      </div>
    </div>
  )
}
