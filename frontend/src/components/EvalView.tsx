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

export default function EvalView({
  jobs, results, configs, logs, selectedJobId,
  onSelectJob, onSubmit, onCancel, onReproduce,
  onNavigateAnalysis, rightTab, onRightTabChange,
}: Props) {
  return (
    <div className="h-full flex overflow-hidden">
      {/* Left: submit form */}
      <div className="w-72 flex-shrink-0 border-r border-ink-800 overflow-y-auto">
        <SubmitView configs={configs} onSubmit={onSubmit} />
      </div>

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
              onNavigate={() => {/* submit form is always visible on the left — no nav needed */}}
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
