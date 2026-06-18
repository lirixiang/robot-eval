import { useState, useEffect, useCallback } from 'react'
import { createMatch, fetchMatches, fetchArenaLeaderboard, fetchArenaEnvs } from '../api'
import type { Match, EloEntry } from '../types'
import { DEFAULT_ENVS } from '../constants'

function EloBar({ rating, rd, ciLow, ciHigh }: { rating: number; rd: number; ciLow?: number; ciHigh?: number }) {
  const color = rating >= 1600 ? '#10b981' : rating >= 1400 ? '#d4a857' : '#6b7280'
  const lo = ciLow  != null ? Math.round(ciLow)  : Math.round(rating - 2 * rd)
  const hi = ciHigh != null ? Math.round(ciHigh) : Math.round(rating + 2 * rd)
  return (
    <div className="flex items-center gap-2">
      <span className="num text-sm font-semibold" style={{ color }}>{Math.round(rating)}</span>
      <span className="text-[11px] text-ink-500">[{lo}, {hi}]</span>
    </div>
  )
}

function MatchStatusBadge({ status, winner }: { status: string; winner: string | null }) {
  if (status === 'done') {
    const label = winner === 'draw' ? 'Draw' : winner === 'a' ? 'A Wins' : winner === 'b' ? 'B Wins' : 'Done'
    const color = winner === 'draw' ? 'text-ink-400'
                : winner == null   ? 'text-ink-500'
                : 'text-green-400'
    return <span className={`text-[11px] num ${color}`}>{label}</span>
  }
  if (status === 'running') return <span className="text-[11px] text-gold">Running</span>
  return <span className="text-[11px] text-ink-500">Pending</span>
}

