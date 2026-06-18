import { useState, useEffect, useRef } from 'react'
import type { Job } from '../types'
import type { ViewName } from '../App'
import { setBaseline, reproduceJob } from '../api'

interface Props {
  jobs: Job[]
  selectedId: string | null
  logs: string[]
  onSelect: (id: string) => void
  onCancel: (id: string) => void
  onNavigate: (v: ViewName) => void
  onReproduce?: (jobId: string) => Promise<void>
}

type Filter = 'all' | 'running' | 'done' | 'failed'

const STATUS_CHIP: Record<string, string> = {
  running: 'chip-run', done: 'chip-done', failed: 'chip-fail', failed_final: 'chip-fail',
  pending: 'chip-pend', cancelled: 'chip', retry_pending: 'chip-pend',
}

function LogLine({ line }: { line: string }) {
  const cls = line.includes('✓') ? 'text-success' : (line.includes('✗') || line.includes('ERROR')) ? 'text-fail' : 'text-ink-400'
  return <div className={`${cls} leading-5`}>{line}</div>
}

export default function JobsView({ jobs, selectedId, logs, onSelect, onCancel, onNavigate, onReproduce }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const logEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const selectedJob = jobs.find(j => j.id === selectedId) ?? null

  const filtered = jobs.filter(j => {
    if (filter === 'all') return true
    if (filter === 'running') return j.status === 'running' || j.status === 'pending' || j.status === 'retry_pending'
    if (filter === 'done') return j.status === 'done'
    if (filter === 'failed') return j.status === 'failed' || j.status === 'failed_final' || j.status === 'cancelled'
    return true
  })

  const FILTERS: { id: Filter; label: string }[] = [
    { id: 'all', label: '全部' },
    { id: 'running', label: '运行中' },
    { id: 'done', label: '完成' },
    { id: 'failed', label: '失败' },
  ]

  return (
    <div className="flex h-[calc(100vh-84px)]">
      {/* Main table */}
      <div className="flex-1 flex flex-col border-r border-ink-700 min-w-0">
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-ink-800 flex-shrink-0">
          <span className="text-sm font-medium text-ink-200">任务队列</span>
          <div className="seg">
            {FILTERS.map(f => (
              <button key={f.id} className={filter === f.id ? 'on' : ''} onClick={() => setFilter(f.id)}>{f.label}</button>
            ))}
          </div>
          <div className="flex-1" />
          <button className="btn-sm" onClick={() => onNavigate('submit')}>
            <i className="fas fa-plus mr-1" />新建
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="thead-sticky border-b border-ink-800">
                <th className="text-left text-ink-500 font-normal px-3 py-2">Job ID</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">环境 / 机器人</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">策略</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">进度</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">成功率</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">UPH</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">耗时(s)</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">状态</th>
                <th className="text-left text-ink-500 font-normal px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={9} className="text-center text-ink-600 py-10">暂无任务</td></tr>
              )}
              {filtered.map(job => {
                const isActive = job.id === selectedId
                const m = job.result?.metrics
                const envStr = job.model_name ?? String(job.config?.arena_env_args?.environment ?? '–')
                const robotStr = String(job.config?.policy_config?.robot ?? '–')
                return (
                  <tr key={job.id}
                      className={`row-hover border-b border-ink-800/50 cursor-pointer ${isActive ? 'bg-[#0d1017]' : ''}`}
                      onClick={() => onSelect(job.id)}>
                    <td className="px-3 py-2 font-mono text-gold">{job.id.slice(0, 8)}</td>
                    <td className="px-3 py-2">
                      <div className="text-ink-200 truncate max-w-[120px]">{envStr}</div>
                      <div className="text-[10px] text-ink-500">{robotStr}</div>
                    </td>
                    <td className="px-3 py-2"><span className="chip chip-env">{job.config?.policy_type ?? job.submitter ?? '–'}</span></td>
                    <td className="px-3 py-2 w-24">
                      {job.status === 'running' ? (
                        <div className="level-bar h-1.5">
                          <div className="level-fill progress-run" style={{ width: '60%' }} />
                        </div>
                      ) : m ? (
                        <span className="num text-ink-300">{m.success_count ?? '–'}/{m.total_episodes ?? job.config?.num_episodes ?? '–'}</span>
                      ) : <span className="text-ink-600">–</span>}
                    </td>
                    <td className="px-3 py-2 num">{m ? <span className="text-success">{(m.success_rate * 100).toFixed(1)}%</span> : '–'}</td>
                    <td className="px-3 py-2 num text-gold">{m ? m.uph.toFixed(1) : '–'}</td>
                    <td className="px-3 py-2 num text-ink-300">{job.result ? job.result.elapsed_s.toFixed(1) : '–'}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1 flex-wrap">
                        <span className={`chip ${STATUS_CHIP[job.status] ?? 'chip'}`}>{job.status}</span>
                        {job.retry_count != null && job.retry_count > 0 && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/40 text-red-400 border border-red-800/40">
                            重试 {job.retry_count}/{job.max_retries ?? 3}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <button className="btn-sm" onClick={e => { e.stopPropagation(); onSelect(job.id) }}>日志</button>
                        {(job.status === 'running' || job.status === 'pending') && (
                          <button className="btn-sm" style={{ color: '#fca5a5', borderColor: 'rgba(239,68,68,.3)' }}
                                  onClick={e => { e.stopPropagation(); onCancel(job.id) }}>×</button>
                        )}
                        {(job.status === 'failed_final' || job.status === 'failed') && onReproduce && (
                          <button className="btn-sm" style={{ color: '#86efac', borderColor: 'rgba(34,197,94,.3)' }}
                                  onClick={e => { e.stopPropagation(); onReproduce(job.id) }}>复现</button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right detail panel */}
      <div className="w-80 flex-shrink-0 bg-ink-900 border-l border-ink-700 overflow-y-auto p-3 flex flex-col gap-3">
        {!selectedJob ? (
          <div className="flex flex-col items-center justify-center h-full text-ink-600 gap-2">
            <i className="fas fa-list-check text-2xl" />
            <span className="text-xs">点击任务查看详情</span>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="font-mono text-gold text-sm">{selectedJob.id.slice(0, 16)}…</span>
              <div className="flex items-center gap-1.5">
                <span className={`chip ${STATUS_CHIP[selectedJob.status] ?? 'chip'}`}>{selectedJob.status}</span>
                {selectedJob.retry_count != null && selectedJob.retry_count > 0 && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/40 text-red-400 border border-red-800/40">
                    重试 {selectedJob.retry_count}/{selectedJob.max_retries ?? 3}
                  </span>
                )}
              </div>
            </div>

            <div className="form-section space-y-1.5">
              <div className="tag text-ink-500 mb-1">任务配置</div>
              {[
                ['环境', String(selectedJob.config?.arena_env_args?.environment ?? selectedJob.model_name ?? '–')],
                ['机器人', String(selectedJob.config?.policy_config?.robot ?? '–')],
                ['策略', selectedJob.config?.policy_type ?? selectedJob.submitter ?? '–'],
                ['并发', String(selectedJob.config?.num_envs ?? '–')],
                ['轮次', String(selectedJob.config?.num_episodes ?? '–')],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-ink-500">{k}</span>
                  <span className="text-ink-200 font-mono">{v}</span>
                </div>
              ))}
            </div>

            {selectedJob.result && (
              <div className="form-section">
                <div className="tag text-ink-500 mb-2">评测指标</div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: '成功率', value: `${(selectedJob.result.metrics.success_rate * 100).toFixed(1)}%`, color: 'text-success' },
                    { label: 'UPH', value: selectedJob.result.metrics.uph.toFixed(1), color: 'text-gold' },
                    { label: '平均耗时', value: `${selectedJob.result.metrics.avg_cycle_s.toFixed(1)}s`, color: 'text-ink-200' },
                    { label: '总轮次', value: String(selectedJob.result.metrics.total_episodes ?? '–'), color: 'text-ink-200' },
                  ].map(s => (
                    <div key={s.label} className="bg-ink-950 rounded-md p-2">
                      <div className="text-[10px] text-ink-500">{s.label}</div>
                      <div className={`num text-sm font-semibold ${s.color}`}>{s.value}</div>
                    </div>
                  ))}
                </div>
                {selectedJob.latest_run && (
                  <button
                    className="mt-2 btn-sm w-full text-center"
                    style={{ color: '#86efac', borderColor: 'rgba(34,197,94,.3)' }}
                    onClick={() => {
                      if (confirm('将此 Run 设为基准？')) {
                        setBaseline(selectedJob.latest_run!.id)
                      }
                    }}
                  >
                    设为基准
                  </button>
                )}
              </div>
            )}

            <div className="form-section flex-1 flex flex-col p-2">
              <div className="tag text-ink-500 mb-1.5 px-1">日志</div>
              <div className="flex-1 h-48 overflow-y-auto bg-ink-950 rounded p-2 font-mono text-xs">
                {logs.length === 0 ? (
                  <div className="text-ink-600 text-center py-4">暂无日志</div>
                ) : (
                  logs.map((l, i) => <LogLine key={i} line={l} />)
                )}
                <div ref={logEndRef} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
