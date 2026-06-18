# UI Navigation Consolidation — Design Spec
**Date:** 2026-06-18  
**Status:** Approved  
**Scope:** Merge 9 navigation pages into 4 workflow-aligned pages

---

## 1. Problem

The current UI has 9 top-level navigation items:
总览 / 提交任务 / 任务队列 / 评测结果 / 集群 / 榜单 / 分析 / 竞技场 / 模板

These map poorly to actual user workflows. Related features are spread across separate pages, requiring multiple navigation jumps to complete a single task.

---

## 2. New Navigation Structure

4 pages, keyboard shortcuts D/E/C/S:

| Page | 快捷键 | Merges |
|---|---|---|
| **总览** (Dashboard) | `D` | Dashboard — unchanged |
| **评测** (Eval) | `E` | 提交任务 + 任务队列 + 评测结果 |
| **竞技** (Arena) | `C` | 竞技场 + 榜单 + 分析 |
| **系统** (System) | `S` | 集群 + 模板 |

Remove from nav: submit, jobs, results, workers, leaderboard, analysis, arena, templates (all absorbed).

---

## 3. Page Designs

### 3.1 总览 (Dashboard) — unchanged
No changes. Existing DashboardView content stays as-is.

### 3.2 评测 (EvalView)

**Layout:** Two-column. Left: submit form (fixed width ~300px). Right: Tab panel.

```
┌─────────────────────────────────────────────────────┐
│  评测                                                │
├──────────────┬──────────────────────────────────────┤
│              │  [队列]  [结果]                       │
│  提交表单    ├──────────────────────────────────────┤
│              │                                      │
│  环境选择    │  队列 Tab:                            │
│  模型/策略   │  - 任务列表（状态/模型/时间）          │
│  参数配置    │  - 点击展开右侧日志/详情面板           │
│              │                                      │
│  [提交]      │  结果 Tab:                            │
│              │  - 结果卡片列表                        │
│              │  - Episode折叠展开                    │
│              │  - 多选 → 跳转分析                    │
└──────────────┴──────────────────────────────────────┘
```

**Behavior:**
- On submit: switch right panel to 队列 Tab, highlight the new job
- Submit form stays visible at all times (no navigation needed to submit again)
- 队列 Tab is default when arriving at 评测 page

**Components to create/modify:**
- `EvalView.tsx` — new container component
- Reuses: `SubmitView` content (left panel), `JobsView` content (right 队列 tab), `ResultsView` content (right 结果 tab)
- State: `rightTab: 'queue' | 'results'`, passed down + auto-switched on submit

### 3.3 竞技 (ArenaView consolidated)

**Layout:** Top 3-tab switcher.

```
┌─────────────────────────────────────────────────────┐
│  竞技   [对战]  [榜单]  [分析]                       │
├─────────────────────────────────────────────────────┤
│  对战 Tab:                                           │
│  ├─ Left (w-64): 发起对战表单                        │
│  ├─ Center (flex): 对战记录列表                      │
│  └─ Right (w-72): 当前环境 Elo 实时榜单              │
│                                                     │
│  榜单 Tab:                                           │
│  ├─ 传统成功率榜 (existing LeaderboardView content)  │
│  └─ Elo竞技榜 + N×N 胜率矩阵                        │
│                                                     │
│  分析 Tab:                                           │
│  └─ 多Run对比表 + 趋势折线图 (existing AnalysisView) │
└─────────────────────────────────────────────────────┘
```

**Components to create/modify:**
- `ArenaConsolidatedView.tsx` — new container with tab switcher
- 对战 Tab: reuses existing `ArenaView` content
- 榜单 Tab: reuses existing `LeaderboardView` content  
- 分析 Tab: reuses existing `AnalysisView` content

### 3.4 系统 (SystemView)

**Layout:** Top 2-tab switcher.

```
┌─────────────────────────────────────────────────────┐
│  系统   [集群]  [模板]                               │
├─────────────────────────────────────────────────────┤
│  集群 Tab:                                           │
│  └─ WorkersView content (worker cards, Ray status)  │
│                                                     │
│  模板 Tab:                                           │
│  └─ TemplatesView content (YAML editor, list)       │
└─────────────────────────────────────────────────────┘
```

**Components to create/modify:**
- `SystemView.tsx` — new container with 2-tab switcher
- 集群 Tab: reuses existing `WorkersView` content
- 模板 Tab: reuses existing `TemplatesView` content

---

## 4. App.tsx Changes

### ViewName
```typescript
export type ViewName = 'dashboard' | 'eval' | 'arena' | 'system'
```

### NAV array
```typescript
const NAV = [
  { id: 'dashboard', label: '总览',  icon: 'fa-gauge-high' },
  { id: 'eval',      label: '评测',  icon: 'fa-list-check' },
  { id: 'arena',     label: '竞技',  icon: 'fa-swords'     },
  { id: 'system',    label: '系统',  icon: 'fa-server'     },
]
```

### Keyboard shortcuts
```
D → dashboard
E → eval
C → arena (竞技)
S → system
```

Remove: N (submit), J (jobs), W (workers), L (leaderboard), A (analysis), R (arena old), T (templates)

### View rendering
```tsx
{view === 'dashboard' && <DashboardView ... />}
{view === 'eval'      && <EvalView jobs={jobs} results={results} configs={configs} onSubmit={handleSubmit} onCancel={handleCancel} onReproduce={handleReproduce} />}
{view === 'arena'     && <ArenaConsolidatedView />}
{view === 'system'    && <SystemView workers={workers} onRefresh={refreshWorkers} onOpenModal={setModalWorker} />}
```

### useRouter.ts PATH_MAP
```typescript
const PATH_MAP = {
  '/':          'dashboard',
  '/dashboard': 'dashboard',
  '/eval':      'eval',
  '/arena':     'arena',
  '/system':    'system',
  // Legacy redirects — map old paths to new views
  '/submit':      'eval',
  '/jobs':        'eval',
  '/results':     'eval',
  '/workers':     'system',
  '/templates':   'system',
  '/leaderboard': 'arena',
  '/analysis':    'arena',
}
```

---

## 5. EvalView State Management

`EvalView` needs to coordinate submit → auto-switch to queue tab:

```typescript
// In App.tsx
const handleSubmit = async (req: SubmitRequest) => {
  const job = await submitJob(req)
  await refreshJobs()
  setEvalTab('queue')          // signal EvalView to show queue tab
  setHighlightedJobId(job.id)  // highlight new job
}
```

Or pass a callback into EvalView that the submit form calls directly.

---

## 6. Files to Create

| File | Action |
|---|---|
| `frontend/src/components/EvalView.tsx` | Create — two-column layout |
| `frontend/src/components/ArenaConsolidatedView.tsx` | Create — 3-tab wrapper |
| `frontend/src/components/SystemView.tsx` | Create — 2-tab wrapper |
| `frontend/src/App.tsx` | Modify — new ViewName, NAV, keyboard shortcuts, view rendering |
| `frontend/src/useRouter.ts` | Modify — new PATH_MAP with legacy redirects |

Existing component files (`SubmitView`, `JobsView`, `ResultsView`, `ArenaView`, `LeaderboardView`, `AnalysisView`, `WorkersView`, `TemplatesView`) remain unchanged — they are wrapped, not rewritten.

---

## 7. Out of Scope

- Changing any backend API
- Modifying existing component internals
- DashboardView changes
- Footer kbd hint strip (update to D/E/C/S)