export default function ArenaView() {
  const [envs, setEnvs]         = useState<string[]>([])
  const [matches, setMatches]   = useState<Match[]>([])
  const [leaderboard, setLb]    = useState<EloEntry[]>([])
  const [selectedEnv, setEnv]   = useState('lift_object')
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)

  // New match form state
  const [modelA, setModelA]           = useState('')
  const [modelB, setModelB]           = useState('')
  const [mode, setMode]               = useState<'direct' | 'swiss' | 'round_robin'>('direct')
  const [isBlind, setIsBlind]         = useState(false)
  const [numEpisodes, setNumEpisodes] = useState(10)
  const [submitting, setSubmitting]   = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [ms, lb] = await Promise.all([
        fetchMatches({ env_name: selectedEnv }),
        fetchArenaLeaderboard(selectedEnv),
      ])
      setMatches(ms)
      setLb(lb)
    } catch {
      // silently ignore — backend may not have arena routes yet
    } finally {
      setLoading(false)
    }
  }, [selectedEnv])

  useEffect(() => {
    fetchArenaEnvs().then(e => {
      if (e.length > 0) {
        setEnvs(e)
        if (!e.includes(selectedEnv)) setEnv(e[0])
      }
    }).catch(() => {
      // Fall back to default envs list — backend arena routes may not be live yet
      setEnvs([...DEFAULT_ENVS])
    })
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  const displayEnvs = envs.length > 0 ? envs : DEFAULT_ENVS

  const handleCreateMatch = async () => {
    if (!modelA || !modelB) return
    setSubmitting(true)
    setError(null)
    try {
      await createMatch({
        env_name: selectedEnv,
        model_a: modelA,
        model_b: modelB,
        mode,
        is_blind: isBlind,
        num_episodes: numEpisodes,
        arena_env_args: { environment: selectedEnv },
      })
      setModelA('')
      setModelB('')
      await refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full overflow-hidden flex gap-4 p-4">
      {/* Left: new match form */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-4">
        <div className="bg-ink-900 rounded-lg border border-ink-700 p-4 space-y-3">
          <div className="text-sm font-semibold text-ink-200 flex items-center gap-2">
            <i className="fas fa-swords text-gold text-[11px]" />
            新对战
          </div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">环境</label>
            <select
              value={selectedEnv}
              onChange={e => setEnv(e.target.value)}
              className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500"
            >
              {displayEnvs.map(e => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">模型 A</label>
            <input
              value={modelA}
              onChange={e => setModelA(e.target.value)}
              placeholder="pi0, zero_action, ..."
              className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500"
            />
          </div>

          <div>
            <label className="text-[11px] text-ink-500 block mb-1">模型 B</label>
            <input
              value={modelB}
              onChange={e => setModelB(e.target.value)}
              placeholder="pi0.5, rsl_rl, ..."
              className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500"
            />
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[11px] text-ink-500 block mb-1">模式</label>
              <select
                value={mode}
                onChange={e => setMode(e.target.value as typeof mode)}
                className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500"
              >
                <option value="direct">直接对战</option>
                <option value="swiss">瑞士制</option>
                <option value="round_robin">循环赛</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">Episodes</label>
              <input
                type="number"
                value={numEpisodes}
                min={1}
                max={100}
                onChange={e => setNumEpisodes(Number(e.target.value))}
                className="w-16 bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isBlind}
              onChange={e => setIsBlind(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-ink-300">盲测模式</span>
          </label>

          {error && (
            <div className="text-red-400 text-[11px] break-all">{error}</div>
          )}

          <button
            onClick={handleCreateMatch}
            disabled={submitting || !modelA || !modelB}
            className="w-full py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm rounded transition-colors"
          >
            {submitting ? '提交中…' : '发起对战'}
          </button>
        </div>

        {/* Info card */}
        <div className="bg-ink-900 rounded-lg border border-ink-800 p-3 text-[11px] text-ink-500 space-y-1.5">
          <div className="text-ink-400 font-medium mb-1">竞技场说明</div>
          <div>• Elo 评分基于 Glicko-2 算法</div>
          <div>• 盲测模式下对手模型名称将隐藏</div>
          <div>• 结果每 5 秒自动刷新</div>
        </div>
      </div>

      {/* Center: match list */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-ink-200">
            对战记录
            {matches.length > 0 && (
              <span className="ml-2 text-[11px] text-ink-500 font-normal">({matches.length})</span>
            )}
          </span>
          <button
            onClick={refresh}
            className="text-[11px] text-ink-500 hover:text-ink-300 flex items-center gap-1"
          >
            <i className="fas fa-rotate-right text-[10px]" />
            刷新
          </button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {!loading && matches.length === 0 ? (
            <div className="text-center text-ink-500 text-sm py-12">
              <i className="fas fa-swords text-2xl block mb-3 opacity-20" />
              暂无对战记录
              <div className="text-[11px] mt-1 text-ink-600">发起第一场对战</div>
            </div>
          ) : (
            matches.map(m => (
              <div
                key={m.id}
                className="bg-ink-900 rounded-lg border border-ink-800 px-3 py-2 flex items-center gap-3"
              >
                <div className="w-24 font-mono text-[11px] text-ink-600 truncate">{m.id.slice(0, 8)}</div>
                <div className="flex-1 flex items-center gap-2 min-w-0">
                  <span className="text-sm text-ink-200 truncate">{m.model_a}</span>
                  <span className="text-ink-600 text-xs">vs</span>
                  {m.model_b === '?' ? (
                    <span className="text-sm text-ink-500 italic">?</span>
                  ) : (
                    <span className="text-sm text-ink-200 truncate">{m.model_b}</span>
                  )}
                </div>
                <div className="text-[11px] text-ink-500 hidden xl:block">{m.env_name}</div>
                <MatchStatusBadge status={m.status} winner={m.winner} />
                {m.is_blind && (
                  <span className="text-[10px] text-violet-400 border border-violet-800/40 rounded px-1 flex-shrink-0">盲</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Elo leaderboard */}
      <div className="w-72 flex-shrink-0 flex flex-col">
        <div className="text-sm font-semibold text-ink-200 mb-3 flex items-center gap-2">
          <i className="fas fa-ranking-star text-gold text-[11px]" />
          Elo 排名
          <span className="text-[11px] text-ink-500 font-normal">· {selectedEnv}</span>
        </div>
        <div className="flex-1 bg-ink-900 rounded-lg border border-ink-700 overflow-hidden">
          {!loading && leaderboard.length === 0 ? (
            <div className="text-center text-ink-500 text-sm py-12">
              <i className="fas fa-chart-bar text-2xl block mb-3 opacity-20" />
              暂无排名数据
              <div className="text-[11px] mt-1 text-ink-600">完成对战后自动生成</div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-800 text-ink-500 text-[11px]">
                  <th className="text-left px-3 py-2 font-normal">#</th>
                  <th className="text-left px-3 py-2 font-normal">模型</th>
                  <th className="text-right px-3 py-2 font-normal">分数</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((e, i) => (
                  <tr key={e.model_name} className="border-b border-ink-800 last:border-0 hover:bg-ink-800/30 transition-colors">
                    <td className="px-3 py-2 text-ink-500 text-[12px]">{i + 1}</td>
                    <td className="px-3 py-2 text-ink-200 truncate max-w-[120px]">{e.model_name}</td>
                    <td className="px-3 py-2 text-right">
                      <EloBar rating={e.rating} rd={e.rd} ciLow={e.ci_low} ciHigh={e.ci_high} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
