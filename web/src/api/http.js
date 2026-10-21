import axios from 'axios'
import router from '../router'
import { useAuthStore } from '../stores/auth'
import { resolveApiErrorMessage } from './errorMessage'

export const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
  withCredentials: true,
})

const unsafeMethods = new Set(['post', 'put', 'patch', 'delete'])

const readCookie = (name) => {
  if (typeof document === 'undefined') return ''
  const prefix = `${name}=`
  const item = document.cookie.split('; ').find((part) => part.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : ''
}

http.interceptors.request.use((config) => {
  const method = String(config.method || 'get').toLowerCase()
  if (unsafeMethods.has(method)) {
    const csrfToken = readCookie('csrf_token')
    if (csrfToken) {
      config.headers = {
        ...(config.headers || {}),
        'X-CSRF-Token': csrfToken,
      }
    }
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      if (router.currentRoute.value.path !== '/login') {
        router.replace('/login')
      }
    }
    const message = resolveApiErrorMessage(error)
    return Promise.reject({ ...error, friendlyMessage: message })
  }
)
