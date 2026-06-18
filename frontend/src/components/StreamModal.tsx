import StreamCanvas from './StreamCanvas'
import type { Worker, Job } from '../types'

interface Props {
  workerId: number
  worker:   Worker | null
  activeJob: Job | null
  onClose:  () => void
}

export default function StreamModal({ workerId, worker, activeJob, onClose }: Props) {
  const job = activeJob?.config

  const handleBackdrop = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,.85)', backdropFilter: 'blur(6px)' }}
      onClick={handleBackdrop}
    >
      <div
        className="flex flex-col bg-ink-900 border border-edge rounded-xl overflow-hidden"
        style={{ width: 'min(1280px, calc(100vw - 80px))', maxHeight: 'calc(100vh - 80px)', boxShadow: '0 0 60px rgba(0,0,0,.8)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-ink-800 bg-ink-850 flex-shrink-0">
          <span className="rec-dot" />
          <span className="text-[13px] font-semibold text-white">
            实时仿真预览 · worker-{workerId}
          </span>
          {worker?.busy
            ? <span className="chip chip-run">运行中</span>
            : <span className="chip">空闲</span>
          }
          {job && (
            <span className="num text-[11px] text-ink-400">
              {String(job.arena_env_args?.environment ?? '')} · {String(job.arena_env_args?.embodiment ?? '')}
            </span>
          )}
          <div className="flex-1" />
          <button className="btn-sm" onClick={onClose}>
            <i className="fas fa-times mr-1" />关闭 <kbd className="kbd ml-1">Esc</kbd>
          </button>
        </div>

        {/* Stream area */}
        <div className="flex-1 min-h-0 relative bg-[#040608]" style={{ aspectRatio: '16/9' }}>
          <StreamCanvas workerId={workerId} className="absolute inset-0 w-full h-full" />
        </div>

        {/* Footer */}
        <div className="flex items-center gap-4 px-4 py-2 border-t border-ink-800 bg-ink-850 flex-shrink-0 text-[11px]">
          {activeJob ? (
            <>
              <span className="text-ink-500">任务</span>
              <span className="num text-gold">{activeJob.id}</span>
              <span className="text-ink-500">环境</span>
              <span className="text-sky2">{String(activeJob.config.arena_env_args?.environment ?? '—')}</span>
              <span className="text-ink-500">机器人</span>
              <span className="text-ink-200">{String(activeJob.config.arena_env_args?.embodiment ?? '—')}</span>
              <span className="text-ink-500">策略</span>
              <span className="text-ink-200">{activeJob.config.policy_type}</span>
            </>
          ) : (
            <span className="text-ink-500">无运行中任务</span>
          )}
        </div>
      </div>
    </div>
  )
}

