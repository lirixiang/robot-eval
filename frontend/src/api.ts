import type { Job, SubmitRequest, Configs, Worker, JobResult, Leaderboard, Host, HostStatus, RemoteWorker, AddHostRequest } from './types'

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

export async function submitJob(req: SubmitRequest): Promise<Job> {
  const r = await fetch(`${BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function cancelJob(id: string): Promise<void> {
  await fetch(`${BASE}/jobs/${id}`, { method: 'DELETE' })
}

export async function fetchResults(): Promise<JobResult[]> {
  const r = await fetch(`${BASE}/results`)
  return r.json()
}

export async function fetchWorkers(): Promise<Worker[]> {
  const r = await fetch(`${BASE}/workers`)
  return r.json()
}

export async function fetchLeaderboard(env?: string): Promise<Leaderboard> {
  const url = env ? `${BASE}/leaderboard?env=${encodeURIComponent(env)}` : `${BASE}/leaderboard`
  const r = await fetch(url)
  return r.json()
}

export function streamLogs(
  jobId: string,
  onLine: (line: string) => void,
  onEnd: () => void,
): () => void {
  const es = new EventSource(`${BASE}/jobs/${jobId}/logs`)
  es.onmessage = (e) => {
    if (e.data === '__END__') { onEnd(); es.close() }
    else {
      try { onLine(JSON.parse(e.data) as string) }
      catch { onLine(e.data as string) }
    }
  }
  es.onerror = () => { onEnd(); es.close() }
  return () => es.close()
}

// ── Host management ───────────────────────────────────────────────────────────

export async function fetchHosts(): Promise<Host[]> {
  const r = await fetch(`${BASE}/hosts`)
  return r.json()
}

export async function addHost(req: AddHostRequest): Promise<Host> {
  const r = await fetch(`${BASE}/hosts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deleteHost(hostId: number): Promise<void> {
  await fetch(`${BASE}/hosts/${hostId}`, { method: 'DELETE' })
}

export async function probeHost(hostId: number): Promise<HostStatus> {
  const r = await fetch(`${BASE}/hosts/${hostId}/probe`, { method: 'POST' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deployWorker(hostId: number): Promise<RemoteWorker> {
  const r = await fetch(`${BASE}/hosts/${hostId}/deploy`, { method: 'POST' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function destroyWorker(hostId: number, workerId: number): Promise<void> {
  await fetch(`${BASE}/hosts/${hostId}/workers/${workerId}`, { method: 'DELETE' })
}

export interface RayStatus {
  online: boolean; nodes: number
  cpu_total: number; cpu_used: number
  gpu_total: number; gpu_used: number
  mem_total_gb: number
}

export async function fetchRayStatus(): Promise<RayStatus> {
  const r = await fetch(`${BASE}/ray/status`)
  return r.json()
}
