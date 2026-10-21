import axios from 'axios'
import router from '../router'
import { useUserAuthStore } from '../stores/userAuth'
import { resolveApiErrorMessage } from './errorMessage'

export const userHttp = axios.create({
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

userHttp.interceptors.request.use((config) => {
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

const isUserPublicRoute = (path) => path === '/u/login' || path === '/u/register'
const resolveUserRedirect = (value) => {
  if (typeof value !== 'string') return '/u'
  return value === '/u' || value.startsWith('/u/') ? value : '/u'
}

userHttp.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      const auth = useUserAuthStore()
      auth.logout()
      const currentPath = router.currentRoute.value.path
      const currentFullPath = resolveUserRedirect(router.currentRoute.value.fullPath)
      if (!isUserPublicRoute(currentPath)) {
        router.replace({ path: '/u/login', query: { redirect: currentFullPath } })
      }
    }
    const message = resolveApiErrorMessage(error)
    return Promise.reject({ ...error, friendlyMessage: message })
  }
)
