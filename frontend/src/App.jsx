import { useCallback, useEffect, useState } from 'react'
import { api, clearToken, getToken } from './api'
import Auth from './components/Auth'
import BusinessSetup from './components/BusinessSetup'
import Dashboard, { PeriodComparison } from './components/Dashboard'
import Upload from './components/Upload'
import { Empty, ErrorNote, Spinner } from './components/Primitives'

const TABS = [
  ['dashboard', 'Dashboard'],
  ['periods', 'Compare periods'],
  ['upload', 'Upload data'],
]

export default function App() {
  const [authed, setAuthed] = useState(Boolean(getToken()))
  const [businesses, setBusinesses] = useState(null)
  const [businessId, setBusinessId] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [period, setPeriod] = useState({ start: '', end: '' })
  const [error, setError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const loadBusinesses = useCallback(() => {
    api
      .businesses()
      .then((list) => {
        setBusinesses(list)
        setBusinessId((current) => current ?? list[0]?.id ?? null)
      })
      .catch((err) => {
        if (err.status === 401) {
          clearToken()
          setAuthed(false)
        } else {
          setError(err.message)
        }
      })
  }, [])

  useEffect(() => {
    if (authed) loadBusinesses()
  }, [authed, loadBusinesses])

  if (!authed) {
    return <Auth onAuthenticated={() => { setAuthed(true); setError(null) }} />
  }

  if (error) return <div className="mx-auto max-w-3xl p-6"><ErrorNote error={error} /></div>
  if (businesses === null) return <Spinner />

  if (businesses.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <BusinessSetup
          onCreated={(created) => {
            setBusinesses([created])
            setBusinessId(created.id)
            setTab('upload')
          }}
        />
      </div>
    )
  }

  const business = businesses.find((b) => b.id === businessId) ?? businesses[0]

  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <select
            className="field w-auto font-medium"
            value={business.id}
            onChange={(e) => setBusinessId(Number(e.target.value))}
          >
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>

          <nav className="flex gap-1">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  tab === key ? 'bg-ink text-white' : 'text-muted hover:bg-gray-50'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          {tab === 'dashboard' && (
            <div className="ml-auto flex items-center gap-2 text-sm">
              <label className="text-muted" htmlFor="from">Period</label>
              <input id="from" className="field w-auto py-1" type="date" value={period.start}
                     onChange={(e) => setPeriod({ ...period, start: e.target.value })} />
              <span className="text-muted">to</span>
              <input className="field w-auto py-1" type="date" value={period.end}
                     onChange={(e) => setPeriod({ ...period, end: e.target.value })} />
              {(period.start || period.end) && (
                <button className="btn-ghost" onClick={() => setPeriod({ start: '', end: '' })}>
                  Clear
                </button>
              )}
            </div>
          )}

          <button
            className="btn-ghost ml-auto"
            onClick={() => { clearToken(); setAuthed(false); setBusinesses(null) }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {tab === 'dashboard' && (
          <Dashboard key={refreshKey} business={business} period={period} />
        )}
        {tab === 'periods' && <PeriodComparison business={business} />}
        {tab === 'upload' && (
          <Upload
            business={business}
            onIngested={() => { setRefreshKey((k) => k + 1); loadBusinesses() }}
          />
        )}
      </main>
    </div>
  )
}
