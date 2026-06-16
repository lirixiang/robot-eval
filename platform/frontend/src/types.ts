export interface JobConfig {
  task: string
  layout: string
  robot: string
  test_num: number
  time_limit: number
}

export interface Job {
  id: string
  config: JobConfig
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  created_at: number
  updated_at: number
  result?: EvalResult
}

export interface EvalResult {
  job_id: string
  task: string
  layout: string
  robot: string
  test_num: number
  success_count: number
  success_rate: number
  avg_cycle_seconds: number
  total_wall_seconds: number
  uph: number
  theoretical_max_uph: number
  timestamp: number
}

export interface Configs {
  tasks: string[]
  layouts: string[]
  robots: string[]
}
