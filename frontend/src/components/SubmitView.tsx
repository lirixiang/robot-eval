import { useState, useRef, useCallback } from 'react'
import type { Configs, SubmitRequest } from '../types'

function Divider({ onDrag }: { onDrag: (dx: number) => void }) {
  const dragging = useRef(false)
  const last = useRef(0)
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true; last.current = e.clientX; e.preventDefault()
    const onMove = (ev: MouseEvent) => { if (dragging.current) { onDrag(ev.clientX - last.current); last.current = ev.clientX } }
    const onUp = () => { dragging.current = false; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp)
  }, [onDrag])
  return <div onMouseDown={onMouseDown} className="w-1 flex-shrink-0 bg-ink-700 hover:bg-green-600/60 active:bg-green-500 cursor-col-resize transition-colors select-none" />
}

interface Props {
  configs: Configs
  onSubmit: (r: SubmitRequest) => Promise<void>
}

interface FormState {
  environment:       string
  embodiment:        string
  pick_up_object:    string
  hdr:               string
  num_envs:          number
  env_spacing:       number
  policy_type:       string
  task_name:         string
  num_episodes:      number
  num_steps:         string
  job_name:          string
  // Remote policy
  use_remote:        boolean
  policy_server_url: string
  model_name:        string
  submitter:         string
  description:       string
  // GPU scheduling
  priority:          number
  num_gpus:          number
  gpu_type:          string
}

const DEFAULT_FORM = (configs: Configs): FormState => ({
  environment:       configs.environments[0] ?? '',
  embodiment:        'franka',
  pick_up_object:    '',
  hdr:               '',
  num_envs:          1,
  env_spacing:       2.5,
  policy_type:       configs.policy_types[0] ?? '',
  task_name:         '',
  num_episodes:      50,
  num_steps:         '',
  job_name:          '',
  use_remote:        false,
  policy_server_url: '',
  model_name:        '',
  submitter:         '',
  description:       '',
  priority:          5,
  num_gpus:          1,
  gpu_type:          '',
})

function formToRequest(f: FormState): SubmitRequest {
  const arena_env_args: Record<string, unknown> = {
    environment:  f.environment,
    embodiment:   f.embodiment,
    env_spacing:  f.env_spacing,
  }
  if (f.pick_up_object) arena_env_args.pick_up_object = f.pick_up_object
  if (f.hdr) arena_env_args.hdr = f.hdr
  return {
    name:              f.job_name || `job-${Date.now()}`,
    arena_env_args,
    num_envs:          f.num_envs,
    num_episodes:      f.num_episodes,
    num_steps:         f.num_steps ? +f.num_steps : null,
    policy_type:       f.use_remote ? 'remote' : f.policy_type,
    policy_config:     { task: f.task_name },
    policy_server_url: f.use_remote ? f.policy_server_url : '',
    model_name:        f.model_name,
    submitter:         f.submitter,
    description:       f.description,
    priority:          f.priority,
    num_gpus:          f.num_gpus,
    gpu_type:          f.gpu_type,
  }
}

