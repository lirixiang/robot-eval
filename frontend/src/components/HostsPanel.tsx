import { useState, useCallback, useEffect } from 'react'
import type { Host, HostStatus, AddHostRequest } from '../types'
import { fetchHosts, addHost, deleteHost, probeHost, deployWorker } from '../api'

interface Props {
  onWorkersChanged: () => void  // triggers parent to refresh /api/workers
}

function AddHostDrawer({ onSave, onClose }: {
  onSave: (req: AddHostRequest) => Promise<void>
  onClose: () => void
}) {
  const [form, setForm] = useState<AddHostRequest>({
    label: '', host: '', port: 22, username: 'root', password: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  const set = (k: keyof AddHostRequest, v: string | number) =>
    setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    if (!form.label || !form.host || !form.username || !form.password) {
      setError('请填写所有必填字段')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(form)
    } catch (e: any) {
      setError(e.message ?? '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end"
         style={{ background: 'rgba(0,0,0,.5)' }} onClick={onClose}>
      <div className="w-80 h-full bg-ink-900 border-l border-ink-800 p-5 flex flex-col gap-4 overflow-y-auto"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-white">添加主机</span>
          <button className="btn-sm" onClick={onClose}>
            <i className="fas fa-times" />
          </button>
        </div>

        {[
          { label: '标签', key: 'label', type: 'text', placeholder: 'GPU服务器-A' },
          { label: 'IP 地址', key: 'host', type: 'text', placeholder: '10.0.0.2' },
          { label: 'SSH 端口', key: 'port', type: 'number', placeholder: '22' },
          { label: '用户名', key: 'username', type: 'text', placeholder: 'root' },
          { label: '密码', key: 'password', type: 'password', placeholder: '••••••••' },
        ].map(({ label, key, type, placeholder }) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-[11px] text-ink-400">{label}</label>
            <input
              type={type}
              placeholder={placeholder}
              value={String(form[key as keyof AddHostRequest])}
              onChange={e => set(
                key as keyof AddHostRequest,
                type === 'number' ? Number(e.target.value) : e.target.value
              )}
              className="bg-ink-800 border border-ink-700 rounded px-2.5 py-1.5 text-sm text-ink-200
                         focus:outline-none focus:border-sky2 placeholder:text-ink-600"
            />
          </div>
        ))}

        {error && <p className="text-[11px] text-red-400">{error}</p>}

        <div className="flex gap-2 mt-auto pt-2">
          <button className="btn-sm flex-1" onClick={onClose}>取消</button>
          <button
            className="btn-sm flex-1 bg-sky2/10 text-sky2 border-sky2/30 hover:bg-sky2/20"
            disabled={saving}
            onClick={handleSave}
          >
            {saving ? <i className="fas fa-spinner animate-spin mr-1" /> : null}
            保存
          </button>
        </div>
      </div>
    </div>
  )
}

function ProbeRow({ hostId, onDeployed }: {
  hostId: number
  onDeployed: () => void
}) {
  const [status, setStatus] = useState<HostStatus | null>(null)
  const [probing, setProbing] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [deployMsg, setDeployMsg] = useState<string | null>(null)

  const handleProbe = useCallback(async () => {
    setProbing(true)
    try {
      const s = await probeHost(hostId)
      setStatus(s)
    } finally {
      setProbing(false)
    }
  }, [hostId])

  useEffect(() => {
    handleProbe()
  }, [handleProbe])

  const handleDeploy = useCallback(async () => {
    setDeploying(true)
    setDeployMsg(null)
    try {
      await deployWorker(hostId)
      setDeployMsg('Worker 部署中，稍后在下方卡片查看状态')
      onDeployed()
    } catch (e: any) {
      setDeployMsg(`部署失败: ${e.message}`)
    } finally {
      setDeploying(false)
    }
  }, [hostId, onDeployed])

  if (!status && !probing) return null

  return (
    <div className="col-span-5 bg-ink-950 border border-ink-800 rounded-lg p-4 mx-1 mb-2 text-[11px]">
      {probing && (
        <div className="flex items-center gap-2 text-ink-500">
          <i className="fas fa-spinner animate-spin" /> 探测中...
        </div>
      )}
      {status && !probing && (
        <>
          {status.error ? (
            <p className="text-red-400">连接失败: {status.error}</p>
          ) : (
            <div className="space-y-3">
              {/* GPUs */}
              <div>
                <span className="text-ink-500 mr-2">GPU</span>
                {status.gpus.map(g => (
                  <span key={g.index} className="mr-3">
                    <span className="text-ink-300">#{g.index} {g.name}</span>
                    <span className="text-ink-500 ml-1">{g.vram_free_mb}MB 空闲</span>
                    <span className={`ml-1 chip ${g.busy ? 'chip-run' : 'chip-pend'}`}>
                      {g.busy ? '忙碌' : '空闲'}
                    </span>
                  </span>
                ))}
              </div>
              {/* Memory + Disk */}
              <div className="flex gap-6">
                <span>
                  <span className="text-ink-500">内存 </span>
                  <span className="text-ink-300 num">{status.memory.used_mb}
                    <span className="text-ink-500">/{status.memory.total_mb} MB</span>
                  </span>
                </span>
                <span>
                  <span className="text-ink-500">磁盘 </span>
                  <span className="text-ink-300 num">{status.disk.used_gb}
                    <span className="text-ink-500">/{status.disk.total_gb} GB</span>
                  </span>
                </span>
              </div>
              {/* Containers */}
              {status.containers.length > 0 && (
                <div>
                  <span className="text-ink-500 mr-2">容器</span>
                  {status.containers.map(c => (
                    <span key={c.name} className="mr-3">
                      <span className="font-mono text-ink-300">{c.name}</span>
                      <span className="text-ink-500 ml-1">{c.status}</span>
                      {c.gpu_index != null && <span className="text-ink-600 ml-1">GPU{c.gpu_index}</span>}
                    </span>
                  ))}
                </div>
              )}
              {/* Deploy button */}
              <div className="flex items-center gap-3 pt-1">
                <button
                  className="btn-sm bg-success/10 text-success border-success/30 hover:bg-success/20"
                  disabled={deploying || status.gpus.every(g => g.busy)}
                  onClick={handleDeploy}
                >
                  {deploying
                    ? <><i className="fas fa-spinner animate-spin mr-1" />部署中...</>
                    : <><i className="fas fa-plus mr-1" />部署新 Worker</>}
                </button>
                {deployMsg && <span className="text-ink-400">{deployMsg}</span>}
                {status.gpus.every(g => g.busy) && (
                  <span className="text-ink-500">所有 GPU 已占用</span>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function HostsPanel({ onWorkersChanged }: Props) {
  const [hosts, setHosts]           = useState<Host[]>([])
  const [loading, setLoading]       = useState(false)
  const [showDrawer, setShowDrawer] = useState(false)
  const [probingId, setProbingId]   = useState<number | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setHosts(await fetchHosts()) } finally { setLoading(false) }
  }, [])

  // Load on mount
  useEffect(() => { refresh() }, [refresh])

  const handleAddHost = async (req: AddHostRequest) => {
    await addHost(req)
    setShowDrawer(false)
    await refresh()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('删除该主机将同时销毁其所有 Worker，确认继续？')) return
    await deleteHost(id)
    await refresh()
    onWorkersChanged()
  }

  const handleProbe = async (id: number) => {
    setProbingId(id)
    setExpandedId(id)
    try { await refresh() } finally { setProbingId(null) }
  }

  return (
    <div className="form-section mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="tag text-ink-400">远端主机</span>
          {loading && <i className="fas fa-spinner animate-spin text-ink-600 text-[10px]" />}
        </div>
        <button
          className="btn-sm bg-sky2/10 text-sky2 border-sky2/30 hover:bg-sky2/20"
          onClick={() => setShowDrawer(true)}
        >
          <i className="fas fa-plus mr-1" />添加主机
        </button>
      </div>

      {hosts.length === 0 ? (
        <p className="text-[11px] text-ink-600 py-2">暂无注册主机。点击"添加主机"开始配置。</p>
      ) : (
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-ink-500 border-b border-ink-800">
              <th className="text-left py-1.5 pr-4 font-normal">标签</th>
              <th className="text-left py-1.5 pr-4 font-normal">IP</th>
              <th className="text-left py-1.5 pr-4 font-normal">用户</th>
              <th className="text-left py-1.5 pr-4 font-normal">Worker</th>
              <th className="text-right py-1.5 font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {hosts.map(h => (
              <>
                <tr key={h.id} className="border-b border-ink-800/50">
                  <td className="py-2 pr-4 text-ink-200 font-medium">{h.label}</td>
                  <td className="py-2 pr-4 font-mono text-ink-300">{h.host}:{h.port}</td>
                  <td className="py-2 pr-4 text-ink-400">{h.username}</td>
                  <td className="py-2 pr-4">
                    {h.worker_count > 0
                      ? <span className="chip chip-run">{h.worker_count} 运行</span>
                      : <span className="text-ink-600">—</span>}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex items-center gap-1.5 justify-end">
                      <button
                        className="btn-sm"
                        disabled={probingId === h.id}
                        onClick={() => handleProbe(h.id)}
                      >
                        {probingId === h.id
                          ? <i className="fas fa-spinner animate-spin" />
                          : <><i className="fas fa-satellite-dish mr-1" />探测</>}
                      </button>
                      <button
                        className="btn-sm text-red-400 border-red-400/30 hover:bg-red-400/10"
                        onClick={() => handleDelete(h.id)}
                      >
                        <i className="fas fa-trash" />
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === h.id && (
                  <tr key={`${h.id}-probe`}>
                    <td colSpan={5} className="pb-2">
                      <ProbeRow
                        hostId={h.id}
                        onDeployed={() => { onWorkersChanged(); refresh() }}
                      />
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}

      {showDrawer && (
        <AddHostDrawer
          onSave={handleAddHost}
          onClose={() => setShowDrawer(false)}
        />
      )}
    </div>
  )
}
