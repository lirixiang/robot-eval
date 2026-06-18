import { useRef, useState, useCallback } from 'react'
import JobsView    from './JobsView'
import ResultsView from './ResultsView'
import SubmitView  from './SubmitView'
import type { Configs, Job, JobResult, SubmitRequest } from '../types'

type RightTab = 'queue' | 'results'

interface Props {
  jobs:                 Job[]
  results:              JobResult[]
  configs:              Configs
  logs:                 string[]
  selectedJobId:        string | null
  onSelectJob:          (id: string) => void
  onSubmit:             (r: SubmitRequest) => Promise<void>
  onCancel:             (id: string) => void
  onReproduce?:         (id: string) => Promise<void>
  onNavigateAnalysis:   (runIds: string[]) => void
  rightTab:             RightTab
  onRightTabChange:     (t: RightTab) => void
}

/** Drag-handle divider — call onDrag(deltaX) on mousemove */
function Divider({ onDrag }: { onDrag: (dx: number) => void }) {
  const dragging = useRef(false)
  const last     = useRef(0)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true
    last.current = e.clientX
    e.preventDefault()

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      onDrag(ev.clientX - last.current)
      last.current = ev.clientX
    }
    const onUp = () => { dragging.current = false; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [onDrag])

  return (
    <div
      onMouseDown={onMouseDown}
      className="w-1 flex-shrink-0 bg-ink-800 hover:bg-green-600/60 active:bg-green-500 cursor-col-resize transition-colors select-none"
    />
  )
}

export default function EvalView({
  jobs, results, configs, logs, selectedJobId,
  onSelectJob, onSubmit, onCancel, onReproduce,
  onNavigateAnalysis, rightTab, onRightTabChange,
}: Props) {
  const [leftW, setLeftW] = useState(760)   // SubmitView has internal 2-column layout

  const clampLeft = (w: number) => Math.max(480, Math.min(1100, w))

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left: submit form (resizable) */}
      <div style={{ width: leftW }} className="flex-shrink-0 overflow-y-auto">
        <SubmitView configs={configs} onSubmit={onSubmit} />
      </div>

      <Divider onDrag={dx => setLeftW(w => clampLeft(w + dx))} />

      {/* Right: tab panel */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Tab bar */}
        <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
          {([
            { id: 'queue'   as RightTab, label: '任务队列', icon: 'fa-list-check'   },
            { id: 'results' as RightTab, label: '评测结果', icon: 'fa-chart-column' },
          ] as const).map(t => (
            <button
              key={t.id}
              onClick={() => onRightTabChange(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors ${
                rightTab === t.id
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
          {rightTab === 'queue' && (
            <JobsView
              jobs={jobs}
              selectedId={selectedJobId}
              logs={logs}
              onSelect={onSelectJob}
              onCancel={onCancel}
              onNavigate={() => {/* submit form always visible on left */}}
              onReproduce={onReproduce}
            />
          )}
          {rightTab === 'results' && (
            <ResultsView
              results={results}
              onNavigateAnalysis={onNavigateAnalysis}
            />
          )}
        </div>
      </div>
    </div>
  )
}
