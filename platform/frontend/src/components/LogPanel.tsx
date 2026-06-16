import { useEffect, useRef } from 'react'
import type { Job } from '../types'
import { BarChart2, Clock, Target, Zap } from 'lucide-react'

interface Props { job: Job | null; logs: string[] }

export default function LogPanel({ job, logs }: Props) {
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Metrics */}
      {job?.result && (
        <div className="p-3 border-b border-gray-800 flex-shrink-0">
          <div className="text-xs text-gray-500 mb-2 font-semibold tracking-wider">评测结果</div>
          <div className="grid grid-cols-2 gap-2">
            <MetricCard icon={<Target size={12} />} label="成功率"
              value={`${(job.result.success_rate * 100).toFixed(1)}%`}
              sub={`${job.result.success_count}/${job.result.test_num}`}
              color="text-green-400" />
            <MetricCard icon={<Zap size={12} />} label="UPH"
              value={job.result.uph.toFixed(1)}
              sub={`理论最大 ${job.result.theoretical_max_uph.toFixed(1)}`}
              color="text-blue-400" />
            <MetricCard icon={<Clock size={12} />} label="平均轮次"
              value={`${job.result.avg_cycle_seconds.toFixed(1)}s`}
              sub="每轮平均耗时"
              color="text-yellow-400" />
            <MetricCard icon={<BarChart2 size={12} />} label="总耗时"
              value={`${job.result.total_wall_seconds.toFixed(0)}s`}
              sub={`${(job.result.total_wall_seconds / 60).toFixed(1)} 分钟`}
              color="text-purple-400" />
          </div>
        </div>
      )}

      {/* Job info */}
      {job && !job.result && (
        <div className="px-3 py-2 border-b border-gray-800 flex-shrink-0">
          <div className="text-xs text-gray-500 mb-1">
            <span className="text-gray-400">{job.id}</span> · {job.config.task} · {job.config.robot}
          </div>
          <div className="flex items-center gap-1.5">
            {job.status === 'running' && <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />}
            <span className="text-xs text-gray-400">{job.status}</span>
          </div>
        </div>
      )}

      {/* Logs */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="px-3 py-1.5 border-b border-gray-800 flex-shrink-0">
          <span className="text-xs text-gray-600 font-semibold tracking-wider">日志</span>
        </div>
        <div ref={logRef} className="flex-1 overflow-y-auto p-2 font-mono text-xs leading-relaxed">
          {!job && <div className="text-gray-700 text-center mt-8">选择一个任务查看日志</div>}
          {logs.map((line, i) => (
            <div key={i} className={
              line.includes('✓') ? 'text-green-400' :
              line.includes('✗') ? 'text-red-400' :
              line.includes('ERROR') ? 'text-red-400' :
              line.includes('完成') ? 'text-green-300' :
              'text-gray-400'
            }>{line}</div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MetricCard({ icon, label, value, sub, color }: {
  icon: React.ReactNode; label: string; value: string; sub: string; color: string
}) {
  return (
    <div className="bg-gray-900 rounded p-2">
      <div className="flex items-center gap-1 text-gray-500 mb-1">
        {icon}<span className="text-xs">{label}</span>
      </div>
      <div className={`text-lg font-bold leading-none ${color}`}>{value}</div>
      <div className="text-gray-600 mt-0.5" style={{fontSize:'10px'}}>{sub}</div>
    </div>
  )
}
