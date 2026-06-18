// frontend/src/components/AnalysisView.tsx
import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { fetchCompare, fetchTrend } from '../api'
import type { AnalysisCompare, TrendPoint } from '../types'

interface Props {
  initialRunIds?: string[]   // pre-selected from ResultsView
}

export default function AnalysisView({ initialRunIds = [] }: Props) {
  const [runInput, setRunInput] = useState(initialRunIds.join(','))
  const [compare, setCompare]   = useState<AnalysisCompare | null>(null)
  const [trendModel, setTrendModel] = useState('')
  const [trendEnv, setTrendEnv]     = useState('lift_object')
  const [trendDays, setTrendDays]   = useState(30)
  const [trendData, setTrendData]   = useState<TrendPoint[]>([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const runCompare = async () => {
    const ids = runInput.split(',').map(s => s.trim()).filter(Boolean)
    if (!ids.length) return
    setLoading(true); setError(null)
    try {
      const data = await fetchCompare(ids)
      setCompare(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const runTrend = async () => {
    if (!trendModel || !trendEnv) return
    setLoading(true); setError(null)
    try {
      const data = await fetchTrend(trendModel, trendEnv, trendDays)
      setTrendData(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-5 space-y-6">
      <h2 className="text-white font-semibold text-lg">分析</h2>

      {/* Compare section */}
      <section className="bg-ink-900 rounded-lg p-4 border border-ink-700 space-y-3">
        <div className="text-sm font-medium text-ink-200">多 Run 对比</div>
        <div className="flex gap-2">
          <input
            value={runInput}
            onChange={e => setRunInput(e.target.value)}
            placeholder="Run ID，逗号分隔"
            className="flex-1 bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500"
          />
          <button onClick={runCompare} disabled={loading}
                  className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded disabled:opacity-50">
            {loading ? '加载中…' : '对比'}
          </button>
        </div>

        {compare && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400 text-left border-b border-ink-700">
                  <th className="pb-2 pr-4">指标</th>
                  {compare.runs.map(r => (
                    <th key={r.id} className="pb-2 pr-4 font-mono text-[11px]">{r.id}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(compare.metrics).map(([metric, vals]) => (
                  <tr key={metric} className="border-b border-ink-800">
                    <td className="py-1.5 pr-4 text-ink-300">{metric}</td>
                    {compare.runs.map(r => {
                      const v = vals[r.id]
                      const isBest = vals['best'] === r.id
                      return (
                        <td key={r.id} className={`py-1.5 pr-4 font-mono ${isBest ? 'text-green-400 font-semibold' : 'text-ink-200'}`}>
                          {typeof v === 'number' ? v.toFixed(3) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Trend section */}
      <section className="bg-ink-900 rounded-lg p-4 border border-ink-700 space-y-3">
        <div className="text-sm font-medium text-ink-200">趋势分析</div>
        <div className="flex gap-2 flex-wrap">
          <input value={trendModel} onChange={e => setTrendModel(e.target.value)}
                 placeholder="模型名称" className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500 w-40" />
          <input value={trendEnv} onChange={e => setTrendEnv(e.target.value)}
                 placeholder="环境名称" className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500 w-40" />
          <select value={trendDays} onChange={e => setTrendDays(Number(e.target.value))}
                  className="bg-ink-800 border border-ink-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
            <option value={7}>7天</option>
            <option value={30}>30天</option>
            <option value={90}>90天</option>
          </select>
          <button onClick={runTrend} disabled={loading}
                  className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-sm rounded disabled:opacity-50">
            查询
          </button>
        </div>

        {trendData.length > 0 && (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendData.map(p => ({
              ...p,
              time: new Date(p.finished_at * 1000).toLocaleDateString(),
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" />
              <XAxis dataKey="time" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#0d1119', border: '1px solid #1e2433', color: '#e5e7eb' }} />
              <Legend />
              <Line type="monotone" dataKey="success_rate" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}

        {trendData.length === 0 && !loading && trendModel && (
          <div className="text-ink-500 text-sm text-center py-4">暂无数据</div>
        )}
      </section>

      {error && (
        <div className="bg-red-900/20 border border-red-800/40 rounded p-3 text-red-400 text-sm">{error}</div>
      )}
    </div>
  )
}
