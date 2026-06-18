import type { Job, SubmitRequest, Configs, Worker, JobResult, Leaderboard, Host, HostStatus, RemoteWorker, AddHostRequest, Run, AnalysisCompare, TrendPoint, Template, Match, EloEntry, WinMatrixEntry, ModelProfile } from './types'

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

// ── Phase 2: Runs, Analysis, Templates ───────────────────────────────────────

export async function fetchRun(id: string): Promise<Run> {
  const r = await fetch(`${BASE}/runs/${id}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function setBaseline(runId: string): Promise<void> {
  const r = await fetch(`${BASE}/runs/${runId}/set-baseline`, { method: 'PUT' })
  if (!r.ok) throw new Error(await r.text())
}

export async function reproduceJob(jobId: string): Promise<Job> {
  const r = await fetch(`${BASE}/jobs/${jobId}/reproduce`, { method: 'POST' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchCompare(runIds: string[]): Promise<AnalysisCompare> {
  const r = await fetch(`${BASE}/analysis/compare?runs=${runIds.join(',')}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchTrend(model: string, env: string, days = 30): Promise<TrendPoint[]> {
  const r = await fetch(`${BASE}/analysis/trend?model=${encodeURIComponent(model)}&env=${encodeURIComponent(env)}&days=${days}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchTemplates(): Promise<Template[]> {
  const r = await fetch(`${BASE}/templates`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function createTemplate(req: {
  name: string; version: string; runner_type: string;
  config_yaml: string; description?: string;
}): Promise<Template> {
  const r = await fetch(`${BASE}/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deleteTemplate(id: number): Promise<void> {
  const r = await fetch(`${BASE}/templates/${id}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
}

export async function validateYaml(config_yaml: string): Promise<{ valid: boolean; errors: string[] }> {
  const r = await fetch(`${BASE}/templates/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_yaml }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

// ── Phase 3: Arena / Elo ──────────────────────────────────────────────────────

export async function fetchMatches(params?: { status?: string; env_name?: string }): Promise<Match[]> {
  const q = new URLSearchParams((params as Record<string, string>) ?? {})
  const r = await fetch(`${BASE}/arena/matches?${q}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function createMatch(req: {
  env_name: string; model_a: string; model_b: string;
  mode?: string; is_blind?: boolean; num_episodes?: number;
  judge_config?: Record<string, unknown>; arena_env_args?: Record<string, unknown>;
  policy_server_url_a?: string; policy_server_url_b?: string;
}): Promise<Match> {
  const r = await fetch(`${BASE}/arena/matches`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchArenaLeaderboard(env: string): Promise<EloEntry[]> {
  const r = await fetch(`${BASE}/arena/leaderboard?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchArenaEnvs(): Promise<string[]> {
  const r = await fetch(`${BASE}/arena/envs`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchWinMatrix(env: string): Promise<WinMatrixEntry[]> {
  const r = await fetch(`${BASE}/arena/matrix?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchModelProfile(model: string, env: string): Promise<ModelProfile> {
  const r = await fetch(`${BASE}/arena/models/${encodeURIComponent(model)}?env=${encodeURIComponent(env)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
