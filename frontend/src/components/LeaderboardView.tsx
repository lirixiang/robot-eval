import { useState, useEffect } from 'react'
import { fetchLeaderboard } from '../api'
import type { Leaderboard, LeaderboardRow } from '../types'

const MEDAL = ['🥇', '🥈', '🥉']

function RankBadge({ rank }: { rank: number }) {
  if (rank <= 3) return <span className="text-base">{MEDAL[rank - 1]}</span>
  return <span className="num text-ink-400 text-[12px]">#{rank}</span>
}

function SrBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#d4a857' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="level-bar w-20 flex-shrink-0">
        <div className="level-fill transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="num text-[12px]" style={{ color }}>{pct.toFixed(1)}%</span>
    </div>
  )
}

function TopCard({ row, rank }: { row: LeaderboardRow; rank: number }) {
  const isFirst = rank === 1
  const borderColor = rank === 1 ? 'rgba(212,168,87,.6)' : rank === 2 ? 'rgba(125,211,252,.4)' : 'rgba(167,139,250,.4)'
  const labelColor  = rank === 1 ? '#d4a857' : rank === 2 ? '#7dd3fc' : '#a78bfa'
  return (
    <div className="form-section flex-1" style={{ borderColor }}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-2xl">{MEDAL[rank - 1]}</span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-white truncate">{row.model_name || '–'}</div>
          <div className="text-[11px] text-ink-400 truncate">{row.submitter || '–'}</div>
        </div>
        {isFirst && (
          <span className="chip chip-done text-[10px] flex-shrink-0">冠军</span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-ink-850 rounded-md p-2">
          <div className="num text-[15px] font-bold text-success">{(row.success_rate * 100).toFixed(1)}%</div>
          <div className="text-[9px] text-ink-500 mt-0.5">成功率</div>
        </div>
        <div className="bg-ink-850 rounded-md p-2">
          <div className="num text-[15px] font-bold" style={{ color: labelColor }}>{row.uph.toFixed(0)}</div>
          <div className="text-[9px] text-ink-500 mt-0.5">UPH</div>
        </div>
        <div className="bg-ink-850 rounded-md p-2">
          <div className="num text-[15px] font-bold text-ink-200">{row.avg_cycle_s.toFixed(1)}s</div>
          <div className="text-[9px] text-ink-500 mt-0.5">avg_cycle</div>
        </div>
      </div>
      {row.description && (
        <div className="mt-2 text-[11px] text-ink-500 line-clamp-2">{row.description}</div>
      )}
    </div>
  )
}

export default function LeaderboardView() {
  const [board, setBoard]   = useState<Leaderboard | null>(null)
  const [envFilter, setEnvFilter] = useState<string>('all')
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    const load = () => {
      setLoading(true)
      fetchLeaderboard(envFilter === 'all' ? undefined : envFilter)
        .then(setBoard)
        .catch(() => {})
        .finally(() => setLoading(false))
    }
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [envFilter])

  const allEnvs = board?.environments ?? []
  const groups  = board?.groups ?? []
  const total   = board?.total_submissions ?? 0

  // Flat top-3 across all envs for podium (best by success_rate)
  const allRows: LeaderboardRow[] = groups.flatMap(g => g.rows)
  const top3 = [...allRows].sort((a, b) => b.success_rate - a.success_rate).slice(0, 3)

  return (
    <div className="overflow-y-auto p-5 space-y-5" style={{ height: 'calc(100vh - 84px)' }}>

      {/* Header */}
      <div className="flex items-center gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <i className="fas fa-trophy text-gold text-base" />
            公开榜单
          </h1>
          <p className="text-[11px] text-ink-500 mt-0.5">
            {total} 次提交 · 按成功率排名 · 每个模型取最佳成绩
          </p>
        </div>
        <div className="flex-1" />
        <div className="text-[11px] text-ink-500 flex items-center gap-1.5">
          <i className="fas fa-info-circle" />
          提交方式：设置 <code className="bg-ink-800 px-1 rounded text-gold">policy_server_url</code> 并运行评测
        </div>
      </div>

      {/* Podium — top 3 across all environments */}
      {top3.length > 0 && (
        <div className="space-y-2">
          <div className="tag text-ink-500">全局 TOP 3（所有环境）</div>
          <div className="flex gap-3">
            {top3.map((row, i) => <TopCard key={row.job_id} row={row} rank={i + 1} />)}
            {top3.length < 3 && Array.from({ length: 3 - top3.length }).map((_, i) => (
              <div key={i} className="flex-1 form-section opacity-30 flex items-center justify-center text-ink-600 text-[12px]">
                <span>待提交</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Env filter */}
      <div className="flex items-center gap-3">
        <span className="tag text-ink-500">按环境筛选</span>
        <div className="seg">
          <button className={`${envFilter === 'all' ? 'on' : ''}`} onClick={() => setEnvFilter('all')}>
            全部
          </button>
          {allEnvs.map(e => (
            <button key={e} className={envFilter === e ? 'on' : ''} onClick={() => setEnvFilter(e)}>
              {e.length > 18 ? e.slice(0, 16) + '…' : e}
            </button>
          ))}
        </div>
        {loading && <span className="spinner" />}
      </div>

      {/* Per-environment ranking tables */}
      {groups.length === 0 && !loading && (
        <div className="form-section text-center py-16 text-ink-600">
          <i className="fas fa-trophy text-3xl mb-3 block opacity-30" />
          <div className="text-[13px]">暂无榜单数据</div>
          <div className="text-[11px] mt-2">
            提交带有 <code className="bg-ink-800 px-1 rounded text-gold">policy_server_url</code> 的评测任务后，成绩将自动上榜
          </div>
          <div className="mt-4 p-3 bg-ink-900 rounded-lg text-left font-mono text-[11px] text-ink-400 max-w-md mx-auto">
            <div className="text-violet mb-1"># 1. 启动你的模型服务</div>
            <div className="text-success">python example_zero_action.py --port 7860</div>
            <div className="text-violet mt-2 mb-1"># 2. 提交时填入 Policy Server URL</div>
            <div className="text-gold">http://{'<your-host>'}:7860</div>
          </div>
        </div>
      )}

      {groups.map(group => (
        <div key={group.environment} className="form-section p-0 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-ink-800 flex items-center gap-3 grad-head">
            <i className="fas fa-cube text-sky2 text-[11px]" />
            <span className="text-[13px] font-semibold text-white">{group.environment}</span>
            <span className="chip chip-env text-[10px]">{group.rows.length} 个提交</span>
            <div className="flex-1" />
            <span className="text-[10px] text-ink-500">
              最佳成功率 <span className="text-success num font-semibold">
                {(Math.max(...group.rows.map(r => r.success_rate)) * 100).toFixed(1)}%
              </span>
            </span>
          </div>
          <table className="w-full text-[12px]">
            <thead className="text-ink-500 text-[10px] tracking-wider uppercase sticky top-0 bg-ink-950 z-10">
              <tr className="border-b border-ink-800">
                <th className="text-left font-normal px-4 py-2 w-12">排名</th>
                <th className="text-left font-normal px-2">模型</th>
                <th className="text-left font-normal px-2">提交方</th>
                <th className="text-left font-normal px-2 max-w-[200px]">描述</th>
                <th className="text-left font-normal px-2">成功率</th>
                <th className="text-right font-normal px-2">UPH</th>
                <th className="text-right font-normal px-2">avg_cycle</th>
                <th className="text-right font-normal px-2">轮次</th>
                <th className="text-right font-normal px-4">提交时间</th>
              </tr>
            </thead>
            <tbody>
              {group.rows.map((row) => (
                <tr key={row.job_id}
                    className={`row-hover border-b border-ink-800/50 ${row.rank === 1 ? 'bg-gold/[0.03]' : ''}`}>
                  <td className="px-4 py-2.5">
                    <RankBadge rank={row.rank} />
                  </td>
                  <td className="px-2 py-2.5">
                    <div className="font-semibold text-white">{row.model_name || <span className="text-ink-500">–</span>}</div>
                    <div className="text-[10px] text-ink-500 font-mono">{row.job_id}</div>
                  </td>
                  <td className="px-2 py-2.5 text-ink-300">{row.submitter || '–'}</td>
                  <td className="px-2 py-2.5 text-ink-400 max-w-[200px]">
                    <span className="truncate block">{row.description || '–'}</span>
                  </td>
                  <td className="px-2 py-2.5"><SrBar value={row.success_rate} /></td>
                  <td className="px-2 py-2.5 text-right num text-gold">{row.uph.toFixed(1)}</td>
                  <td className="px-2 py-2.5 text-right num text-ink-300">{row.avg_cycle_s.toFixed(2)}s</td>
                  <td className="px-2 py-2.5 text-right num text-ink-400">{row.num_episodes}</td>
                  <td className="px-4 py-2.5 text-right text-ink-500 whitespace-nowrap">
                    {row.timestamp ? new Date(row.timestamp * 1000).toLocaleDateString('zh-CN') : '–'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {/* How to submit guide */}
      <div className="form-section">
        <div className="tag text-ink-500 mb-3">如何提交到榜单</div>
        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
          <div className="bg-ink-900 rounded-lg p-4">
            <div className="w-7 h-7 rounded-full bg-gold/20 text-gold flex items-center justify-center text-[12px] font-bold mb-2">1</div>
            <div className="text-[12px] text-white font-medium mb-1">实现 PolicyBase</div>
            <div className="text-[11px] text-ink-500 leading-relaxed">继承 <code className="text-gold">PolicyBase</code>，实现 <code className="text-violet">reset()</code> 和 <code className="text-violet">act()</code> 方法。支持 pi0.5、RDT、RoboVLMs 等任何模型。</div>
          </div>
          <div className="bg-ink-900 rounded-lg p-4">
            <div className="w-7 h-7 rounded-full bg-sky2/20 text-sky2 flex items-center justify-center text-[12px] font-bold mb-2">2</div>
            <div className="text-[12px] text-white font-medium mb-1">启动 Policy Server</div>
            <div className="text-[11px] text-ink-500 leading-relaxed">调用 <code className="text-gold">serve(my_policy, port=7860)</code> 暴露 HTTP 接口。平台通过 <code className="text-violet">POST /act</code> 获取动作。</div>
          </div>
          <div className="bg-ink-900 rounded-lg p-4">
            <div className="w-7 h-7 rounded-full bg-success/20 text-success flex items-center justify-center text-[12px] font-bold mb-2">3</div>
            <div className="text-[12px] text-white font-medium mb-1">提交并上榜</div>
            <div className="text-[11px] text-ink-500 leading-relaxed">在提交页填入 Policy Server URL、模型名称和提交方。评测完成后自动出现在榜单。</div>
          </div>
        </div>
      </div>

    </div>
  )
}