export default function SubmitView({ configs, onSubmit }: Props) {
  const [form, setForm]       = useState<FormState>(() => DEFAULT_FORM(configs))
  const [submitting, setSubmitting] = useState(false)
  const [previewW, setPreviewW] = useState(360)

  const set = (key: keyof FormState, value: unknown) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onSubmit(formToRequest(form))
      setForm(DEFAULT_FORM(configs))
    } finally { setSubmitting(false) }
  }

  const preview = formToRequest(form)

  return (
    <div className="flex h-full overflow-hidden">
      {/* LEFT: Form */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">

        {/* 环境配置 */}
        <div className="form-section space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="tag text-ink-400">环境配置</span>
            <span className="chip chip-env text-[10px]">arena_env_args</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">环境</label>
              <select className="inp" value={form.environment} onChange={e => set('environment', e.target.value)}>
                {configs.environments.map(ev => <option key={ev}>{ev}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">机器人本体</label>
              <select className="inp" value={form.embodiment} onChange={e => set('embodiment', e.target.value)}>
                {['franka', 'droid_rel_joint_pos', 'g1', 'gr1'].map(v => <option key={v}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">拾取物体 <span className="text-ink-600">(可选)</span></label>
              <input className="inp" placeholder="e.g. red_cube" value={form.pick_up_object} onChange={e => set('pick_up_object', e.target.value)} />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">HDR 贴图 <span className="text-ink-600">(可选)</span></label>
              <input className="inp" placeholder="e.g. studio_small" value={form.hdr} onChange={e => set('hdr', e.target.value)} />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">并发环境数</label>
              <input type="number" className="inp" min={1} max={32} value={form.num_envs} onChange={e => set('num_envs', +e.target.value)} />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">env_spacing</label>
              <input type="number" className="inp" step={0.5} min={1} value={form.env_spacing} onChange={e => set('env_spacing', +e.target.value)} />
            </div>
          </div>
        </div>

        {/* 策略来源切换 */}
        <div className="form-section space-y-3">
          <div className="flex items-center gap-3 mb-1">
            <span className="tag text-ink-400">策略来源</span>
            <div className="seg">
              <button className={!form.use_remote ? 'on' : ''} onClick={() => set('use_remote', false)}>
                <i className="fas fa-cube mr-1 text-[10px]" />内置策略
              </button>
              <button className={form.use_remote ? 'on' : ''} onClick={() => set('use_remote', true)}>
                <i className="fas fa-plug mr-1 text-[10px]" />外部模型
              </button>
            </div>
            {form.use_remote && (
              <span className="chip chip-run text-[10px] animate-pulse">接入榜单</span>
            )}
          </div>

          {!form.use_remote ? (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-ink-500 block mb-1">策略类型</label>
                <select className="inp" value={form.policy_type} onChange={e => set('policy_type', e.target.value)}>
                  {configs.policy_types.map(p => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-ink-500 block mb-1">任务名称</label>
                <input className="inp" placeholder="e.g. LiftObj" value={form.task_name} onChange={e => set('task_name', e.target.value)} />
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Policy Server URL */}
              <div>
                <label className="text-[11px] text-ink-500 block mb-1">
                  Policy Server URL <span className="text-gold">*</span>
                </label>
                <input
                  className="inp font-mono"
                  placeholder="http://192.168.1.100:7860"
                  value={form.policy_server_url}
                  onChange={e => set('policy_server_url', e.target.value)}
                />
                <div className="text-[10px] text-ink-600 mt-1">
                  服务器需实现 <code className="text-violet">GET /info</code>、<code className="text-violet">POST /reset</code>、<code className="text-violet">POST /act</code>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-ink-500 block mb-1">模型名称 <span className="text-gold">*</span></label>
                  <input className="inp" placeholder="e.g. pi0.5" value={form.model_name} onChange={e => set('model_name', e.target.value)} />
                </div>
                <div>
                  <label className="text-[11px] text-ink-500 block mb-1">提交方 <span className="text-gold">*</span></label>
                  <input className="inp" placeholder="e.g. My Lab" value={form.submitter} onChange={e => set('submitter', e.target.value)} />
                </div>
              </div>
              <div>
                <label className="text-[11px] text-ink-500 block mb-1">描述 <span className="text-ink-600">(可选)</span></label>
                <input className="inp" placeholder="e.g. Diffusion policy, pretrained on 1k demos" value={form.description} onChange={e => set('description', e.target.value)} />
              </div>
              {/* SDK hint */}
              <div className="bg-ink-950 rounded-lg p-3 border border-ink-800">
                <div className="text-[10px] text-ink-500 mb-2 tag">快速接入</div>
                <pre className="text-[11px] font-mono leading-5 text-ink-300 whitespace-pre-wrap">{`from policy_server import PolicyBase, serve

class MyPolicy(PolicyBase):
    info = {"model": "${form.model_name || 'my-model'}", "submitter": "${form.submitter || 'My Lab'}"}

    def reset(self, episode_id, env_info): ...

    def act(self, observations, episode_id, step):
        return [0.0] * observations["action_dim"]

serve(MyPolicy(), port=7860)`}</pre>
              </div>
            </div>
          )}
        </div>

        {/* 评测参数 */}
        <div className="form-section space-y-3">
          <div className="tag text-ink-400 mb-1">评测参数</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">评测轮次</label>
              <input type="number" className="inp" min={1} value={form.num_episodes} onChange={e => set('num_episodes', +e.target.value)} />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">最大步数 <span className="text-ink-600">(可选)</span></label>
              <input type="number" className="inp" placeholder="留空不限" value={form.num_steps} onChange={e => set('num_steps', e.target.value)} />
            </div>
            <div className="col-span-2">
              <label className="text-[11px] text-ink-500 block mb-1">任务名称 <span className="text-ink-600">(留空自动生成)</span></label>
              <input className="inp" placeholder="e.g. lift-franka-v1" value={form.job_name} onChange={e => set('job_name', e.target.value)} />
            </div>
          </div>
        </div>

        {/* GPU 调度配置 */}
        <div className="form-section space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="tag text-ink-400">GPU 调度</span>
            <span className="chip chip-env text-[10px]">scheduling</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">优先级</label>
              <select className="inp" value={form.priority} onChange={e => set('priority', +e.target.value)}>
                <option value={1}>1 - 最高</option>
                <option value={2}>2 - 紧急</option>
                <option value={3}>3 - 高</option>
                <option value={5}>5 - 普通</option>
                <option value={7}>7 - 低</option>
                <option value={9}>9 - 最低</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">GPU 数量</label>
              <input type="number" className="inp" min={1} max={8} value={form.num_gpus} onChange={e => set('num_gpus', +e.target.value)} />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">GPU 型号 <span className="text-ink-600">(可选)</span></label>
              <select className="inp" value={form.gpu_type} onChange={e => set('gpu_type', e.target.value)}>
                <option value="">不限</option>
                <option value="A100">A100</option>
                <option value="H100">H100</option>
                <option value="RTX 4090">RTX 4090</option>
                <option value="RTX 3090">RTX 3090</option>
              </select>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex gap-3">
          <button
            className="btn-primary"
            disabled={submitting || (form.use_remote && !form.policy_server_url)}
            onClick={handleSubmit}
          >
            {submitting
              ? <><span className="spinner mr-1.5" />提交中…</>
              : <><i className="fas fa-paper-plane mr-1.5" />{form.use_remote ? '提交并上榜' : '提交评测'}</>
            }
          </button>
          <button className="btn-sm px-4 py-2" onClick={() => setForm(DEFAULT_FORM(configs))}>
            <i className="fas fa-rotate-left mr-1" />重置
          </button>
        </div>
      </div>

      {/* RIGHT: Preview */}
      <Divider onDrag={dx => setPreviewW(w => Math.max(200, Math.min(700, w - dx)))} />
      <div style={{ width: previewW }} className="flex-shrink-0 overflow-y-auto p-4 space-y-4 bg-ink-900">
        <div className="form-section">
          <div className="flex items-center justify-between mb-2">
            <span className="tag text-ink-400">Job Config 预览</span>
            <span className="chip chip-env">JSON</span>
          </div>
          <pre className="text-success font-mono text-[11px] whitespace-pre-wrap break-all leading-5 overflow-auto max-h-80">
            {JSON.stringify(preview, null, 2)}
          </pre>
        </div>

        <div className="form-section">
          <div className="tag text-ink-400 mb-3">队列状态</div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="dot bg-success" />
            <span className="text-xs text-ink-300">就绪</span>
          </div>
          <div className="text-xs text-ink-500">0 任务排队</div>
        </div>

        {form.use_remote && (
          <div className="form-section" style={{ borderColor: 'rgba(212,168,87,.35)' }}>
            <div className="flex items-center gap-2 mb-2">
              <i className="fas fa-trophy text-gold text-[11px]" />
              <span className="tag text-gold">榜单提交</span>
            </div>
            <div className="space-y-1 text-[11px] text-ink-400">
              <div>模型：<span className="text-white">{form.model_name || '–'}</span></div>
              <div>提交方：<span className="text-white">{form.submitter || '–'}</span></div>
              <div>环境：<span className="text-sky2">{form.environment}</span></div>
              <div>轮次：<span className="num text-ink-200">{form.num_episodes}</span></div>
            </div>
            <div className="mt-2 text-[10px] text-ink-600">
              评测完成后自动出现在公开榜单
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
