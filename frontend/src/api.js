// Thin API client. The token lives in localStorage; every call attaches it and
// surfaces the server's own message, which is written for the user to read.

const TOKEN_KEY = 'bi.token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function messageFrom(payload, fallback) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail?.errors)) return detail.errors.map((e) => e.message).join(' ')
  if (Array.isArray(detail)) return detail.map((e) => e.msg ?? String(e)).join(' ')
  return fallback
}

async function request(path, { method = 'GET', body, form, params } = {}) {
  const url = new URL(path, window.location.origin)
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v))
    else url.searchParams.set(key, value)
  })

  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body) headers['Content-Type'] = 'application/json'

  const response = await fetch(url, {
    method,
    headers,
    body: form ?? (body ? JSON.stringify(body) : undefined),
  })

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      messageFrom(payload, `Request failed (${response.status})`),
      response.status,
    )
  }
  return payload
}

export const api = {
  register: (email, password) =>
    request('/api/auth/register', { method: 'POST', body: { email, password } }),

  login: (email, password) => {
    const form = new URLSearchParams({ username: email, password })
    return fetch('/api/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    }).then(async (r) => {
      const payload = await r.json().catch(() => null)
      if (!r.ok) throw new ApiError(messageFrom(payload, 'Incorrect email or password'), r.status)
      return payload
    })
  },

  concepts: () => request('/api/concepts'),
  businesses: () => request('/api/businesses'),
  createBusiness: (payload) => request('/api/businesses', { method: 'POST', body: payload }),
  datasets: (id) => request(`/api/businesses/${id}/datasets`),

  upload: (id, file, fields) => {
    const form = new FormData()
    form.append('file', file)
    Object.entries(fields ?? {}).forEach(([key, value]) => {
      if (value) form.append(key, value)
    })
    return request(`/api/businesses/${id}/uploads`, { method: 'POST', form })
  },

  confirmMappings: (versionId, updates) =>
    request(`/api/versions/${versionId}/mappings`, { method: 'PATCH', body: { updates } }),

  overview: (id, params) => request(`/api/businesses/${id}/overview`, { params }),
  compareBranches: (id, params) => request(`/api/businesses/${id}/compare/branches`, { params }),
  comparePeriods: (id, params) => request(`/api/businesses/${id}/compare/periods`, { params }),
  problems: (id, params) => request(`/api/businesses/${id}/problems`, { params }),
}

export { ApiError }
