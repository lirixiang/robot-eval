import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchJobs, fetchConfigs, submitJob, cancelJob, fetchResults, streamLogs } from './api'
import type { Job, JobConfig, Configs, EvalResult } from './types'
import JobForm from './components/JobForm'
import JobList from './components/JobList'
import LogPanel from './components/LogPanel'
import ResultsPanel from './components/ResultsPanel'
import SimView from './components/SimView'

export default function App() {
  const [configs, setConfigs] = useState<Configs>({ tasks: [], layouts: [], robots: [] })
  const [jobs, setJobs] = useState<Job[]>([])
  const [results, setResults] = useState<EvalResult[]>([])
  const [selectedJob, setSelectedJob] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [tab, setTab] = useState<'jobs' | 'results'>('jobs')
  const unsubRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    fetchConfigs().then(setConfigs)
    refreshJobs()
    fetchResults().then(setResults)
    const t = setInterval(refreshJobs, 3000)
    return () => clearInterval(t)
  }, [])

  const refreshJobs = () => fetchJobs().then(setJobs)

  const handleSelect = useCallback((jobId: string) => {
    setSelectedJob(jobId)
    setLogs([])
    unsubRef.current?.()
    unsubRef.current = streamLogs(
      jobId,
      (line) => setLogs(prev => [...prev.slice(-500), line]),
      () => { refreshJobs(); fetchResults().then(setResults) }
    )
  }, [])

  const handleSubmit = async (cfg: JobConfig) => {
    const job = await submitJob(cfg)
    await refreshJobs()
    handleSelect(job.id)
    setTab('jobs')
  }

  const handleCancel = async (id: string) => {
    await cancelJob(id)
    refreshJobs()
  }

  const selectedJobData = jobs.find(j => j.id === selectedJob)

  return (
    <div className="h-screen flex flex-col bg-gray-950 overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 h-11 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        <span className="text-green-400 font-bold tracking-widest text-sm">■ ROBOT EVAL</span>
        <span className="text-gray-700">|</span>
        <span className="text-gray-500 text-xs">Isaac Sim 5.0 评测平台</span>
        <div className="ml-auto flex gap-1">
          {(['jobs', 'results'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                tab === t ? 'bg-gray-700 text-gray-100' : 'text-gray-500 hover:text-gray-300'
              }`}>
              {t === 'jobs' ? '任务' : '历史结果'}
            </button>
          ))}
        </div>
      </header>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="w-72 flex-shrink-0 border-r border-gray-800 flex flex-col overflow-hidden">
          <JobForm configs={configs} onSubmit={handleSubmit} />
          <div className="flex-1 overflow-y-auto">
            {tab === 'jobs'
              ? <JobList jobs={jobs} selectedId={selectedJob} onSelect={handleSelect} onCancel={handleCancel} />
              : <ResultsPanel results={results} />
            }
          </div>
        </aside>

        {/* Center: Isaac Sim view */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <SimView />
        </main>

        {/* Right: logs + metrics */}
        <aside className="w-80 flex-shrink-0 border-l border-gray-800 flex flex-col overflow-hidden">
          <LogPanel job={selectedJobData ?? null} logs={logs} />
        </aside>
      </div>
    </div>
  )
}
