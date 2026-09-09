import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { formatChange, formatMetric, toneFor } from '../format'
import {
  BarRow,
  CalculationPanel,
  Empty,
  ErrorNote,
  FindingCard,
  MetricTile,
  Spinner,
} from './Primitives'

export default function Dashboard({ business, period }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [inspecting, setInspecting] = useState(null)

  const load = useCallback(() => {
    setError(null)
    setData(null)
    const params = { period_start: period.start, period_end: period.end }
    Promise.all([
      api.overview(business.id, params),
      api.compareBranches(business.id, params).catch(() => null),
    ])
      .then(([overview, branches]) => setData({ overview, branches }))
      .catch((err) => setError(err.message))
  }, [business.id, period.start, period.end])

  useEffect(load, [load])

  if (error) {
    return (
      <Empty title="Nothing to show yet">
        {error}
      </Empty>
    )
  }
  if (!data) return <Spinner label="Calculating" />

  const { overview, branches } = data
  const currency = overview.business.currency

  return (
    <div className="space-y-8">
      {overview.notes?.length > 0 && (
        <div className="rounded-md border border-warn/30 bg-warn/5 p-4 text-sm text-warn">
          {overview.notes.map((note, i) => <p key={i}>{note}</p>)}
        </div>
      )}

      <section>
        <SectionHeading
          title="Company overview"
          subtitle={`${overview.scope.branches.length} branch(es) · ${describePeriod(period)}`}
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {overview.headline.map((metric) => (
            <MetricTile key={metric.key} metric={metric} currency={currency}
                        onInspect={setInspecting} />
          ))}
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {['employee_cost_ratio', 'operating_margin', 'revenue_per_employee']
            .map((key) => overview.metrics[key])
            .filter(Boolean)
            .map((metric) => (
              <MetricTile key={metric.key} metric={metric} currency={currency}
                          onInspect={setInspecting} />
            ))}
        </div>
      </section>

      {branches && branches.members.length > 1 && (
        <BranchSection comparison={branches} currency={currency} />
      )}

      <Readiness readiness={overview.readiness} />

      <CalculationPanel metric={inspecting} currency={currency}
                        onClose={() => setInspecting(null)} />
    </div>
  )
}

function BranchSection({ comparison, currency }) {
  const revenue = comparison.metrics.find((m) => m.key === 'total_revenue')
  const rankable = comparison.metrics.filter((m) => m.comparable)

  return (
    <section>
      <SectionHeading title="Branch performance"
                      subtitle="Ranked only on metrics every branch can supply" />

      {revenue?.comparable && (
        <div className="card">
          <p className="label">Revenue</p>
          {comparison.members
            .slice()
            .sort((a, b) => revenue.values[b] - revenue.values[a])
            .map((member) => (
              <BarRow
                key={member}
                label={member}
                value={revenue.values[member]}
                max={Math.max(...Object.values(revenue.values).map(Math.abs))}
                unit="currency"
                currency={currency}
                highlight={member === revenue.best}
              />
            ))}
        </div>
      )}

      <div className="card mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="py-2 text-left">Metric</th>
              {comparison.members.map((member) => (
                <th key={member} className="py-2 text-right">{member}</th>
              ))}
              <th className="py-2 text-right">Best</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rankable.map((row) => (
              <tr key={row.key}>
                <td className="py-2">{row.label}</td>
                {comparison.members.map((member) => (
                  <td key={member} className="num py-2">
                    {formatMetric(row.values[member], row.unit, currency)}
                  </td>
                ))}
                <td className="num py-2 font-medium">
                  {row.best ?? (
                    <span className="cursor-help font-normal text-muted" title={row.note}>
                      —
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {comparison.metrics.some((m) => !m.comparable) && (
          <p className="mt-3 text-xs text-muted">
            Hidden:{' '}
            {comparison.metrics.filter((m) => !m.comparable).map((m) => m.label).join(', ')} —
            not available for every branch, so ranking would be misleading.
          </p>
        )}
        {rankable.some((m) => !m.best) && (
          <p className="mt-2 text-xs text-muted">
            Not ranked:{' '}
            {rankable.filter((m) => !m.best).map((m) => m.label).join(', ')} — absolute totals
            follow branch size, so compare the ratios instead.
          </p>
        )}
      </div>

      {comparison.findings?.length > 0 && (
        <div className="mt-4 space-y-3">
          {comparison.findings.map((finding, i) => <FindingCard key={i} finding={finding} />)}
        </div>
      )}
    </section>
  )
}

function Readiness({ readiness }) {
  const blocked = readiness.filter((r) => !r.available)
  if (blocked.length === 0) return null
  return (
    <section>
      <SectionHeading title="What your data cannot answer yet"
                      subtitle="Upload the missing information to unlock these" />
      <ul className="card space-y-2 text-sm">
        {blocked.map((row) => (
          <li key={row.metric} className="flex gap-3">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted" />
            <span className="text-muted">{row.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Period-over-period view with findings and branch-level drivers. */
export function PeriodComparison({ business }) {
  const [range, setRange] = useState({
    current_start: '', current_end: '', previous_start: '', previous_end: '',
  })
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const ready = Object.values(range).every(Boolean)

  async function run(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setData(null)
    try {
      setData(await api.comparePeriods(business.id, range))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={run} className="card">
        <h2 className="text-lg font-semibold">Compare two periods</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['current_start', 'This period from'],
            ['current_end', 'to'],
            ['previous_start', 'Compare with from'],
            ['previous_end', 'to'],
          ].map(([key, label]) => (
            <div key={key}>
              <label className="label" htmlFor={key}>{label}</label>
              <input id={key} className="field" type="date" value={range[key]}
                     onChange={(e) => setRange({ ...range, [key]: e.target.value })} />
            </div>
          ))}
        </div>
        <button className="btn mt-4" disabled={!ready || busy}>
          {busy ? 'Comparing…' : 'Compare'}
        </button>
      </form>

      <ErrorNote error={error} />

      {data && (
        <>
          {data.findings.length + data.drivers.length > 0 && (
            <section>
              <SectionHeading title="What changed and why"
                              subtitle="Facts and supported drivers are separated from hypotheses" />
              <div className="space-y-3">
                {[...data.findings, ...data.drivers].map((finding, i) => (
                  <FindingCard key={i} finding={finding} />
                ))}
              </div>
            </section>
          )}

          <section>
            <SectionHeading title="Every metric" />
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                    <th className="py-2 text-left">Metric</th>
                    <th className="py-2 text-right">Previous</th>
                    <th className="py-2 text-right">Current</th>
                    <th className="py-2 text-right">Change</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.changes.map((change) => (
                    <tr key={change.key}>
                      <td className="py-2">{change.label}</td>
                      <td className="num py-2">{formatMetric(change.previous, change.unit)}</td>
                      <td className="num py-2">{formatMetric(change.current, change.unit)}</td>
                      <td className={`num py-2 font-medium ${toneFor(change.favourable)}`}>
                        {formatChange(change.percent)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

function SectionHeading({ title, subtitle }) {
  return (
    <div className="mb-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
    </div>
  )
}

function describePeriod(period) {
  if (!period.start && !period.end) return 'All periods'
  return `${period.start || 'start'} to ${period.end || 'today'}`
}
