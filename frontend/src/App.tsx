import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchJobs, fetchConfigs, fetchResults, fetchWorkers, submitJob, cancelJob, streamLogs, reproduceJob } from './api'
import type { Job, JobResult, Worker, Configs, SubmitRequest } from './types'
import { useRouter } from './useRouter'
import DashboardView  from './components/DashboardView'
import EvalView               from './components/EvalView'
import ArenaConsolidatedView  from './components/ArenaConsolidatedView'
import SystemView             from './components/SystemView'
import StreamModal    from './components/StreamModal'

export type ViewName = 'dashboard' | 'eval' | 'arena' | 'system'

export default function App() {
  const { view, params, navigate, setParam } = useRouter()

  const [configs, setConfigs] = useState<Configs>({ environments: [], policy_types: [], example_job: {} as SubmitRequest })
  const [jobs, setJobs]       = useState<Job[]>([])
  const [results, setResults] = useState<JobResult[]>([])
  const [workers, setWorkers] = useState<Worker[]>([])
  const [logs, setLogs]       = useState<string[]>([])
  const [modalWorker, setModalWorker] = useState<number | null>(null)
  const [analysisRunIds, setAnalysisRunIds] = useState<string[]>([])
  const [evalRightTab, setEvalRightTab] = useState<'queue' | 'results'>('queue')
  const unsubRef = useRef<(() => void) | null>(null)
  const justSelectedJobRef = useRef(false)

  // ── Data fetching ──────────────────────────────────────────────────────────
  const refreshJobs    = useCallback(() => fetchJobs().then(setJobs), [])
  const refreshResults = useCallback(() => fetchResults().then(setResults), [])
  const refreshWorkers = useCallback(() => fetchWorkers().then(setWorkers).catch(() => {}), [])

  useEffect(() => {
    fetchConfigs().then(setConfigs).catch(() => {})
    refreshJobs()
    refreshResults()
    refreshWorkers()
    const t = setInterval(() => { refreshJobs(); refreshWorkers() }, 3000)
    return () => clearInterval(t)
  }, [refreshJobs, refreshResults, refreshWorkers])

  // ── Log streaming ──────────────────────────────────────────────────────────
  const selectJob = useCallback((jobId: string) => {
    setParam('id', jobId)
    setLogs([])
    unsubRef.current?.()
    justSelectedJobRef.current = true
    unsubRef.current = streamLogs(
      jobId,
      (line) => setLogs(prev => [...prev.slice(-500), line]),
      () => { refreshJobs(); refreshResults() },
    )
  }, [setParam, refreshJobs, refreshResults])

  // Re-attach log stream when navigating back to /eval?id=xxx
  useEffect(() => {
    if (view === 'eval' && params.get('id')) {
      if (justSelectedJobRef.current) {
        justSelectedJobRef.current = false
        return
      }
      const id = params.get('id')!
      unsubRef.current?.()
      unsubRef.current = streamLogs(
        id,
        (line) => setLogs(prev => [...prev.slice(-500), line]),
        () => { refreshJobs(); refreshResults() },
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, params.get('id')])

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (req: SubmitRequest) => {
    const job = await submitJob(req)
    await refreshJobs()
    navigate('eval')
    setEvalRightTab('queue')
    selectJob(job.id)
  }

  const handleCancel = async (id: string) => {
    await cancelJob(id)
    refreshJobs()
  }

  const handleReproduce = async (jobId: string) => {
    await reproduceJob(jobId)
    await refreshJobs()
  }

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'd' || e.key === 'D') navigate('dashboard')
      if (e.key === 'e' || e.key === 'E') navigate('eval')
      if (e.key === 'c' || e.key === 'C') navigate('arena')
      if (e.key === 's' || e.key === 'S') navigate('system')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  // ── Derived ────────────────────────────────────────────────────────────────
  const activeJob     = jobs.find(j => j.status === 'running') ?? null
  const busyWorkers   = workers.filter(w => w.busy).length
  const onlineWorkers = workers.filter(w => w.online).length

  const NAV: { id: ViewName; label: string; icon: string }[] = [
    { id: 'dashboard', label: '总览', icon: 'fa-gauge-high' },
    { id: 'eval',      label: '评测', icon: 'fa-list-check' },
    { id: 'arena',     label: '竞技', icon: 'fa-swords'     },
    { id: 'system',    label: '系统', icon: 'fa-server'     },
  ]

  // ── Aggregate metrics ──────────────────────────────────────────────────────
  const completedResults = results.filter(r => r.metrics?.success_rate != null)
  const avgSr    = completedResults.length ? completedResults.reduce((s, r) => s + (r.metrics.success_rate ?? 0), 0) / completedResults.length : 0
  const bestUph  = completedResults.length ? Math.max(...completedResults.map(r => r.metrics.uph ?? 0)) : 0
  const avgCycle = completedResults.length ? completedResults.reduce((s, r) => s + (r.metrics.avg_cycle_s ?? 0), 0) / completedResults.length : 0

  return (
    <div className="h-screen flex flex-col bg-ink-950 overflow-hidden font-sans">

      {/* ── HEADER ─────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 border-b border-ink-800"
              style={{ background: 'linear-gradient(180deg,#0d1119 0%,#0a0d14 100%)' }}>
        {/* Main nav row */}
        <div className="flex items-center h-12 px-5 gap-4">
          {/* Brand */}
          <div className="flex items-center gap-2.5 pr-4 border-r border-ink-800">
            <div className="w-7 h-7 rounded-md flex items-center justify-center text-white"
                 style={{ background: 'linear-gradient(135deg,#10b981 0%,#059669 100%)' }}>
              <i className="fas fa-robot text-[11px]" />
            </div>
            <div className="leading-tight">
              <div className="text-[13px] font-semibold tracking-wide text-white">
                RoboEval <span className="text-gold font-normal">评测</span>
              </div>
              <div className="text-[10px] text-ink-500 -mt-0.5 tracking-widest">ISAAC LAB · RAY CLUSTER</div>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-0.5">
            {NAV.map(n => (
              <button key={n.id} className={`nav-btn ${view === n.id ? 'active' : ''}`}
                      onClick={() => navigate(n.id)}>
                <i className={`fas ${n.icon} mr-1.5 text-[11px]`} />
                {n.label}
              </button>
            ))}
          </nav>

          <div className="flex-1" />

          {/* Cluster status */}
          <div className="flex items-center gap-4 text-[11px]">
            <div className="flex items-center gap-1.5">
              <span className="pulse-dot relative">
                <span className={`dot ${onlineWorkers > 0 ? 'bg-success' : 'bg-ink-500'}`} />
              </span>
              <span className="text-ink-300">{onlineWorkers > 0 ? 'Ray 在线' : 'Ray 离线'}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="dot bg-gold" />
              <span className="num text-ink-200">{onlineWorkers}</span>
              <span className="text-ink-500">GPU 就绪</span>
            </div>
            {busyWorkers > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="dot bg-violet" />
                <span className="num text-ink-200">{busyWorkers}</span>
                <span className="text-ink-500">运行中</span>
              </div>
            )}
            <div className="w-px h-4 bg-ink-700" />
            <div className="w-6 h-6 rounded-full bg-ink-700 flex items-center justify-center text-[10px] text-ink-300"
                 style={{ boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.04)' }}>
              RX
            </div>
          </div>
        </div>

        {/* Status strip */}
        <div className="flex items-center h-8 px-5 gap-6 border-t border-ink-800 text-[11px] num">
          <div className="flex items-center gap-1.5">
            <span className="text-ink-500">成功率</span>
            <span className="text-success">{(avgSr * 100).toFixed(1)}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-ink-500">最佳 UPH</span>
            <span className="text-gold">{bestUph.toFixed(0)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-ink-500">已完成</span>
            <span className="text-ink-200">{completedResults.length}</span>
            <span className="text-ink-500">轮</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-ink-500">平均耗时</span>
            <span className="text-ink-200">{avgCycle.toFixed(1)}</span>
            <span className="text-ink-500">s</span>
          </div>
          <div className="flex-1" />
          <span className="text-ink-600">Isaac Sim 6.0 · Isaac Lab 3.0 · Ray 2.9</span>
        </div>
      </header>

      {/* ── VIEWS ──────────────────────────────────────────────────────── */}
      <main className="flex-1 min-h-0">
        {view === 'dashboard' && (
          <DashboardView
            jobs={jobs} results={results} workers={workers}
            activeJob={activeJob} logs={logs}
            onSelectJob={selectJob} onOpenModal={setModalWorker}
            onNavigate={navigate}
            onQuickSubmit={handleSubmit}
            configs={configs}
          />
        )}
        {view === 'eval' && (
          <EvalView
            jobs={jobs}
            results={results}
            configs={configs}
            logs={logs}
            selectedJobId={view === 'eval' ? (params.get('id') ?? null) : null}
            onSelectJob={selectJob}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
            onReproduce={handleReproduce}
            onNavigateAnalysis={(runIds) => { setAnalysisRunIds(runIds); navigate('arena'); setTimeout(() => setAnalysisRunIds([]), 100) }}
            rightTab={evalRightTab}
            onRightTabChange={setEvalRightTab}
          />
        )}
        {view === 'arena' && (
          <ArenaConsolidatedView initialAnalysisRunIds={analysisRunIds} />
        )}
        {view === 'system' && (
          <SystemView workers={workers} onOpenModal={setModalWorker} onRefresh={refreshWorkers} />
        )}
      </main>

      {/* ── FOOTER ─────────────────────────────────────────────────────── */}
      <footer className="h-8 border-t border-ink-800 flex items-center px-5 text-[11px] text-ink-500 gap-4 flex-shrink-0"
              style={{ background: 'linear-gradient(180deg,#0d1119 0%,#0a0d14 100%)' }}>
        <span className="flex items-center gap-1.5">
          <span className={`dot ${onlineWorkers > 0 ? 'bg-success' : 'bg-ink-600'}`} />
          {onlineWorkers > 0 ? 'Ray 集群在线' : 'Ray 未连接'}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="dot bg-violet" />
          {workers.length} Actors
        </span>
        <span>isaaclab_arena</span>
        <div className="flex-1" />
        <span><kbd className="kbd">D</kbd> 总览</span>
        <span><kbd className="kbd">E</kbd> 评测</span>
        <span><kbd className="kbd">C</kbd> 竞技</span>
        <span><kbd className="kbd">S</kbd> 系统</span>
        <span className="text-ink-600">RoboEval · Ray + isaaclab_arena</span>
      </footer>

      {/* ── STREAM MODAL ────────────────────────────────────────────────── */}
      {modalWorker !== null && (
        <StreamModal
          workerId={modalWorker}
          worker={workers.find(w => w.id === modalWorker) ?? null}
          activeJob={activeJob}
          onClose={() => setModalWorker(null)}
        />
      )}
    </div>
  )
}
