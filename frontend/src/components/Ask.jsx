import { useState } from 'react'
import { api } from '../api'
import { formatMetric } from '../format'
import { ErrorNote, FindingCard } from './Primitives'

const SUGGESTIONS = [
  'What is total revenue?',
  'Which branch is performing best?',
  'How much are we spending on salaries?',
  'What changed last month?',
]

/**
 * Ask your data. The answer is calculated before it is written: the evidence
 * panel below every answer is the calculation itself, not a citation added
 * afterwards.
 */
export default function Ask({ business }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run(text) {
    const asked = (text ?? question).trim()
    if (!asked) return
    setQuestion(asked)
    setBusy(true)
    setError(null)
    setAnswer(null)
    try {
      setAnswer(await api.ask(business.id, asked))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault()
          run()
        }}
      >
        <h2 className="text-lg font-semibold">Ask your data</h2>
        <p className="mt-1 text-sm text-muted">
          Answers are calculated from your uploads. If the data can&apos;t support an
          answer, you&apos;ll be told why rather than given a guess.
        </p>

        <div className="mt-4 flex gap-2">
          <input
            className="field"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Why did profit fall in March?"
          />
          <button className="btn" disabled={busy || !question.trim()}>
            {busy ? 'Working…' : 'Ask'}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((text) => (
            <button
              key={text}
              type="button"
              className="btn-ghost text-xs"
              onClick={() => run(text)}
            >
              {text}
            </button>
          ))}
        </div>
      </form>

      <ErrorNote error={error} />
      {answer && <AnswerPanel answer={answer} currency={business.currency} />}
    </div>
  )
}

function AnswerPanel({ answer, currency }) {
  const unanswered = answer.status !== 'answered'

  return (
    <div className="space-y-4">
      <div className={`card ${unanswered ? 'border-warn/40 bg-warn/5' : ''}`}>
        <p className="text-lg font-medium">{answer.headline}</p>
        {answer.explanation && (
          <p className="mt-3 leading-relaxed text-ink/80">{answer.explanation}</p>
        )}
        {answer.limitations?.length > 0 && (
          <ul className="mt-4 space-y-1 text-sm text-muted">
            {answer.limitations.map((item, index) => (
              <li key={index}>• {item}</li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs text-muted">
          Understood as: {answer.question.intent.replace('_', ' ')}
          {answer.question.period &&
            ` · ${answer.question.period[0]} to ${answer.question.period[1]}`}
          {answer.question.branches?.length > 0 &&
            ` · ${answer.question.branches.join(', ')}`}
          {answer.interpreter !== 'none' && ` · explained by ${answer.interpreter}`}
        </p>
      </div>

      {answer.findings?.length > 0 && (
        <div className="space-y-3">
          {answer.findings.map((finding, index) => (
            <FindingCard key={index} finding={finding} />
          ))}
        </div>
      )}

      {answer.evidence?.length > 0 && (
        <div className="card">
          <h3 className="font-semibold">The numbers behind this</h3>
          <table className="mt-3 w-full text-sm">
            <tbody className="divide-y divide-line">
              {answer.evidence.map((row, index) => (
                <tr key={index}>
                  <td className="py-2">{row.label}</td>
                  <td className="num py-2">
                    {row.values
                      ? Object.entries(row.values)
                          .map(([k, v]) => `${k}: ${formatMetric(v, row.unit, currency)}`)
                          .join('  ·  ')
                      : formatMetric(
                          row.value ?? row.current,
                          row.unit,
                          currency,
                        )}
                  </td>
                  <td className="py-2 text-right text-xs text-muted">
                    {row.formula ?? row.scope}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
