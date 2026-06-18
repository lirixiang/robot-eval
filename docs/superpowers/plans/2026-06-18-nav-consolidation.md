# UI Navigation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate 9 navigation pages into 4 workflow-aligned pages (总览/评测/竞技/系统) by creating 3 wrapper components and updating App.tsx + useRouter.ts.

**Architecture:** Three new container components wrap existing views without modifying them. `EvalView` manages its own `rightTab` state and auto-switches on submit. `ArenaConsolidatedView` and `SystemView` are simple tab wrappers. App.tsx shrinks its ViewName union and NAV array; useRouter.ts adds legacy path redirects. No backend changes.

**Tech Stack:** React 18, TypeScript strict, Tailwind CSS, Vite

## Global Constraints

- TypeScript strict mode — no `any`, no type assertions except where already used
- Tailwind CSS only — no inline styles beyond what existing components already use
- Existing component files (`SubmitView`, `JobsView`, `ResultsView`, `ArenaView`, `LeaderboardView`, `AnalysisView`, `WorkersView`, `TemplatesView`) must NOT be modified
- Frontend build must pass: `cd frontend && npm run build` with zero TypeScript errors
- No backend changes
- Keep `StreamModal` and all existing state management in App.tsx (workers modal etc.)

---

## File Map

```
frontend/src/
  components/
    EvalView.tsx              CREATE — two-column layout wrapping SubmitView + JobsView + ResultsView
    ArenaConsolidatedView.tsx CREATE — 3-tab wrapper: ArenaView | LeaderboardView | AnalysisView
    SystemView.tsx            CREATE — 2-tab wrapper: WorkersView | TemplatesView
  App.tsx                     MODIFY — ViewName, NAV, keyboard shortcuts, view rendering, handleSubmit
  useRouter.ts                MODIFY — PATH_MAP with 4 new paths + 9 legacy redirects
```

---

## Task 1: SystemView — simplest wrapper (2 tabs, no props needed)

**Files:**
- Create: `frontend/src/components/SystemView.tsx`

**Interfaces:**
- Consumes:
  - `WorkersView({ workers, onOpenModal, onRefresh })` — needs `Worker[]`, `(id:number)=>void`, `()=>void`
  - `TemplatesView()` — no props
- Produces: `SystemView({ workers, onOpenModal, onRefresh })` component

- [ ] **Step 1.1: Create `frontend/src/components/SystemView.tsx`**

```tsx
import { useState } from 'react'
import WorkersView  from './WorkersView'
import TemplatesView from './TemplatesView'
import type { Worker } from '../types'

interface Props {
  workers:     Worker[]
  onOpenModal: (id: number) => void
  onRefresh:   () => void
}

type Tab = 'workers' | 'templates'

export default function SystemView({ workers, onOpenModal, onRefresh }: Props) {
  const [tab, setTab] = useState<Tab>('workers')

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
        {([
          { id: 'workers'   as Tab, label: '集群',  icon: 'fa-server'    },
          { id: 'templates' as Tab, label: '模板',  icon: 'fa-file-code' },
        ] as const).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-green-500 text-white'
                : 'border-transparent text-ink-400 hover:text-ink-200'
            }`}
          >
            <i className={`fas ${t.icon} text-[11px]`} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'workers'   && <WorkersView  workers={workers} onOpenModal={onOpenModal} onRefresh={onRefresh} />}
        {tab === 'templates' && <TemplatesView />}
      </div>
    </div>
  )
}
```

- [ ] **Step 1.2: Verify TypeScript accepts the file**

```bash
cd /home/disk/lrx/robot-eval/frontend && npx tsc --noEmit 2>&1 | grep SystemView
```
Expected: no output (no errors for SystemView.tsx)

- [ ] **Step 1.3: Commit**

```bash
git add frontend/src/components/SystemView.tsx
git commit -m "feat: SystemView — 2-tab wrapper for WorkersView + TemplatesView"
```

---

## Task 2: ArenaConsolidatedView — 3-tab wrapper

**Files:**
- Create: `frontend/src/components/ArenaConsolidatedView.tsx`

**Interfaces:**
- Consumes:
  - `ArenaView()` — no props
  - `LeaderboardView()` — no props
  - `AnalysisView({ initialRunIds?: string[] })` — optional prop
- Produces: `ArenaConsolidatedView({ initialAnalysisRunIds?: string[] })` component

- [ ] **Step 2.1: Create `frontend/src/components/ArenaConsolidatedView.tsx`**

```tsx
import { useState } from 'react'
import ArenaView       from './ArenaView'
import LeaderboardView from './LeaderboardView'
import AnalysisView    from './AnalysisView'

