import { useState } from 'react'
import type { Configs, JobConfig } from '../types'
import { Play } from 'lucide-react'

interface Props { configs: Configs; onSubmit: (cfg: JobConfig) => Promise<void> }

export default function JobForm({ configs, onSubmit }: Props) {
  const [cfg, setCfg] = useState<JobConfig>({
    task: 'LiftObj', layout: 'robocasakitchen-9-8',
    robot: 'LeRobot-RL', test_num: 10, time_limit: 60,
  })
  const [submitting, setSubmitting] = useState(false)

  const set = (k: keyof JobConfig, v: string | number) =>
    setCfg(prev => ({ ...prev, [k]: v }))

  const handle = async () => {
    setSubmitting(true)
    try { await onSubmit(cfg) } finally { setSubmitting(false) }
  }

  const field = 'w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-green-500 transition-colors'
  const label = 'text-xs text-gray-500 mb-1 block'

  return (
    <div className="p-3 border-b border-gray-800 flex-shrink-0">
      <div className="text-xs font-semibold text-gray-400 mb-3 tracking-wider">提交评测任务</div>
      <div className="space-y-2">
        <div>
          <label className={label}>任务 Task</label>
          <select className={field} value={cfg.task} onChange={e => set('task', e.target.value)}>
            {(configs.tasks.length ? configs.tasks : ['LiftObj']).map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className={label}>场景 Layout</label>
          <select className={field} value={cfg.layout} onChange={e => set('layout', e.target.value)}>
            {(configs.layouts.length ? configs.layouts : ['robocasakitchen-9-8']).map(l => <option key={l}>{l}</option>)}
          </select>
        </div>
        <div>
          <label className={label}>机器人 Robot</label>
          <select className={field} value={cfg.robot} onChange={e => set('robot', e.target.value)}>
            {(configs.robots.length ? configs.robots : ['LeRobot-RL']).map(r => <option key={r}>{r}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={label}>轮数</label>
            <input type="number" className={field} value={cfg.test_num} min={1} max={100}
              onChange={e => set('test_num', parseInt(e.target.value) || 1)} />
          </div>
          <div>
            <label className={label}>超时(s)</label>
            <input type="number" className={field} value={cfg.time_limit} min={10}
              onChange={e => set('time_limit', parseFloat(e.target.value) || 60)} />
          </div>
        </div>
      </div>
      <button onClick={handle} disabled={submitting}
        className="mt-3 w-full flex items-center justify-center gap-2 py-2 rounded text-xs font-semibold bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
        <Play size={12} />
        {submitting ? '提交中...' : '开始评测'}
      </button>
    </div>
  )
}
