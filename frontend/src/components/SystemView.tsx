import { useState } from 'react'
import WorkersView  from './WorkersView'
import TemplatesView from './TemplatesView'
import type { Worker } from '../types'

interface Props {
  workers:     Worker[]
  onOpenModal: (id: number) => void
  onRefresh:   () => void
}

type Tab = 'workers' | 'templates'

export default function SystemView({ workers, onOpenModal, onRefresh }: Props) {
  const [tab, setTab] = useState<Tab>('workers')

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
        {([
          { id: 'workers'   as Tab, label: '集群',  icon: 'fa-server'    },
          { id: 'templates' as Tab, label: '模板',  icon: 'fa-file-code' },
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
        {tab === 'workers'   && <WorkersView  workers={workers} onOpenModal={onOpenModal} onRefresh={onRefresh} />}
        {tab === 'templates' && <TemplatesView />}
      </div>
    </div>
  )
}
