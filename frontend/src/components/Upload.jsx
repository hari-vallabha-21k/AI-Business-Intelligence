import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote } from './Primitives'

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 }
const SEVERITY_STYLE = {
  critical: 'border-bad/30 bg-bad/5 text-bad',
  warning: 'border-warn/30 bg-warn/5 text-warn',
  info: 'border-line bg-gray-50 text-muted',
}

export default function Upload({ business, onIngested }) {
  const [file, setFile] = useState(null)
  const [datasetName, setDatasetName] = useState('')
  const [branch, setBranch] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const uploaded = await api.upload(business.id, file, {
        dataset_name: datasetName || file.name.replace(/\.[^.]+$/, ''),
        branch,
        period_start: periodStart,
        period_end: periodEnd,
      })
      setResult(uploaded)
      onIngested?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="card space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Upload data</h2>
          <p className="mt-1 text-sm text-muted">
            Excel or CSV. Sales, employees and expenses can all be uploaded — the columns do
            not need to follow any fixed format.
          </p>
        </div>

        <div>
          <label className="label" htmlFor="file">File</label>
          <input
            id="file"
            className="field"
            type="file"
            accept=".csv,.tsv,.xlsx,.xlsm,.xls"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="dataset">Dataset name</label>
            <input id="dataset" className="field" value={datasetName}
                   onChange={(e) => setDatasetName(e.target.value)}
                   placeholder="Sales" />
          </div>
          <div>
            <label className="label" htmlFor="branch">Branch (if the file has no branch column)</label>
            <select id="branch" className="field" value={branch}
                    onChange={(e) => setBranch(e.target.value)}>
              <option value="">Detect from the file</option>
              {business.branches.map((b) => (
                <option key={b.id} value={b.name}>{b.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="start">Period start (optional)</label>
            <input id="start" className="field" type="date" value={periodStart}
                   onChange={(e) => setPeriodStart(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="end">Period end (optional)</label>
            <input id="end" className="field" type="date" value={periodEnd}
                   onChange={(e) => setPeriodEnd(e.target.value)} />
          </div>
        </div>
        <p className="text-xs text-muted">
          A payroll or expense file with no date column needs a period, otherwise it cannot be
          included in month-by-month analysis.
        </p>

        <ErrorNote error={error} />
        <button className="btn" disabled={!file || busy}>
          {busy ? 'Analysing…' : 'Upload and analyse'}
        </button>
      </form>

      {result && <UploadReport result={result} onUpdated={(r) => { setResult(r); onIngested?.() }} />}
    </div>
  )
}

function UploadReport({ result, onUpdated }) {
  const issues = [...result.quality_issues].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  )

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold">{result.filename}</h3>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase tracking-wide">
            {result.entity_kind} data
          </span>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <Stat label="Rows" value={result.row_count.toLocaleString()} />
          <Stat label="Columns" value={result.column_count} />
          <Stat label="Period start" value={result.period_start ?? 'Not set'} />
          <Stat label="Period end" value={result.period_end ?? 'Not set'} />
        </dl>

        {result.new_concepts.length > 0 && (
          <p className="mt-4 rounded-md border border-line bg-gray-50 p-3 text-sm">
            New information detected in this file:{' '}
            <strong>{result.new_concepts.join(', ')}</strong>. It is now included in analysis.
          </p>
        )}
      </div>

      <MappingTable
        mappings={result.mappings}
        versionId={result.dataset_version_id}
        onUpdated={onUpdated}
      />

      {issues.length > 0 && (
        <div className="card">
          <h3 className="font-semibold">Data quality</h3>
          <ul className="mt-3 space-y-2">
            {issues.map((issue, index) => (
              <li key={index}
                  className={`rounded-md border p-3 text-sm ${SEVERITY_STYLE[issue.severity]}`}>
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.cleaning_log.length > 0 && (
        <div className="card">
          <h3 className="font-semibold">What we cleaned</h3>
          <p className="mt-1 text-sm text-muted">
            Your original values are kept unchanged alongside the cleaned ones.
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {result.cleaning_log.map((entry, index) => (
              <li key={index} className="text-muted">
                {describeCleaning(entry)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function describeCleaning(entry) {
  switch (entry.type) {
    case 'label_normalisation':
      return `"${entry.variants.join('", "')}" treated as ${entry.canonical} (${entry.rows_affected} rows)`
    case 'role_normalisation':
      return `Role spellings standardised in ${entry.column} (${entry.rows_affected} rows)`
    case 'non_numeric_dropped':
      return `${entry.rows_affected} values in ${entry.column} could not be read as numbers`
    case 'measure_combined':
      return `${entry.column} added into ${entry.concept}`
    case 'branch_defaulted':
      return `All rows attributed to ${entry.value}`
    default:
      return entry.type
  }
}

function Stat({ label, value }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}

/** PRD §14: low-confidence columns are asked about, not assumed. */
function MappingTable({ mappings, versionId, onUpdated }) {
  const [concepts, setConcepts] = useState([])
  const [pending, setPending] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.concepts().then(setConcepts).catch(() => setConcepts([]))
  }, [])

  const unresolved = mappings.filter((m) => m.needs_confirmation || !m.concept)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updates = Object.entries(pending).map(([id, concept]) => ({
        mapping_id: Number(id),
        concept: concept === '__ignore__' ? null : concept,
        remember: true,
      }))
      if (updates.length) {
        const updated = await api.confirmMappings(versionId, updates)
        onUpdated(updated)
        setPending({})
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <h3 className="font-semibold">What each column means</h3>
      <p className="mt-1 text-sm text-muted">
        {unresolved.length === 0
          ? 'Every column was identified confidently.'
          : `${unresolved.length} column(s) need your confirmation before they are used.`}
      </p>

      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="py-2">Column</th>
            <th className="py-2">Understood as</th>
            <th className="py-2">Confidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {mappings.map((mapping) => {
            const needs = mapping.needs_confirmation || !mapping.concept
            return (
              <tr key={mapping.id}>
                <td className="py-2 font-medium">{mapping.source_column}</td>
                <td className="py-2">
                  {needs ? (
                    <select
                      className="field py-1"
                      value={pending[mapping.id] ?? mapping.concept ?? ''}
                      onChange={(e) =>
                        setPending({ ...pending, [mapping.id]: e.target.value })
                      }
                    >
                      <option value="">Select what this is…</option>
                      {concepts.map((c) => (
                        <option key={c.name} value={c.name}>{c.label}</option>
                      ))}
                      <option value="__ignore__">Ignore this column</option>
                    </select>
                  ) : (
                    <span>{conceptLabel(concepts, mapping.concept)}</span>
                  )}
                  <p className="mt-1 text-xs text-muted">{mapping.rationale}</p>
                </td>
                <td className="py-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      mapping.confidence === 'high'
                        ? 'bg-good/10 text-good'
                        : mapping.confidence === 'medium'
                          ? 'bg-warn/10 text-warn'
                          : 'bg-gray-100 text-muted'
                    }`}
                  >
                    {mapping.confirmed_by_user ? 'confirmed' : mapping.confidence}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <ErrorNote error={error} />
      {Object.keys(pending).length > 0 && (
        <button className="btn mt-4" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : 'Save and remember these'}
        </button>
      )}
    </div>
  )
}

function conceptLabel(concepts, name) {
  return concepts.find((c) => c.name === name)?.label ?? name ?? 'Not used'
}
