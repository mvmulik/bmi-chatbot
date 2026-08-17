import { useEffect, useState } from 'react'
import './App.css'

type HealthStatus = 'checking' | 'healthy' | 'unreachable'

function App() {
  const [health, setHealth] = useState<HealthStatus>('checking')

  useEffect(() => {
    let cancelled = false

    async function checkHealth() {
      try {
        const response = await fetch('/api/health')
        if (!cancelled) {
          setHealth(response.ok ? 'healthy' : 'unreachable')
        }
      } catch {
        if (!cancelled) {
          setHealth('unreachable')
        }
      }
    }

    void checkHealth()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="page">
      <header className="header">
        <p className="brand">BMI Chatbot</p>
        <h1>Project scaffold is ready</h1>
        <p className="subtitle">
          React frontend and FastAPI backend are wired for local development.
          Crawler and chat features will be added next.
        </p>
      </header>

      <section className="status" aria-live="polite">
        <h2>Backend status</h2>
        <p className={`badge badge-${health}`}>
          {health === 'checking' && 'Checking API…'}
          {health === 'healthy' && 'API healthy at /health'}
          {health === 'unreachable' && 'API unreachable — start the backend on port 8000'}
        </p>
      </section>
    </main>
  )
}

export default App
