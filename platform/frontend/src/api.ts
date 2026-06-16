import type { Job, JobConfig, Configs, EvalResult } from './types'

const BASE = '/api'

export async function fetchConfigs(): Promise<Configs> {
  const r = await fetch(`${BASE}/configs`)
  return r.json()
}

export async function fetchJobs(): Promise<Job[]> {
  const r = await fetch(`${BASE}/jobs`)
  return r.json()
}

export async function fetchJob(id: string): Promise<Job> {
  const r = await fetch(`${BASE}/jobs/${id}`)
  return r.json()
}

export async function submitJob(config: JobConfig): Promise<Job> {
  const r = await fetch(`${BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return r.json()
}

export async function cancelJob(id: string): Promise<void> {
  await fetch(`${BASE}/jobs/${id}`, { method: 'DELETE' })
}

export async function fetchResults(): Promise<EvalResult[]> {
  const r = await fetch(`${BASE}/results`)
  return r.json()
}

export function streamLogs(jobId: string, onLine: (line: string) => void, onEnd: () => void): () => void {
  const es = new EventSource(`${BASE}/jobs/${jobId}/logs`)
  es.onmessage = (e) => {
    if (e.data === '__END__') { onEnd(); es.close() }
    else onLine(e.data)
  }
  es.onerror = () => { onEnd(); es.close() }
  return () => es.close()
}
