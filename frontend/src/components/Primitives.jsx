import { AVAILABILITY, KIND_LABEL, SEVERITY_STYLE, formatMetric } from '../format'

export function Spinner({ label = 'Loading' }) {
  return <p className="py-8 text-center text-sm text-muted">{label}…</p>
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-md border border-bad/30 bg-bad/5 p-4 text-sm text-bad">
      <p>{error}</p>
      {onRetry && (
        <button className="btn-ghost mt-3 text-bad" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ title, children }) {
  return (
    <div className="card text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-muted">{children}</p>}
    </div>
  )
}

/**
 * A headline figure. An unavailable metric shows why, never a zero — and a
 * figure computed from incomplete or unconfirmed data says so on its face,
 * because a caveated number read as a clean one is worse than no number.
 */
export function MetricTile({ metric, currency, onInspect }) {
  const state = AVAILABILITY[metric.availability] ?? AVAILABILITY.AVAILABLE

  if (!metric.available) {
    return (
      <div className="card">
        <p className="text-xs uppercase tracking-wide text-muted">{metric.label}</p>
        <p className="mt-2 text-2xl font-semibold text-muted">Not available</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">{metric.reason}</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-muted">{metric.label}</p>
        {state.label && (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${state.tone}`}>
            {state.label}
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        {formatMetric(metric.value, metric.unit, currency)}
      </p>
      {metric.caveats?.length > 0 && (
        <p className="mt-2 text-xs leading-relaxed text-warn">{metric.caveats[0]}</p>
      )}
      <button
        className="mt-2 text-xs text-muted underline underline-offset-2 hover:text-ink"
        onClick={() => onInspect(metric)}
      >
        View calculation
      </button>
    </div>
  )
}

/** The evidence behind a number (PRD §25). */
export function CalculationPanel({ metric, currency, onClose }) {
  if (!metric) return null
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/30 p-4 sm:items-center">
      <div className="w-full max-w-lg rounded-lg bg-white p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">How this was calculated</p>
            <h3 className="mt-1 text-lg font-semibold">{metric.label}</h3>
          </div>
          <button className="btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <p className="mt-5 text-2xl font-semibold tabular-nums">
          {formatMetric(metric.value, metric.unit, currency)}
        </p>

        <div className="mt-5">
          <p className="label">Formula</p>
          <code className="block rounded bg-gray-50 p-3 text-sm">{metric.formula}</code>
        </div>

        {metric.provenance?.length > 0 && (
          <div className="mt-4">
            <p className="label">Where this came from</p>
            <ul className="divide-y divide-line rounded border border-line text-sm">
              {metric.provenance.map((source, index) => (
                <li key={index} className="px-3 py-2">
                  <span className="font-medium">{source.concept}</span>{' '}
                  <span className="text-muted">
                    from {source.file} (v{source.version}, {source.rows?.toLocaleString()} rows
                    {source.period_start ? `, ${source.period_start} to ${source.period_end}` : ''})
                  </span>
                  {source.grain && <p className="text-xs text-muted">{source.grain}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {metric.caveats?.length > 0 && (
          <div className="mt-4">
            <p className="label">What to keep in mind</p>
            <ul className="space-y-1 text-sm text-warn">
              {metric.caveats.map((caveat, index) => <li key={index}>{caveat}</li>)}
            </ul>
          </div>
        )}

        {Object.keys(metric.inputs ?? {}).length > 0 && (
          <div className="mt-4">
            <p className="label">Inputs</p>
            <ul className="divide-y divide-line rounded border border-line text-sm">
              {Object.entries(metric.inputs).map(([key, value]) => (
                <li key={key} className="flex justify-between px-3 py-2">
                  <span className="text-muted">{key}</span>
                  <span className="num">{value.toLocaleString('en-IN')}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * A detected problem. The kind badge is load-bearing: it keeps a hypothesis
 * from reading like a fact (PRD §23).
 */
export function FindingCard({ finding }) {
  return (
    <div className={`rounded-md border p-4 ${SEVERITY_STYLE[finding.severity] ?? ''}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-white/70 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide">
          {KIND_LABEL[finding.kind] ?? finding.kind}
        </span>
        <p className="font-medium">{finding.title}</p>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-ink/80">{finding.detail}</p>
      {finding.kind === 'hypothesis' && (
        <p className="mt-2 text-xs italic text-muted">
          A possible explanation, not something the uploaded data proves.
        </p>
      )}
    </div>
  )
}

/** Horizontal bars: enough to rank branches at a glance, no chart library. */
export function BarRow({ label, value, max, unit, currency, highlight }) {
  const width = max > 0 ? Math.max((Math.abs(value) / max) * 100, 1.5) : 0
  return (
    <div className="grid grid-cols-[10rem_1fr_7rem] items-center gap-3 py-1.5">
      <span className="truncate text-sm">{label}</span>
      <span className="h-3 rounded-sm bg-gray-100">
        <span
          className={`block h-3 rounded-sm ${
            value < 0 ? 'bg-bad' : highlight ? 'bg-ink' : 'bg-ink/40'
          }`}
          style={{ width: `${width}%` }}
        />
      </span>
      <span className="num text-sm">{formatMetric(value, unit, currency)}</span>
    </div>
  )
}
