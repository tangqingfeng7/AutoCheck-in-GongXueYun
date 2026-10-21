import { defineStore } from 'pinia'

const META_KEY = 'auth_meta'
const SESSION_VALIDATE_TIMEOUT_MS = 5000

const fetchWithTimeout = async (url, options = {}) => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), SESSION_VALIDATE_TIMEOUT_MS)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timeoutId)
  }
}

const readMeta = () => {
  try {
    return JSON.parse(sessionStorage.getItem(META_KEY) || '{}')
  } catch {
    return {}
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const meta = readMeta()
    return {
      authed: meta.authed === true,
      username: meta.username || '',
      role: meta.role || '',
      permissions: Array.isArray(meta.permissions) ? meta.permissions : [],
      sessionChecked: false,
    }
  },
  getters: {
    isAuthed: (s) => !!s.authed,
    isAdmin: (s) => s.role === 'admin',
    canWrite: (s) => s.role === 'admin' || s.role === 'operator',
    can: (s) => (permission) => Array.isArray(s.permissions) && s.permissions.includes(permission),
  },
  actions: {
    setAuth(_token, username, role, permissions = []) {
      this.authed = !!(_token || role)
      this.username = username || ''
      this.role = role || ''
      this.permissions = Array.isArray(permissions) ? permissions : []
      this.sessionChecked = false
      if (this.authed) {
        sessionStorage.setItem(META_KEY, JSON.stringify({
          authed: true,
          username: this.username,
          role: this.role,
          permissions: this.permissions,
        }))
      } else {
        sessionStorage.removeItem(META_KEY)
      }
    },
    logout() {
      this.authed = false
      this.username = ''
      this.role = ''
      this.permissions = []
      this.sessionChecked = false
      sessionStorage.removeItem(META_KEY)
    },
    async validateSession() {
      try {
        const response = await fetchWithTimeout('/api/auth/me', { credentials: 'include' })
        if (!response.ok) throw new Error('session invalid')
        const data = await response.json()
        this.authed = true
        this.username = data.username || ''
        this.role = data.role || ''
        this.permissions = Array.isArray(data.permissions) ? data.permissions : []
        this.sessionChecked = true
        sessionStorage.setItem(META_KEY, JSON.stringify({
          authed: true,
          username: this.username,
          role: this.role,
          permissions: this.permissions,
        }))
        return true
      } catch {
        this.authed = false
        this.username = ''
        this.role = ''
        this.permissions = []
        this.sessionChecked = true
        sessionStorage.removeItem(META_KEY)
        return false
      }
    },
  },
})
