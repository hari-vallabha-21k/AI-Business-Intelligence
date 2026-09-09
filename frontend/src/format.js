// Formatting rules shared by every view.

const COMPACT = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function formatMetric(value, unit, currency = 'INR') {
  if (value === null || value === undefined) return '—'
  if (unit === 'percent') return `${value.toFixed(1)}%`
  if (unit === 'count') return COMPACT.format(value)
  if (unit === 'currency') return `${symbolFor(currency)}${COMPACT.format(value)}`
  return COMPACT.format(Math.round(value * 100) / 100)
}

export function symbolFor(currency) {
  return { INR: '₹', USD: '$', EUR: '€', GBP: '£' }[currency] ?? `${currency} `
}

export function formatChange(percent) {
  if (percent === null || percent === undefined) return '—'
  const arrow = percent > 0 ? '▲' : percent < 0 ? '▼' : '—'
  return `${arrow} ${Math.abs(percent).toFixed(1)}%`
}

// Favourable/unfavourable comes from the API, which knows whether a rising
// number is good for that particular metric.
export function toneFor(favourable) {
  if (favourable === true) return 'text-good'
  if (favourable === false) return 'text-bad'
  return 'text-muted'
}

export const SEVERITY_STYLE = {
  high: 'border-bad/30 bg-bad/5 text-bad',
  medium: 'border-warn/30 bg-warn/5 text-warn',
  low: 'border-line bg-gray-50 text-muted',
}

// How far a figure can be trusted. AVAILABLE is unremarkable and shows nothing;
// the others always carry their reason.
export const AVAILABILITY = {
  AVAILABLE: { label: null, tone: '' },
  PARTIALLY_AVAILABLE: {
    label: 'Incomplete data',
    tone: 'bg-warn/10 text-warn',
  },
  NEEDS_CONFIRMATION: {
    label: 'Needs your confirmation',
    tone: 'bg-warn/10 text-warn',
  },
  UNAVAILABLE: { label: 'Not available', tone: 'bg-gray-100 text-muted' },
}

export const KIND_LABEL = {
  fact: 'Fact',
  driver: 'Supported driver',
  hypothesis: 'Hypothesis',
}