interface Props {
  initialAnalysisRunIds?: string[]
}

type Tab = 'battle' | 'leaderboard' | 'analysis'

export default function ArenaConsolidatedView({ initialAnalysisRunIds = [] }: Props) {
  const [tab, setTab] = useState<Tab>('battle')

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
        {([
          { id: 'battle'      as Tab, label: '对战',  icon: 'fa-swords'     },
          { id: 'leaderboard' as Tab, label: '榜单',  icon: 'fa-trophy'     },
          { id: 'analysis'    as Tab, label: '分析',  icon: 'fa-chart-line' },
        ] as const).map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-green-500 text-white'
                : 'border-transparent text-ink-400 hover:text-ink-200'
            }`}
          >
            <i className={`fas ${t.icon} text-[11px]`} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'battle'      && <ArenaView />}
        {tab === 'leaderboard' && <LeaderboardView />}
        {tab === 'analysis'    && <AnalysisView initialRunIds={initialAnalysisRunIds} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2.2: Verify TypeScript**

```bash
cd /home/disk/lrx/robot-eval/frontend && npx tsc --noEmit 2>&1 | grep ArenaConsolidatedView
```
Expected: no output

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/components/ArenaConsolidatedView.tsx
git commit -m "feat: ArenaConsolidatedView — 3-tab wrapper for ArenaView + LeaderboardView + AnalysisView"
```

---

## Task 3: EvalView — two-column layout with auto-tab-switch on submit

**Files:**
- Create: `frontend/src/components/EvalView.tsx`

**Interfaces:**
- Consumes:
  - `SubmitView({ configs, onSubmit })` — `Configs`, `(r: SubmitRequest) => Promise<void>`
  - `JobsView({ jobs, selectedId, logs, onSelect, onCancel, onNavigate, onReproduce? })` — all existing props except `onNavigate` (which previously navigated to 'submit' — now a no-op since submit is always visible)
  - `ResultsView({ results, onNavigateAnalysis? })` — existing props
- Produces:
  ```typescript
  EvalView({
    jobs: Job[],
    results: JobResult[],
    configs: Configs,
    logs: string[],
    selectedJobId: string | null,
    onSelectJob: (id: string) => void,
    onSubmit: (r: SubmitRequest) => Promise<void>,
    onCancel: (id: string) => void,
    onReproduce?: (id: string) => Promise<void>,
    onNavigateAnalysis: (runIds: string[]) => void,
    rightTab: 'queue' | 'results',
    onRightTabChange: (t: 'queue' | 'results') => void,
  })
  ```

Note: `rightTab` and `onRightTabChange` are controlled from App.tsx so the parent can auto-switch to 'queue' after submit.

- [ ] **Step 3.1: Create `frontend/src/components/EvalView.tsx`**

```tsx
import JobsView    from './JobsView'
import ResultsView from './ResultsView'
import SubmitView  from './SubmitView'
import type { Configs, Job, JobResult, SubmitRequest } from '../types'

type RightTab = 'queue' | 'results'

interface Props {
  jobs:                 Job[]
  results:              JobResult[]
  configs:              Configs
  logs:                 string[]
  selectedJobId:        string | null
  onSelectJob:          (id: string) => void
  onSubmit:             (r: SubmitRequest) => Promise<void>
  onCancel:             (id: string) => void
  onReproduce?:         (id: string) => Promise<void>
  onNavigateAnalysis:   (runIds: string[]) => void
  rightTab:             RightTab
  onRightTabChange:     (t: RightTab) => void
}

export default function EvalView({
  jobs, results, configs, logs, selectedJobId,
  onSelectJob, onSubmit, onCancel, onReproduce,
  onNavigateAnalysis, rightTab, onRightTabChange,
}: Props) {
  return (
    <div className="h-full flex overflow-hidden">
      {/* Left: submit form */}
      <div className="w-72 flex-shrink-0 border-r border-ink-800 overflow-y-auto">
        <SubmitView configs={configs} onSubmit={onSubmit} />
      </div>

      {/* Right: tab panel */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Tab bar */}
        <div className="flex-shrink-0 flex items-center gap-1 px-5 pt-3 pb-0 border-b border-ink-800">
          {([
            { id: 'queue'   as RightTab, label: '任务队列', icon: 'fa-list-check'   },
            { id: 'results' as RightTab, label: '评测结果', icon: 'fa-chart-column' },
          ] as const).map(t => (
            <button
              key={t.id}
              onClick={() => onRightTabChange(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors ${
                rightTab === t.id
                  ? 'border-green-500 text-white'
                  : 'border-transparent text-ink-400 hover:text-ink-200'
              }`}
            >
              <i className={`fas ${t.icon} text-[11px]`} />
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {rightTab === 'queue' && (
            <JobsView
              jobs={jobs}
              selectedId={selectedJobId}
              logs={logs}
              onSelect={onSelectJob}
              onCancel={onCancel}
              onNavigate={() => {}}
              onReproduce={onReproduce}
            />
          )}
          {rightTab === 'results' && (
            <ResultsView
              results={results}
              onNavigateAnalysis={onNavigateAnalysis}
            />
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3.2: Verify TypeScript**

```bash
cd /home/disk/lrx/robot-eval/frontend && npx tsc --noEmit 2>&1 | grep EvalView
```
Expected: no output

- [ ] **Step 3.3: Commit**

```bash
git add frontend/src/components/EvalView.tsx
git commit -m "feat: EvalView — two-column layout with submit form + queue/results tabs"
```

---

## Task 4: Update App.tsx and useRouter.ts

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/useRouter.ts`

**Interfaces:**
- Consumes: all three new components from Tasks 1–3
- Produces: working 4-page nav, build passes, all routes functional

- [ ] **Step 4.1: Update `frontend/src/useRouter.ts`**

Replace the existing `PATH_MAP` and `VIEW_PATH` with:

```typescript
const PATH_MAP: Record<string, ViewName> = {
  '/':            'dashboard',
  '/dashboard':   'dashboard',
  '/eval':        'eval',
  '/arena':       'arena',
  '/system':      'system',
  // Legacy: map old paths to their new host page
  '/submit':      'eval',
  '/jobs':        'eval',
  '/results':     'eval',
  '/workers':     'system',
  '/templates':   'system',
  '/leaderboard': 'arena',
  '/analysis':    'arena',
}

const VIEW_PATH: Record<ViewName, string> = {
  dashboard: '/',
  eval:      '/eval',
  arena:     '/arena',
  system:    '/system',
}
```

Also update the `ViewName` import — it will come from the updated App.tsx in the next step, so make sure the import line stays as:
```typescript
import type { ViewName } from './App'
```

- [ ] **Step 4.2: Update `frontend/src/App.tsx`**

Make these changes to App.tsx (do NOT remove existing state/handlers — only modify the parts listed):

**a) Update ViewName type** (line ~14):
```typescript
export type ViewName = 'dashboard' | 'eval' | 'arena' | 'system'
```

**b) Add evalRightTab state** (after `analysisRunIds` state, ~line 90):
```typescript
const [evalRightTab, setEvalRightTab] = useState<'queue' | 'results'>('queue')
```

**c) Update handleSubmit** to auto-switch eval tab (replace existing):
```typescript
const handleSubmit = async (req: SubmitRequest) => {
  const job = await submitJob(req)
  await refreshJobs()
  navigate('eval')
  setEvalRightTab('queue')
  selectJob(job.id)
}
```

**d) Update keyboard shortcuts** (replace existing onKey handler body):
```typescript
const onKey = (e: KeyboardEvent) => {
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
  if (e.key === 'd' || e.key === 'D') navigate('dashboard')
  if (e.key === 'e' || e.key === 'E') navigate('eval')
  if (e.key === 'c' || e.key === 'C') navigate('arena')
  if (e.key === 's' || e.key === 'S') navigate('system')
}
```

**e) Update NAV array** (replace existing):
```typescript
const NAV: { id: ViewName; label: string; icon: string }[] = [
  { id: 'dashboard', label: '总览', icon: 'fa-gauge-high' },
  { id: 'eval',      label: '评测', icon: 'fa-list-check' },
  { id: 'arena',     label: '竞技', icon: 'fa-swords'     },
  { id: 'system',    label: '系统', icon: 'fa-server'     },
]
```

**f) Update imports** — add the three new components at the top:
```typescript
import EvalView               from './components/EvalView'
import ArenaConsolidatedView  from './components/ArenaConsolidatedView'
import SystemView             from './components/SystemView'
```

**g) Replace the view rendering block** (the entire `<main>` content, lines ~228–260):
```tsx
<main className="flex-1 min-h-0">
  {view === 'dashboard' && (
    <DashboardView
      jobs={jobs} results={results} workers={workers}
      activeJob={activeJob} logs={logs}
      onSelectJob={selectJob} onOpenModal={setModalWorker}
      onNavigate={navigate}
      onQuickSubmit={handleSubmit}
      configs={configs}
    />
  )}
  {view === 'eval' && (
    <EvalView
      jobs={jobs}
      results={results}
      configs={configs}
      logs={logs}
      selectedJobId={view === 'eval' ? (params.get('id') ?? null) : null}
      onSelectJob={selectJob}
      onSubmit={handleSubmit}
      onCancel={handleCancel}
      onReproduce={handleReproduce}
      onNavigateAnalysis={(runIds) => { setAnalysisRunIds(runIds); navigate('arena') }}
      rightTab={evalRightTab}
      onRightTabChange={setEvalRightTab}
    />
  )}
  {view === 'arena' && (
    <ArenaConsolidatedView initialAnalysisRunIds={analysisRunIds} />
  )}
  {view === 'system' && (
    <SystemView workers={workers} onOpenModal={setModalWorker} onRefresh={refreshWorkers} />
  )}
</main>
```

**h) Update footer kbd hints** — replace the kbd hint span block in the footer:
```tsx
<span><kbd className="kbd">D</kbd> 总览</span>
<span><kbd className="kbd">E</kbd> 评测</span>
<span><kbd className="kbd">C</kbd> 竞技</span>
<span><kbd className="kbd">S</kbd> 系统</span>
```

**i) Remove** `selectedJobId` computed at the top — it's now computed inline in the eval view block above. Delete this line:
```typescript
// DELETE this line:
const selectedJobId = view === 'jobs' ? (params.get('id') ?? null) : null
```

Also remove the `useEffect` that re-attaches log stream `if (view === 'jobs' && selectedJobId)` — replace with `if (view === 'eval' && ...)`:
```typescript
useEffect(() => {
  if (view === 'eval' && params.get('id')) {
    const id = params.get('id')!
    unsubRef.current?.()
    unsubRef.current = streamLogs(
      id,
      (line) => setLogs(prev => [...prev.slice(-500), line]),
      () => { refreshJobs(); refreshResults() },
    )
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [view, params.get('id')])
```

- [ ] **Step 4.3: Run TypeScript check**

```bash
cd /home/disk/lrx/robot-eval/frontend && npx tsc --noEmit 2>&1
```
Expected: no errors. Fix any type errors before proceeding.

- [ ] **Step 4.4: Build**

```bash
cd /home/disk/lrx/robot-eval/frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in Xs`

- [ ] **Step 4.5: Smoke test in browser**

With the platform running, verify:
1. `/` loads dashboard ✓
2. `/eval` loads EvalView with submit form on left, queue tab on right ✓
3. `/arena` loads ArenaConsolidatedView with 对战/榜单/分析 tabs ✓
4. `/system` loads SystemView with 集群/模板 tabs ✓
5. `/jobs` redirects to `/eval` (legacy path) ✓
6. `/templates` redirects to `/system` ✓
7. `/leaderboard` redirects to `/arena` ✓
8. Submit a job: verify it auto-switches to queue tab and highlights the new job ✓
9. Keyboard shortcuts D/E/C/S all work ✓

- [ ] **Step 4.6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/useRouter.ts
git commit -m "feat: consolidate 9-page nav into 4 workflow pages (评测/竞技/系统/总览)"
```

---

## Self-Review

**Spec coverage:**
- ✅ 4-page nav (dashboard/eval/arena/system) — Task 4
- ✅ EvalView two-column layout with submit+queue+results — Task 3
- ✅ Auto-switch to queue tab on submit — Task 4 (handleSubmit)
- ✅ ArenaConsolidatedView 3-tab (对战/榜单/分析) — Task 2
- ✅ SystemView 2-tab (集群/模板) — Task 1
- ✅ Keyboard shortcuts D/E/C/S — Task 4
- ✅ Legacy path redirects — Task 4 (useRouter.ts)
- ✅ Footer kbd hints updated — Task 4
- ✅ Existing components not modified — all tasks wrap, never rewrite
- ✅ analysisRunIds flow: ResultsView → onNavigateAnalysis → setAnalysisRunIds → navigate('arena') — Task 4 view rendering

**Placeholder scan:** No TBD/TODO found.

**Type consistency:**
- `RightTab = 'queue' | 'results'` defined in EvalView.tsx, referenced as `rightTab: RightTab` in Props, matches `evalRightTab` state type in App.tsx ✓
- `ViewName` updated to 4 values in App.tsx, imported by useRouter.ts ✓
- `onNavigate` in JobsView receives `() => {}` no-op (previously navigated to 'submit', now irrelevant since submit is always visible) ✓
- `selectedJobId` removed from top-level const, computed inline in eval view block ✓
