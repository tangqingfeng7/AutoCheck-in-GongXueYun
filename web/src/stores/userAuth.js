import { defineStore } from 'pinia'

const META_KEY = 'user_auth_meta'
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

export const useUserAuthStore = defineStore('userAuth', {
  state: () => {
    const meta = readMeta()
    return {
      authed: meta.authed === true,
      phone: meta.phone || '',
      userId: meta.userId || '',
      sessionChecked: false,
    }
  },
  getters: {
    isAuthed: (s) => !!s.authed,
  },
  actions: {
    setAuth(_token, phone, userId) {
      this.authed = !!(_token || phone || userId)
      this.phone = phone || ''
      this.userId = userId || ''
      this.sessionChecked = false
      if (this.authed) {
        sessionStorage.setItem(META_KEY, JSON.stringify({
          authed: true,
          phone: this.phone,
          userId: this.userId,
        }))
      } else {
        sessionStorage.removeItem(META_KEY)
      }
    },
    logout() {
      this.authed = false
      this.phone = ''
      this.userId = ''
      this.sessionChecked = false
      sessionStorage.removeItem(META_KEY)
    },
    async validateSession() {
      try {
        const response = await fetchWithTimeout('/api/app/me', { credentials: 'include' })
        if (!response.ok) throw new Error('session invalid')
        const data = await response.json()
        this.authed = true
        this.phone = data.app_phone || ''
        this.userId = data.task_user?.id || this.userId || ''
        this.sessionChecked = true
        sessionStorage.setItem(META_KEY, JSON.stringify({
          authed: true,
          phone: this.phone,
          userId: this.userId,
        }))
        return true
      } catch {
        this.authed = false
        this.phone = ''
        this.userId = ''
        this.sessionChecked = true
        sessionStorage.removeItem(META_KEY)
        return false
      }
    },
  },
})
