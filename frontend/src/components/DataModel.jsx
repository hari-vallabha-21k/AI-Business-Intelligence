import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote, Spinner } from './Primitives'

/**
 * What the system understands about the business (PRD §17): the datasets it
 * read, what one row of each means, the entities it resolved and the links it
 * validated between files. Shown because the analysis is only as trustworthy
 * as this model, and the user is the one who can spot a wrong reading.
 */
export default function DataModel({ business }) {
  const [model, setModel] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.model(business.id).then(setModel).catch((err) => setError(err.message))
  }, [business.id])

  if (error) return <ErrorNote error={error} />
  if (!model) return <Spinner label="Reading your data model" />

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-lg font-semibold">What we read</h2>
        <p className="mb-3 text-sm text-muted">
          One row of each file, as the system understood it.
        </p>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2">File</th>
                <th className="py-2">Understood as</th>
                <th className="py-2">One row is</th>
                <th className="py-2 text-right">Rows</th>
                <th className="py-2">Period</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {model.datasets.map((dataset, index) => (
                <tr key={index}>
                  <td className="py-2 font-medium">{dataset.file}</td>
                  <td className="py-2">
                    {(dataset.classification?.category ?? 'unknown').replace(/_/g, ' ')}
                    <span className="ml-2 text-xs text-muted">
                      {Math.round((dataset.classification?.confidence ?? 0) * 100)}%
                    </span>
                    {dataset.classification?.needs_review && (
                      <span className="ml-2 rounded bg-warn/10 px-1.5 py-0.5 text-[10px] text-warn">
                        confirm
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-muted">{dataset.grain?.description ?? '—'}</td>
                  <td className="num py-2">{dataset.rows?.toLocaleString()}</td>
                  <td className="py-2 text-muted">
                    {dataset.period_start ? `${dataset.period_start} → ${dataset.period_end}` : 'not set'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {model.entities.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Branches and departments we identified</h2>
          <p className="mb-3 text-sm text-muted">
            Different spellings of the same thing, grouped. Your original values are kept.
          </p>
          <div className="card space-y-2">
            {model.entities.map((entity, index) => (
              <div key={index} className="flex flex-wrap items-baseline gap-2 text-sm">
                <span className="font-medium">{entity.name}</span>
                <span className="text-xs uppercase tracking-wide text-muted">
                  {entity.type.toLowerCase()}
                </span>
                {entity.aliases.length > 1 && (
                  <span className="text-xs text-muted">
                    also written: {entity.aliases.filter((a) => a !== entity.name).join(', ')}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {model.relationships.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Links between your files</h2>
          <p className="mb-3 text-sm text-muted">
            Only links the data actually supports — checked, not guessed from column names.
          </p>
          <div className="card space-y-2 text-sm">
            {model.relationships.map((rel, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2">
                <code className="rounded bg-gray-50 px-1.5 py-0.5 text-xs">
                  {rel.from_column} → {rel.to_column}
                </code>
                <span className="text-xs text-muted">{rel.kind}</span>
                {!rel.is_safe_join && (
                  <span className="rounded bg-warn/10 px-1.5 py-0.5 text-[10px] text-warn">
                    incomplete
                  </span>
                )}
                <span className="text-xs text-muted">{rel.reason}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {model.notes?.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Decisions we made</h2>
          <ul className="card space-y-2 text-sm text-muted">
            {model.notes.map((note, index) => <li key={index}>{note}</li>)}
          </ul>
        </section>
      )}
    </div>
  )
}
