import React, { useState, useRef } from 'react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from 'recharts'
import type { JobResult } from '../types'
import { fetchRun } from '../api'
import type { Run } from '../types'

interface Props {
  results: JobResult[]
  onNavigateAnalysis?: (runIds: string[]) => void
}

function exportCSV(results: JobResult[]) {
  const header = ['job_id', 'environment', 'robot', 'num_episodes', 'success_count', 'success_rate', 'avg_cycle_s', 'uph', 'theoretical_uph', 'status', 'timestamp']
  const rows = results.map(r => [
    r.job_id,
    String(r.job.arena_env_args?.environment ?? ''),
    String(r.job.policy_config?.robot ?? ''),
    r.job.num_episodes ?? '',
    r.metrics.success_count ?? '',
    (r.metrics.success_rate * 100).toFixed(2),
    r.metrics.avg_cycle_s.toFixed(2),
    r.metrics.uph.toFixed(2),
    r.metrics.theoretical_max_uph != null ? r.metrics.theoretical_max_uph.toFixed(2) : (r.metrics.avg_cycle_s > 0 ? (3600 / r.metrics.avg_cycle_s).toFixed(2) : ''),
    'done',
    new Date(r.timestamp * 1000).toISOString(),
  ])
  const csv = [header, ...rows].map(r => r.join(',')).join('\n')
  const a = document.createElement('a')
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
  a.download = `results_${Date.now()}.csv`
  a.click()
}

