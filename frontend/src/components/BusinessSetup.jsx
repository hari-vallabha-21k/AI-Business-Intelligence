import { useState } from 'react'
import { api } from '../api'
import { ErrorNote } from './Primitives'

/** Process doc §1: name, type, currency, branches. */
export default function BusinessSetup({ onCreated }) {
  const [name, setName] = useState('')
  const [businessType, setBusinessType] = useState('restaurant')
  const [currency, setCurrency] = useState('INR')
  const [branches, setBranches] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api.createBusiness({
        name,
        business_type: businessType,
        currency,
        branches: branches
          .split('\n')
          .map((b) => b.trim())
          .filter(Boolean),
      })
      onCreated(created)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card mx-auto max-w-lg space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Create your business</h2>
        <p className="mt-1 text-sm text-muted">
          Branches can be added now or picked up automatically from the files you upload.
        </p>
      </div>

      <div>
        <label className="label" htmlFor="name">Business name</label>
        <input id="name" className="field" required value={name}
               onChange={(e) => setName(e.target.value)} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="label" htmlFor="type">Type</label>
          <select id="type" className="field" value={businessType}
                  onChange={(e) => setBusinessType(e.target.value)}>
            <option value="restaurant">Restaurant</option>
            <option value="retail">Retail</option>
            <option value="services">Services</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="currency">Currency</label>
          <select id="currency" className="field" value={currency}
                  onChange={(e) => setCurrency(e.target.value)}>
            <option value="INR">INR ₹</option>
            <option value="USD">USD $</option>
            <option value="EUR">EUR €</option>
            <option value="GBP">GBP £</option>
          </select>
        </div>
      </div>

      <div>
        <label className="label" htmlFor="branches">Branches (one per line)</label>
        <textarea id="branches" className="field h-24" value={branches}
                  onChange={(e) => setBranches(e.target.value)}
                  placeholder={'Jubilee Hills\nBanjara Hills'} />
      </div>

      <ErrorNote error={error} />
      <button className="btn w-full" disabled={busy}>
        {busy ? 'Creating…' : 'Create business'}
      </button>
    </form>
  )
}
