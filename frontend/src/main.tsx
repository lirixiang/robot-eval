import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(e: Error) { return { error: e } }
  render() {
    if (this.state.error) {
      const e = this.state.error as Error
      return (
        <div style={{ background: '#07090d', color: '#ef4444', padding: 32, fontFamily: 'monospace', fontSize: 13 }}>
          <div style={{ color: '#d4a857', marginBottom: 8, fontSize: 16 }}>⚠ RoboEval — Render Error</div>
          <div style={{ color: '#fca5a5', marginBottom: 16 }}>{e.message}</div>
          <pre style={{ color: '#8b93a7', overflow: 'auto', fontSize: 11 }}>{e.stack}</pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 16, background: '#1c2230', color: '#d6dae3', border: '1px solid #2a3142', padding: '6px 16px', borderRadius: 5, cursor: 'pointer' }}>
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
)
