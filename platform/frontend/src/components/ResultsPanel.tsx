import type { EvalResult } from '../types'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

interface Props { results: EvalResult[] }

export default function ResultsPanel({ results }: Props) {
  if (!results.length) return (
    <div className="p-4 text-center text-gray-600 text-xs mt-8">暂无历史结果</div>
  )

  const chartData = results.slice(0, 10).reverse().map(r => ({
    name: `${r.robot.slice(0, 8)}`,
    成功率: Math.round(r.success_rate * 100),
    UPH: r.uph,
  }))

  return (
    <div className="p-3">
      <div className="text-xs text-gray-500 mb-3 font-semibold tracking-wider">历史结果 ({results.length})</div>

      {/* Chart */}
      <div className="mb-4">
        <div className="text-xs text-gray-600 mb-1">成功率对比 (%)</div>
        <ResponsiveContainer width="100%" height={100}>
          <BarChart data={chartData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#6B7280' }} />
            <YAxis tick={{ fontSize: 9, fill: '#6B7280' }} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 11 }} />
            <Bar dataKey="成功率" fill="#10B981" radius={[2,2,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table */}
      <div className="space-y-1">
        {results.slice(0, 20).map((r, i) => (
          <div key={i} className="bg-gray-900 rounded p-2 text-xs">
            <div className="flex justify-between mb-1">
              <span className="text-gray-400 font-semibold">{r.robot}</span>
              <span className="text-gray-600">{r.test_num} 轮</span>
            </div>
            <div className="text-gray-600 mb-1.5">{r.task} · {r.layout}</div>
            <div className="grid grid-cols-3 gap-1 text-center">
              <div>
                <div className="text-green-400 font-bold">{(r.success_rate * 100).toFixed(0)}%</div>
                <div className="text-gray-600" style={{fontSize:'9px'}}>成功率</div>
              </div>
              <div>
                <div className="text-blue-400 font-bold">{r.uph.toFixed(1)}</div>
                <div className="text-gray-600" style={{fontSize:'9px'}}>UPH</div>
              </div>
              <div>
                <div className="text-yellow-400 font-bold">{r.avg_cycle_seconds.toFixed(0)}s</div>
                <div className="text-gray-600" style={{fontSize:'9px'}}>均值</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
