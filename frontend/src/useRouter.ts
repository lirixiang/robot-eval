import { useState, useEffect, useCallback } from 'react'
import type { ViewName } from './App'

const PATH_MAP: Record<string, ViewName> = {
  '/':            'dashboard',
  '/dashboard':   'dashboard',
  '/submit':      'submit',
  '/jobs':        'jobs',
  '/results':     'results',
  '/workers':     'workers',
  '/leaderboard': 'leaderboard',
  '/analysis':    'analysis',
  '/arena':       'arena',
  '/templates':   'templates',
}

const VIEW_PATH: Record<ViewName, string> = {
  dashboard:   '/',
  submit:      '/submit',
  jobs:        '/jobs',
  results:     '/results',
  workers:     '/workers',
  leaderboard: '/leaderboard',
  analysis:    '/analysis',
  arena:       '/arena',
  templates:   '/templates',
}

function currentView(): ViewName {
  return PATH_MAP[window.location.pathname] ?? 'dashboard'
}

function currentParams(): URLSearchParams {
  return new URLSearchParams(window.location.search)
}

export function useRouter() {
  const [view, setView]     = useState<ViewName>(currentView)
  const [params, setParams] = useState<URLSearchParams>(currentParams)

  // Sync on browser back/forward
  useEffect(() => {
    const onPop = () => {
      setView(currentView())
      setParams(currentParams())
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Navigate to a view, optionally setting query params
  const navigate = useCallback((next: ViewName, nextParams?: Record<string, string>) => {
    const search = nextParams && Object.keys(nextParams).length
      ? '?' + new URLSearchParams(nextParams).toString()
      : ''
    history.pushState(null, '', VIEW_PATH[next] + search)
    setView(next)
    setParams(new URLSearchParams(search))
  }, [])

  // Update a single query param without changing the view (uses replaceState)
  const setParam = useCallback((key: string, value: string | null) => {
    const p = new URLSearchParams(window.location.search)
    if (value === null) p.delete(key)
    else p.set(key, value)
    const search = p.toString() ? '?' + p.toString() : ''
    history.replaceState(null, '', VIEW_PATH[currentView()] + search)
    setParams(new URLSearchParams(p))
  }, [])

  return { view, params, navigate, setParam }
}
