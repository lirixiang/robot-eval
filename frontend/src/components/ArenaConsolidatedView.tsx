import { useState } from 'react'
import ArenaView       from './ArenaView'
import LeaderboardView from './LeaderboardView'
import AnalysisView    from './AnalysisView'

interface Props {
  initialAnalysisRunIds?: string[]
}

type Tab = 'battle' | 'leaderboard' | 'analysis'

export default function ArenaConsolidatedView({ initialAnalysisRunIds = [] }: Props) {
  const [tab, setTab] = useState<Tab>(initialAnalysisRunIds.length > 0 ? 'analysis' : 'battle')

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
        {([
          { id: 'battle'      as Tab, label: '对战',  icon: 'fa-swords'     },
          { id: 'leaderboard' as Tab, label: '榜单',  icon: 'fa-trophy'     },
          { id: 'analysis'    as Tab, label: '分析',  icon: 'fa-chart-line' },
        ] as const).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-gold text-white'
                : 'border-transparent text-ink-400 hover:text-ink-200'
            }`}
          >
            <i className={`fas ${t.icon} text-[11px]`} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'battle'      && <ArenaView />}
        {tab === 'leaderboard' && <LeaderboardView />}
        {tab === 'analysis'    && <AnalysisView initialRunIds={initialAnalysisRunIds} />}
      </div>
    </div>
  )
}
