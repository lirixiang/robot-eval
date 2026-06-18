// ── Submit request (matches backend SubmitRequest model) ──────────────────────
export interface SubmitRequest {
  name:              string
  arena_env_args:    Record<string, unknown>
  num_envs:          number
  num_episodes:      number | null
  num_steps:         number | null
  policy_type:       string
  policy_config:     Record<string, unknown>
  // Remote policy fields
  policy_server_url: string
  model_name:        string
  submitter:         string
  description:       string
}

// ── Run (a single attempt for a job) ──────────────────────────────────────────
export interface Run {
  id:          string
  job_id:      string
  attempt:     number
  worker_id:   number | null
  status:      'pending' | 'running' | 'done' | 'failed'
  metrics:     Record<string, number>
  seed:        number | null
  elapsed_s:   number | null
  error_msg:   string | null
  started_at:  number | null
  finished_at: number | null
  episodes?:   Episode[]
}

// ── Episode (per-episode result) ───────────────────────────────────────────────
export interface Episode {
  id:                 number
  run_id:             string
  episode_index:      number
  success:            boolean
  reward_total:       number
  steps:              number
  termination_reason: string
  metadata:           Record<string, unknown>
}

// ── Template ───────────────────────────────────────────────────────────────────
export interface Template {
  id:          number
  name:        string
  version:     string
  runner_type: string
  config_yaml: string
  description: string | null
  created_at:  string
}

// ── Analysis ───────────────────────────────────────────────────────────────────
export interface AnalysisCompare {
  runs: { id: string; job_id: string; metrics: Record<string, number>; finished_at: number | null; elapsed_s: number | null }[]
  metrics: Record<string, Record<string, number | string>>
  episodes: ({ index: number } & Record<string, boolean>)[]
}

export interface TrendPoint {
  run_id:       string
  job_id:       string
  finished_at:  number
  success_rate: number
  uph:          number
  model_name:   string
  env_name:     string
}

// ── Job (stored in DB, returned from /api/jobs) ────────────────────────────────
export interface Job {
  id:           string
  name?:        string
  status:       'pending' | 'running' | 'done' | 'failed_final' | 'failed' | 'cancelled' | 'retry_pending'
  config?:      SubmitRequest   // old shape (kept for compat)
  retry_count?: number
  max_retries?: number
  model_name?:  string
  submitter?:   string
  latest_run?:  Run
  created_at:   number
  updated_at:   number
  result?:      JobResult
}

export interface JobResult {
  job_id:    string
  run_id?:   string   // NEW — latest run UUID
  actor:     string
  job:       SubmitRequest
  metrics:   Metrics
  elapsed_s: number
  timestamp: number
}

// ── Metrics returned by eval backend ─────────────────────────────────────────
export interface Metrics {
  success_rate:        number   // 0–1
  uph:                 number
  avg_cycle_s:         number
  total_episodes?:     number
  success_count?:      number
  theoretical_max_uph?: number
  policy_model?:       string
  policy_submitter?:   string
  [key: string]: unknown
}

// ── Worker (returned from /api/workers) ───────────────────────────────────────
export interface Worker {
  id:              number
  host_id:         number
  host:            string
  http_port:       number
  livestream_port: number
  actor:           string
  online:          boolean
  busy:            boolean
  status:          string
  worker_id?:      number
}

// ── /api/configs response ─────────────────────────────────────────────────────
export interface Configs {
  environments: string[]
  policy_types: string[]
  example_job:  SubmitRequest
}

// ── Leaderboard ───────────────────────────────────────────────────────────────
export interface LeaderboardRow {
  rank:         number
  environment:  string
  model_name:   string
  submitter:    string
  description:  string
  success_rate: number
  uph:          number
  avg_cycle_s:  number
  num_episodes: number
  job_id:       string
  timestamp:    number
}

export interface LeaderboardGroup {
  environment: string
  rows:        LeaderboardRow[]
}

export interface Leaderboard {
  groups:            LeaderboardGroup[]
  total_submissions: number
  environments:      string[]
}

// ── Host management ───────────────────────────────────────────────────────────

export interface Host {
  id:           number
  label:        string
  host:         string
  port:         number
  username:     string
  worker_count: number
  created_at:   string
}

export interface GpuInfo {
  index:           number
  name:            string
  vram_total_mb:   number
  vram_free_mb:    number
  utilization_pct: number
  busy:            boolean
}

export interface MemInfo  { total_mb: number; used_mb: number }
export interface DiskInfo { path: string; total_gb: number; used_gb: number }

export interface ContainerInfo {
  name:      string
  status:    string
  gpu_index: number | null
}

export interface HostStatus {
  host_id:    number
  probed_at:  string
  gpus:       GpuInfo[]
  memory:     MemInfo
  disk:       DiskInfo
  containers: ContainerInfo[]
  used_ports: number[]
  error:      string | null
}

export interface RemoteWorker {
  id:              number
  host_id:         number
  worker_id:       number
  gpu_index:       number
  http_port:       number
  livestream_port: number
  container_name:  string
  status:          string
}

export interface AddHostRequest {
  label:    string
  host:     string
  port:     number
  username: string
  password: string
}
