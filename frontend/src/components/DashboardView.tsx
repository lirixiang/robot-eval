import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts'
import type { Job, JobResult, Worker, Configs, SubmitRequest } from '../types'
import type { ViewName } from '../App'
import { StatusChip } from './StatusChip'

interface Props {
  jobs: Job[]
  results: JobResult[]
  workers: Worker[]
  activeJob: Job | null
  logs: string[]
  onSelectJob: (id: string) => void
  onOpenModal: (workerId: number) => void
  onNavigate: (v: ViewName) => void
  onQuickSubmit: (r: SubmitRequest) => Promise<void>
  configs: Configs
}

function LogLine({ line }: { line: string }) {
  const cls = line.includes('✓') ? 'text-success' : (line.includes('✗') || line.includes('ERROR')) ? 'text-fail' : 'text-ink-400'
  return <div className={`${cls} leading-5`}>{line}</div>
}


export default function DashboardView({ jobs, results, workers, activeJob, logs, onSelectJob, onOpenModal, onNavigate, onQuickSubmit, configs }: Props) {
  const logEndRef = useRef<HTMLDivElement>(null)
  const [submitting, setSubmitting] = useState(false)
  const [env, setEnv] = useState('')
  const [robot, setRobot] = useState('LeRobot-RL')
  const [episodes, setEpisodes] = useState(10)
  const [numEnvs, setNumEnvs] = useState(1)
  const [policyType, setPolicyType] = useState('')

  useEffect(() => {
    if (configs.environments[0] && !env) setEnv(configs.environments[0])
    if (configs.policy_types[0] && !policyType) setPolicyType(configs.policy_types[0])
  }, [configs]) // eslint-disable-line

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const onlineWorkers = workers.filter(w => w.online)
  const validResults = results.filter(r => r.metrics)
  const completedToday = validResults.length
  const avgSr = validResults.length ? validResults.reduce((s, r) => s + (r.metrics.success_rate ?? 0), 0) / validResults.length : 0
  const bestUph = validResults.length ? Math.max(...validResults.map(r => r.metrics.uph ?? 0)) : 0
  const avgCycle = validResults.length ? validResults.reduce((s, r) => s + (r.metrics.avg_cycle_s ?? 0), 0) / validResults.length : 0
  const recentResults = [...validResults].slice(-6).reverse()
  const trendData = [...validResults].slice(-10).map((r, i) => ({ i, v: +(r.metrics.success_rate * 100).toFixed(1) }))
  const theoreticalUph = avgCycle > 0 ? 3600 / avgCycle : 0
  const uphPct = theoreticalUph > 0 ? Math.min(100, (bestUph / theoreticalUph) * 100) : 0

  const handleQuickSubmit = async () => {
    if (!env || !policyType) return
    setSubmitting(true)
    try {
      await onQuickSubmit({
        name: `quick-${Date.now()}`,
        arena_env_args: { environment: env },
        num_envs: numEnvs,
        num_episodes: episodes,
        num_steps: null,
        policy_type: policyType,
        policy_config: { robot },
        policy_server_url: '',
        model_name: '',
        submitter: '',
        description: '',
        priority: 5,
        num_gpus: 1,
        gpu_type: '',
      })
    } finally { setSubmitting(false) }
  }

  return (
    <div className="flex h-[calc(100vh-84px)]">
      {/* LEFT: Workers */}
      <div className="w-[300px] flex-shrink-0 border-r border-ink-700 bg-ink-900 overflow-y-auto flex flex-col">
        <div className="px-3 py-2 border-b border-ink-800 flex items-center justify-between flex-shrink-0">
          <span className="tag text-ink-400">Isaac Lab Workers</span>
          <span className="chip chip-run">{onlineWorkers.length} 在线</span>
        </div>

        <div className="flex-1 p-2 space-y-2">
          {workers.length === 0 && (
            <div className="text-center text-ink-600 text-xs py-6">暂无 Worker</div>
          )}
          {workers.map(w => (
            <div key={w.id} className={`worker-card p-2 cursor-pointer ${w.busy ? 'busy' : ''}`}
                 onClick={() => onOpenModal(w.id)}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-ink-300 font-medium">Worker #{w.id}</span>
                <span className={`chip ${w.busy ? 'chip-run' : w.online ? 'chip-pend' : 'chip-fail'}`}>
                  {w.busy ? '运行' : w.online ? '空闲' : '离线'}
                </span>
              </div>
              <div className="mb-1.5">
                <div className="flex justify-between text-[10px] text-ink-500 mb-0.5">
                  <span>GPU</span><span>{w.busy ? '~60%' : '~5%'}</span>
                </div>
                <div className="level-bar"><div className="level-fill bg-gold transition-all duration-700" style={{ width: w.busy ? '60%' : '5%' }} /></div>
              </div>
              {w.busy && <div className="text-[10px] text-ink-500 truncate">{w.status}</div>}
              {!w.busy && w.online && (
                <button className="btn-sm w-full mt-1.5" onClick={e => { e.stopPropagation(); onOpenModal(w.id) }}>
                  分配任务
                </button>
              )}
            </div>
          ))}
        </div>

        {/* 今日统计 */}
        <div className="p-2 border-t border-ink-800 flex-shrink-0">
          <div className="tag text-ink-500 mb-2 px-1">今日统计</div>
          <div className="grid grid-cols-2 gap-1.5">
            {[
              { label: '成功率', value: `${(avgSr * 100).toFixed(1)}%`, color: 'text-success' },
              { label: '最佳 UPH', value: bestUph.toFixed(0), color: 'text-gold' },
              { label: '平均耗时', value: `${avgCycle.toFixed(1)}s`, color: 'text-ink-200' },
              { label: '已完成', value: String(completedToday), color: 'text-ink-200' },
            ].map(s => (
              <div key={s.label} className="form-section p-2 rounded-md">
                <div className="text-[10px] text-ink-500 mb-0.5">{s.label}</div>
                <div className={`num text-sm font-semibold ${s.color}`}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CENTER */}
      <div className="flex-1 bg-ink-950 flex flex-col min-w-0">
        {activeJob ? (
          <div className="flex-shrink-0 border-b border-ink-800 p-3 bg-ink-900">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="tag text-ink-500">运行中</span>
                <span className="chip chip-run font-mono text-[11px]">{activeJob.id.slice(0, 8)}</span>
                <StatusChip status={activeJob.status} />
              </div>
              <button className="btn-sm" style={{ color: '#fca5a5', borderColor: 'rgba(239,68,68,.3)' }}>终止</button>
            </div>
            <div className="level-bar h-1.5 mb-1">
              <div className="level-fill progress-run" style={{ width: '60%' }} />
            </div>
            <div className="flex gap-4 text-[10px] text-ink-500 mt-1 num">
              <span>预计剩余 <span className="text-ink-300">--s</span></span>
              <span>已完成 <span className="text-ink-300">--</span> 轮</span>
              <span>成功率 <span className="text-ink-300">--%</span></span>
            </div>
          </div>
        ) : (
          <div className="flex-shrink-0 border-b border-ink-800 p-3 flex items-center justify-between bg-ink-900">
            <span className="text-xs text-ink-500">暂无运行中任务</span>
            <button className="btn-sm" onClick={() => onNavigate('eval')}>
              <i className="fas fa-plus mr-1" />新建任务
            </button>
          </div>
        )}

        {/* Logs */}
        <div className="flex-shrink-0 border-b border-ink-800 h-28 overflow-y-auto bg-[#060810] p-2 font-mono text-xs">
          {logs.length === 0 ? (
            <div className="text-ink-600 text-center mt-6">选择任务后显示日志…</div>
          ) : (
            logs.map((l, i) => <LogLine key={i} line={l} />)
          )}
          <div ref={logEndRef} />
        </div>

        {/* Recent results table */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="thead-sticky border-b border-ink-800">
                {['Job ID', '环境', '策略', '成功率', 'UPH', '耗时', '状态', '操作'].map(h => (
                  <th key={h} className="text-left text-ink-500 font-normal px-3 py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentResults.length === 0 && (
                <tr><td colSpan={8} className="text-center text-ink-600 py-10">暂无评测结果</td></tr>
              )}
              {recentResults.map(r => (
                <tr key={r.job_id} className="row-hover border-b border-ink-800/50 cursor-pointer"
                    onClick={() => { onSelectJob(r.job_id); onNavigate('eval') }}>
                  <td className="px-3 py-2 font-mono text-gold">{r.job_id.slice(0, 8)}</td>
                  <td className="px-3 py-2 text-ink-300">{String(r.job.arena_env_args?.environment ?? '–')}</td>
                  <td className="px-3 py-2"><span className="chip chip-env">{r.job.policy_type}</span></td>
                  <td className="px-3 py-2 num text-success">{((r.metrics.success_rate ?? 0) * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2 num text-gold">{(r.metrics.uph ?? 0).toFixed(1)}</td>
                  <td className="px-3 py-2 num text-ink-300">{r.elapsed_s.toFixed(1)}s</td>
                  <td className="px-3 py-2"><span className="chip chip-done">done</span></td>
                  <td className="px-3 py-2">
                    <button className="btn-sm" onClick={e => { e.stopPropagation(); onSelectJob(r.job_id); onNavigate('eval') }}>查看</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* RIGHT: Quick submit + stats */}
      <div className="w-[320px] flex-shrink-0 border-l border-ink-700 bg-ink-900 overflow-y-auto p-3 space-y-3">
        <div className="form-section space-y-2">
          <div className="tag text-ink-400 mb-2">快速提交</div>
          <select className="inp" value={env} onChange={e => setEnv(e.target.value)}>
            {configs.environments.map(ev => <option key={ev}>{ev}</option>)}
          </select>
          <input className="inp" placeholder="Robot (e.g. LeRobot-RL)" value={robot} onChange={e => setRobot(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-[10px] text-ink-500 mb-0.5">轮次</div>
              <input type="number" className="inp" value={episodes} min={1} onChange={e => setEpisodes(+e.target.value)} />
            </div>
            <div>
              <div className="text-[10px] text-ink-500 mb-0.5">并发</div>
              <input type="number" className="inp" value={numEnvs} min={1} onChange={e => setNumEnvs(+e.target.value)} />
            </div>
          </div>
          <select className="inp" value={policyType} onChange={e => setPolicyType(e.target.value)}>
            {configs.policy_types.map(p => <option key={p}>{p}</option>)}
          </select>
          <button className="btn-primary w-full text-sm" disabled={submitting} onClick={handleQuickSubmit}>
            {submitting ? <><span className="spinner mr-1" />提交中…</> : '提交评测'}
          </button>
        </div>

        {results.length > 0 && (
          <div className="form-section">
            <div className="tag text-ink-400 mb-2">理论极限 UPH</div>
            <div className="flex justify-between items-baseline mb-1.5">
              <span className="num text-xl text-gold">{theoreticalUph.toFixed(0)}</span>
              <span className="text-[10px] text-ink-500">实际 {bestUph.toFixed(0)}</span>
            </div>
            <div className="level-bar">
              <div className="level-fill transition-all duration-700" style={{ width: `${uphPct}%`, background: uphPct > 80 ? '#10b981' : '#d4a857' }} />
            </div>
            <div className="text-[10px] text-ink-600 mt-1">{uphPct.toFixed(0)}% 利用率</div>
          </div>
        )}

        {trendData.length > 1 && (
          <div className="form-section">
            <div className="tag text-ink-400 mb-2">成功率趋势</div>
            <ResponsiveContainer width="100%" height={80}>
              <AreaChart data={trendData} margin={{ top: 4, right: 4, left: -30, bottom: 0 }}>
                <defs>
                  <linearGradient id="dashGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#d4a857" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#d4a857" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Tooltip contentStyle={{ background: '#0b0e14', border: '1px solid #1f2535', fontSize: 11 }}
                         formatter={(v: number) => [`${v.toFixed(1)}%`, '成功率']} />
                <Area type="monotone" dataKey="v" stroke="#d4a857" fill="url(#dashGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
