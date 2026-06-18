import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchJobs, fetchConfigs, fetchResults, fetchWorkers, submitJob, cancelJob, streamLogs, reproduceJob } from './api'
import type { Job, JobResult, Worker, Configs, SubmitRequest } from './types'
import { useRouter } from './useRouter'
import DashboardView  from './components/DashboardView'
import SubmitView     from './components/SubmitView'
import JobsView       from './components/JobsView'
import ResultsView    from './components/ResultsView'
import WorkersView    from './components/WorkersView'
import StreamModal    from './components/StreamModal'
import LeaderboardView from './components/LeaderboardView'
import AnalysisView   from './components/AnalysisView'
import ArenaView      from './components/ArenaView'

export type ViewName = 'dashboard' | 'submit' | 'jobs' | 'results' | 'workers' | 'leaderboard' | 'analysis' | 'arena'

export default function App() {
  const { view, params, navigate, setParam } = useRouter()

  const [configs, setConfigs] = useState<Configs>({ environments: [], policy_types: [], example_job: {} as SubmitRequest })
  const [jobs, setJobs]       = useState<Job[]>([])
  const [results, setResults] = useState<JobResult[]>([])
  const [workers, setWorkers] = useState<Worker[]>([])
  const [logs, setLogs]       = useState<string[]>([])
  const [modalWorker, setModalWorker] = useState<number | null>(null)
  const unsubRef = useRef<(() => void) | null>(null)

  // selectedJobId lives in URL: /jobs?id=xxx
  const selectedJobId = view === 'jobs' ? (params.get('id') ?? null) : null

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
    unsubRef.current = streamLogs(
      jobId,
      (line) => setLogs(prev => [...prev.slice(-500), line]),
      () => { refreshJobs(); refreshResults() },
    )
  }, [setParam, refreshJobs, refreshResults])

  // Re-attach log stream when navigating back to /jobs?id=xxx
  useEffect(() => {
    if (view === 'jobs' && selectedJobId) {
      unsubRef.current?.()
      unsubRef.current = streamLogs(
        selectedJobId,
        (line) => setLogs(prev => [...prev.slice(-500), line]),
        () => { refreshJobs(); refreshResults() },
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, selectedJobId])

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (req: SubmitRequest) => {
    const job = await submitJob(req)
    await refreshJobs()
    navigate('jobs', { id: job.id })
  }

  const handleCancel = async (id: string) => {
    await cancelJob(id)
    refreshJobs()
  }

  const handleReproduce = async (jobId: string) => {
    await reproduceJob(jobId)
    await refreshJobs()
  }

  // Analysis: state for pre-selected run IDs (from ResultsView)
  const [analysisRunIds, setAnalysisRunIds] = useState<string[]>([])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'n' || e.key === 'N') navigate('submit')
      if (e.key === 'j' || e.key === 'J') navigate('jobs')
      if (e.key === 'w' || e.key === 'W') navigate('workers')
      if (e.key === 'l' || e.key === 'L') navigate('leaderboard')
      if (e.key === 'a' || e.key === 'A') navigate('analysis')
      if (e.key === 'r' || e.key === 'R') navigate('arena')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  // ── Derived ────────────────────────────────────────────────────────────────
  const activeJob     = jobs.find(j => j.status === 'running') ?? null
  const busyWorkers   = workers.filter(w => w.busy).length
  const onlineWorkers = workers.filter(w => w.online).length

  const NAV: { id: ViewName; label: string; icon: string }[] = [
    { id: 'dashboard',   label: '总览',    icon: 'fa-gauge-high' },
    { id: 'submit',      label: '提交任务', icon: 'fa-plus' },
    { id: 'jobs',        label: '任务队列', icon: 'fa-list-check' },
    { id: 'results',     label: '评测结果', icon: 'fa-chart-column' },
    { id: 'workers',     label: '集群',    icon: 'fa-server' },
    { id: 'leaderboard', label: '榜单',    icon: 'fa-trophy' },
    { id: 'analysis',    label: '分析',    icon: 'fa-chart-line' },
    { id: 'arena',       label: '竞技场',  icon: 'fa-swords' },
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
        {view === 'submit' && (
          <SubmitView configs={configs} onSubmit={handleSubmit} />
        )}
        {view === 'jobs' && (
          <JobsView
            jobs={jobs} selectedId={selectedJobId} logs={logs}
            onSelect={selectJob} onCancel={handleCancel}
            onNavigate={navigate}
            onReproduce={handleReproduce}
          />
        )}
        {view === 'results' && (
          <ResultsView results={results} onNavigateAnalysis={(runIds) => { setAnalysisRunIds(runIds); navigate('analysis') }} />
        )}
        {view === 'workers' && (
          <WorkersView workers={workers} onOpenModal={setModalWorker} onRefresh={refreshWorkers} />
        )}
        {view === 'leaderboard' && (
          <LeaderboardView />
        )}
        {view === 'analysis' && (
          <AnalysisView initialRunIds={analysisRunIds} />
        )}
        {view === 'arena' && (
          <ArenaView />
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
        <span><kbd className="kbd">N</kbd> 新建</span>
        <span><kbd className="kbd">J</kbd> 队列</span>
        <span><kbd className="kbd">W</kbd> 集群</span>
        <span><kbd className="kbd">L</kbd> 榜单</span>
        <span><kbd className="kbd">A</kbd> 分析</span>
        <span><kbd className="kbd">R</kbd> 竞技场</span>
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
