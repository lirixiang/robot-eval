import { useState, useEffect, useCallback } from 'react'
import { fetchTemplates, createTemplate, deleteTemplate, validateYaml, submitJob } from '../api'
import type { Template, SubmitRequest } from '../types'

const STARTER_YAML = `name: my_benchmark
version: "1.0"
runner: isaaclab
runner_config:
  environment: lift_object
  embodiment: franka_joint_pos
  num_envs: 1
metrics:
  - name: success_rate
    type: ratio
    higher_is_better: true
  - name: uph
    type: float
    higher_is_better: true
episodes: 50
timeout_s: 3600
judge:
  type: metric_compare
  metric: success_rate
  min_diff: 0.02
`

export default function TemplatesView() {
  const [templates, setTemplates]   = useState<Template[]>([])
  const [selected, setSelected]     = useState<Template | null>(null)
  const [editorYaml, setEditorYaml] = useState(STARTER_YAML)
  const [newName, setNewName]       = useState('')
  const [newVersion, setNewVersion] = useState('1.0')
  const [newRunner, setNewRunner]   = useState('isaaclab')
  const [newDesc, setNewDesc]       = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [hasValidated, setHasValidated] = useState(false)
  const [saving, setSaving]         = useState(false)
  const [runMsg, setRunMsg]         = useState<string | null>(null)

  const refresh = useCallback(() =>
    fetchTemplates().then(setTemplates).catch(() => {}), [])

  useEffect(() => { refresh() }, [refresh])

  const handleValidate = async () => {
    const result = await validateYaml(editorYaml).catch(() => ({ valid: false, errors: ['Network error'] }))
    setValidationErrors(result.errors)
    setHasValidated(true)
  }

  const handleSave = async () => {
    if (!newName.trim()) return
    setSaving(true); setValidationErrors([])
    try {
      const t = await createTemplate({
        name: newName.trim(), version: newVersion,
        runner_type: newRunner, config_yaml: editorYaml,
        description: newDesc || undefined,
      })
      await refresh()
      setSelected(t)
      setIsCreating(false)
    } catch (e) {
      setValidationErrors([String(e)])
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (t: Template) => {
    if (!confirm(`删除模板 "${t.name}@${t.version}"？`)) return
    await deleteTemplate(t.id)
    await refresh()
    if (selected?.id === t.id) setSelected(null)
  }

  const handleRunBenchmark = async (t: Template) => {
    setRunMsg(null)
    try {
      const req: SubmitRequest = {
        name: `${t.name}_v${t.version}`,
        arena_env_args: {},
        num_envs: 1,
        num_episodes: 10,
        num_steps: null,
        policy_type: 'zero_action',
        policy_config: {},
        policy_server_url: '',
        model_name: '',
        submitter: '',
        description: `Benchmark run for template ${t.name}@${t.version}`,
      }
      // Try to parse config_yaml for env args
      try {
        const lines = t.config_yaml.split('\n')
        const envLine = lines.find(l => l.includes('environment:'))
        if (envLine) {
          const env = envLine.split(':')[1].trim()
          req.arena_env_args = { environment: env }
        }
      } catch {}
      await submitJob(req)
      setRunMsg('评测任务已提交，查看任务队列')
    } catch (e) {
      setRunMsg(`提交失败: ${e}`)
    }
  }

  const displayTemplate = isCreating ? null : selected

  return (
    <div className="h-full flex gap-4 p-4 overflow-hidden">
      {/* Left: template list */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-ink-200">评测模板</span>
          <button onClick={() => { setIsCreating(true); setSelected(null); setEditorYaml(STARTER_YAML); setValidationErrors([]); setHasValidated(false) }}
                  className="text-[11px] px-2 py-1 bg-green-600 hover:bg-green-500 text-white rounded">
            + 新建
          </button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1">
          {templates.length === 0 && (
            <div className="text-center text-ink-500 text-sm py-6">暂无模板</div>
          )}
          {templates.map(t => (
            <div key={t.id}
                 onClick={() => { setSelected(t); setIsCreating(false); setEditorYaml(t.config_yaml); setHasValidated(false) }}
                 className={`rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
                   selected?.id === t.id && !isCreating
                     ? 'border-green-600/60 bg-green-950/20'
                     : 'border-ink-800 bg-ink-900 hover:border-ink-600'
                 }`}>
              <div className="text-sm text-ink-200 font-medium">{t.name}</div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-ink-500">v{t.version}</span>
                <span className="text-[10px] px-1 bg-ink-800 text-ink-400 rounded">{t.runner_type}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right: editor / detail */}
      <div className="flex-1 flex flex-col min-w-0 gap-3">
        {isCreating && (
          <div className="bg-ink-900 rounded-lg border border-ink-700 p-4 grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">名称</label>
              <input value={newName} onChange={e => setNewName(e.target.value)}
                     placeholder="my_benchmark"
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">版本</label>
              <input value={newVersion} onChange={e => setNewVersion(e.target.value)}
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500" />
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">Runner 类型</label>
              <select value={newRunner} onChange={e => setNewRunner(e.target.value)}
                      className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-green-500">
                <option value="isaaclab">isaaclab</option>
                <option value="lmeval">lmeval</option>
                <option value="subprocess">subprocess</option>
                <option value="remote_policy">remote_policy</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-500 block mb-1">描述</label>
              <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
                     placeholder="可选"
                     className="w-full bg-ink-800 border border-ink-600 rounded px-2 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-green-500" />
            </div>
          </div>
        )}

        {displayTemplate && !isCreating && (
          <div className="bg-ink-900 rounded-lg border border-ink-700 px-4 py-3 flex items-center gap-4">
            <div className="flex-1">
              <span className="text-base font-semibold text-ink-100">{displayTemplate.name}</span>
              <span className="text-ink-500 text-sm ml-2">v{displayTemplate.version}</span>
              {displayTemplate.description && (
                <span className="text-ink-400 text-sm ml-3">{displayTemplate.description}</span>
              )}
            </div>
            <button onClick={() => handleRunBenchmark(displayTemplate)}
                    className="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white text-sm rounded">
              运行 Benchmark
            </button>
            <button onClick={() => handleDelete(displayTemplate)}
                    className="px-3 py-1.5 bg-red-900/40 hover:bg-red-800/60 text-red-400 text-sm rounded border border-red-800/40">
              删除
            </button>
          </div>
        )}

        {runMsg && (
          <div className="bg-ink-900 border border-ink-700 rounded px-3 py-2 text-sm text-ink-300">{runMsg}</div>
        )}

        {/* YAML editor */}
        <div className="flex-1 flex flex-col min-h-0 bg-ink-900 rounded-lg border border-ink-700 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800">
            <span className="text-[11px] text-ink-400 font-mono">config.yaml</span>
            <div className="flex gap-2">
              <button onClick={handleValidate}
                      className="text-[11px] px-2 py-1 border border-ink-600 rounded text-ink-300 hover:text-white hover:border-ink-400">
                校验
              </button>
              {isCreating && (
                <button onClick={handleSave} disabled={saving || !newName}
                        className="text-[11px] px-2 py-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white rounded">
                  {saving ? '保存中…' : '保存模板'}
                </button>
              )}
            </div>
          </div>
          {validationErrors.length > 0 && (
            <div className="px-3 py-2 bg-red-950/30 border-b border-red-800/30">
              {validationErrors.map((e, i) => (
                <div key={i} className="text-red-400 text-[11px]">{e}</div>
              ))}
            </div>
          )}
          {hasValidated && validationErrors.length === 0 && editorYaml && (
            <div className="px-3 py-1 bg-green-950/20 border-b border-green-900/30">
              <span className="text-green-500 text-[11px]">✓ YAML 有效</span>
            </div>
          )}
          <textarea
            value={editorYaml}
            onChange={e => { setEditorYaml(e.target.value); setValidationErrors([]) }}
            readOnly={!isCreating}
            spellCheck={false}
            className={`flex-1 p-3 font-mono text-[12px] leading-relaxed bg-transparent text-ink-200 resize-none focus:outline-none min-h-0 ${
              !isCreating ? 'text-ink-400' : ''
            }`}
          />
        </div>
      </div>
    </div>
  )
}
