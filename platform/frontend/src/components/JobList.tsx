import type { Job } from '../types'
import { XCircle } from 'lucide-react'

interface Props {
  jobs: Job[]
  selectedId: string | null
  onSelect: (id: string) => void
  onCancel: (id: string) => void
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'text-yellow-400',
  running: 'text-blue-400',
  done:    'text-green-400',
  failed:  'text-red-400',
  cancelled: 'text-gray-500',
}

const STATUS_DOT: Record<string, string> = {
  pending: 'bg-yellow-400',
  running: 'bg-blue-400 animate-pulse',
  done:    'bg-green-400',
  failed:  'bg-red-400',
  cancelled: 'bg-gray-500',
}

export default function JobList({ jobs, selectedId, onSelect, onCancel }: Props) {
  if (!jobs.length) return (
    <div className="p-4 text-center text-gray-600 text-xs mt-8">暂无任务</div>
  )

  return (
    <div className="py-1">
      {jobs.map(job => (
        <div key={job.id} onClick={() => onSelect(job.id)}
          className={`px-3 py-2.5 cursor-pointer border-l-2 transition-colors hover:bg-gray-900 ${
            selectedId === job.id ? 'border-green-500 bg-gray-900' : 'border-transparent'
          }`}>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_DOT[job.status]}`} />
              <span className="text-xs font-mono text-gray-300">{job.id}</span>
            </div>
            {(job.status === 'pending' || job.status === 'running') && (
              <button onClick={e => { e.stopPropagation(); onCancel(job.id) }}
                className="text-gray-600 hover:text-red-400 transition-colors">
                <XCircle size={13} />
              </button>
            )}
          </div>
          <div className="text-xs text-gray-500 truncate">{job.config.task} · {job.config.robot}</div>
          <div className="flex items-center justify-between mt-1">
            <span className={`text-xs ${STATUS_COLOR[job.status]}`}>{job.status}</span>
            <span className="text-xs text-gray-600">{job.config.test_num} 轮</span>
          </div>
          {job.result && (
            <div className="mt-1.5 grid grid-cols-3 gap-1">
              {[
                ['成功率', `${(job.result.success_rate * 100).toFixed(0)}%`],
                ['UPH', job.result.uph.toFixed(1)],
                ['耗时', `${job.result.avg_cycle_seconds.toFixed(0)}s`],
              ].map(([k, v]) => (
                <div key={k} className="bg-gray-800 rounded px-1.5 py-0.5 text-center">
                  <div className="text-gray-500" style={{fontSize:'9px'}}>{k}</div>
                  <div className="text-green-400 text-xs font-semibold">{v}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