export default function ResultsView({ results, onNavigateAnalysis }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // runCache does not drive render directly — use a ref to avoid O(n) spreads and spurious re-renders.
  const runCache = useRef<Map<string, Run>>(new Map())
  // Trigger a re-render after a run is loaded so the expanded row can display its data.
  const [, forceUpdate] = useState(0)

  const toggleSelect = (jobId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(jobId) ? next.delete(jobId) : next.add(jobId)
      return next
    })
  }

  const toggleExpand = async (r: JobResult) => {
    const runId = r.run_id
    if (!runId) return  // no run_id available, can't fetch episodes
    const isExpanding = !expanded.has(r.job_id)
    setExpanded(prev => {
      const next = new Set(prev)
      isExpanding ? next.add(r.job_id) : next.delete(r.job_id)
      return next
    })
    // Lazily load run with episodes if not cached
    if (isExpanding && !runCache.current.has(r.job_id)) {
      try {
        const run = await fetchRun(runId)
        runCache.current.set(r.job_id, run)
        forceUpdate(n => n + 1)
      } catch {
        // Revert expansion so the user can see it failed rather than showing "暂无单集数据"
        setExpanded(prev => { const next = new Set(prev); next.delete(r.job_id); return next })
      }
    }
  }
  const validResults = results.filter(r => r.metrics)
  const totalJobs = validResults.length
  const avgSr = totalJobs ? validResults.reduce((s, r) => s + (r.metrics.success_rate ?? 0), 0) / totalJobs : 0
  const bestUph = totalJobs ? Math.max(...validResults.map(r => r.metrics.uph ?? 0)) : 0
  const avgCycle = totalJobs ? validResults.reduce((s, r) => s + (r.metrics.avg_cycle_s ?? 0), 0) / totalJobs : 0
  const theoreticalUph = avgCycle > 0 ? 3600 / avgCycle : 0

  const trendData = [...validResults].slice(-20).map((r, i) => ({ i, v: +(r.metrics.success_rate * 100).toFixed(1) }))

  // Group by environment for bar chart
  const envMap: Record<string, number[]> = {}
  validResults.forEach(r => {
    const e = String(r.job.arena_env_args?.environment ?? 'unknown')
    if (!envMap[e]) envMap[e] = []
    envMap[e].push(r.metrics.uph ?? 0)
  })
  const barData = Object.entries(envMap).map(([env, uphs]) => ({
    env: env.length > 16 ? env.slice(0, 14) + '…' : env,
    uph: +(uphs.reduce((s, v) => s + v, 0) / uphs.length).toFixed(1),
  }))

  const topMetrics = [
    { label: '总任务数', value: String(totalJobs), color: 'text-ink-200' },
    { label: '平均成功率', value: `${(avgSr * 100).toFixed(1)}%`, color: 'text-success' },
    { label: '最佳 UPH', value: bestUph.toFixed(1), color: 'text-gold' },
    { label: '平均耗时(s)', value: avgCycle.toFixed(1), color: 'text-ink-200' },
    { label: '理论最大 UPH', value: theoreticalUph.toFixed(1), color: 'text-gold' },
  ]

  const chartBg = { background: '#07090d', borderRadius: 6 }
  const tooltipStyle = { background: '#0b0e14', border: '1px solid #1f2535', fontSize: 11, borderRadius: 5 }

  return (
    <div className="overflow-y-auto p-5 space-y-5">
      {/* Top metrics */}
      <div className="grid grid-cols-5 gap-3">
        {topMetrics.map(m => (
          <div key={m.label} className="form-section p-3">
            <div className="text-[11px] text-ink-500 mb-1">{m.label}</div>
            <div className={`num text-lg font-semibold ${m.color}`}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="form-section">
          <div className="tag text-ink-400 mb-3">成功率趋势</div>
          <div style={chartBg}>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={trendData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="srGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#d4a857" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#d4a857" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="i" tick={{ fill: '#4a5368', fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: '#4a5368', fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v.toFixed(1)}%`, '成功率']} />
                <ReferenceLine y={80} stroke="#10b981" strokeDasharray="3 3" strokeOpacity={0.6} />
                <Area type="monotone" dataKey="v" stroke="#d4a857" fill="url(#srGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="form-section">
          <div className="tag text-ink-400 mb-3">UPH 分布（按环境）</div>
          <div style={chartBg}>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={barData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <XAxis dataKey="env" tick={{ fill: '#4a5368', fontSize: 9 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: '#4a5368', fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v.toFixed(1), 'UPH']} />
                <Bar dataKey="uph" radius={[3, 3, 0, 0]}>
                  {barData.map((_, i) => <Cell key={i} fill="#d4a857" fillOpacity={0.85} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Full results table */}
      <div className="form-section p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-800">
          <span className="tag text-ink-400">完整结果</span>
          <div className="flex items-center gap-2">
            {selected.size > 0 && onNavigateAnalysis && (
              <button className="btn-sm" style={{ color: '#86efac', borderColor: 'rgba(34,197,94,.3)' }}
                      onClick={() => {
                        const selectedRunIds = Array.from(selected)
                          .map(jobId => results.find(r => r.job_id === jobId)?.run_id)
                          .filter((id): id is string => !!id)
                        if (selectedRunIds.length > 0) {
                          onNavigateAnalysis(selectedRunIds)
                        }
                      }}>
                <i className="fas fa-chart-line mr-1" />比较选中 ({selected.size})
              </button>
            )}
            <button className="btn-sm" onClick={() => exportCSV(results)}>
              <i className="fas fa-download mr-1" />导出 CSV
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="thead-sticky border-b border-ink-800">
                <th className="text-left text-ink-500 font-normal px-3 py-2 w-8"></th>
                {['Job ID', '环境', '机器人', '轮次', '成功', '成功率', 'avg_cycle(s)', 'UPH', '理论UPH', '状态', '时间', ''].map(h => (
                  <th key={h} className="text-left text-ink-500 font-normal px-3 py-2 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.length === 0 && (
                <tr><td colSpan={13} className="text-center text-ink-600 py-10">暂无结果</td></tr>
              )}
              {[...validResults].reverse().map(r => {
                const m = r.metrics
                const tUph = m.theoretical_max_uph ?? (m.avg_cycle_s > 0 ? 3600 / m.avg_cycle_s : 0)
                const isExpanded = expanded.has(r.job_id)
                const run = runCache.current.get(r.job_id)
                return (
                  <React.Fragment key={r.job_id}>
                    <tr className="row-hover border-b border-ink-800/50">
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={selected.has(r.job_id)}
                               onChange={() => toggleSelect(r.job_id)}
                               className="accent-gold cursor-pointer" />
                      </td>
                      <td className="px-3 py-2 font-mono text-gold">{r.job_id.slice(0, 8)}</td>
                      <td className="px-3 py-2 text-ink-300 max-w-[140px] truncate">{String(r.job.arena_env_args?.environment ?? '–')}</td>
                      <td className="px-3 py-2 text-ink-300">{String(r.job.policy_config?.robot ?? '–')}</td>
                      <td className="px-3 py-2 num text-ink-400">{r.job.num_episodes ?? '–'}</td>
                      <td className="px-3 py-2 num text-ink-400">{m.success_count ?? '–'}</td>
                      <td className="px-3 py-2 num text-success">{((m.success_rate ?? 0) * 100).toFixed(1)}%</td>
                      <td className="px-3 py-2 num text-ink-300">{(m.avg_cycle_s ?? 0).toFixed(2)}</td>
                      <td className="px-3 py-2 num text-gold">{(m.uph ?? 0).toFixed(1)}</td>
                      <td className="px-3 py-2 num text-ink-400">{tUph.toFixed(1)}</td>
                      <td className="px-3 py-2"><span className="chip chip-done">done</span></td>
                      <td className="px-3 py-2 text-ink-500 whitespace-nowrap">{new Date(r.timestamp * 1000).toLocaleString('zh-CN')}</td>
                      <td className="px-3 py-2">
                        <button className="btn-sm text-[10px]" onClick={() => toggleExpand(r)}>
                          {isExpanded ? '收起' : '单集'}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${r.job_id}-episodes`} className="border-b border-ink-800/50">
                        <td colSpan={13} className="bg-ink-950 px-4 py-2">
                          {run?.episodes && run.episodes.length > 0 ? (
                            <div className="flex flex-wrap gap-1 p-3">
                              {run.episodes.map((ep, i) => (
                                <div key={i}
                                     title={`#${ep.episode_index}: ${ep.success ? '✓' : '✗'} (${ep.termination_reason})`}
                                     className={`w-4 h-4 rounded-sm ${ep.success ? 'bg-success' : 'bg-fail/60'}`}
                                />
                              ))}
                            </div>
                          ) : (
                            <div className="text-ink-600 text-xs py-2 px-3">暂无单集数据</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
