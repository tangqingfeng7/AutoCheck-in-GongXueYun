import { ElMessage } from 'element-plus'

export const notify = (options) => {
  const type = options?.type || 'info'
  const message = String(options?.message ?? '')
  const duration = options?.duration
  if (!message) return
  ElMessage({
    type,
    message,
    duration: typeof duration === 'number' ? duration : undefined,
    showClose: false,
  })
}

export const notifySuccess = (message, options) =>
  notify({ type: 'success', message, duration: 2200, ...(options || {}) })

export const notifyInfo = (message, options) =>
  notify({ type: 'info', message, duration: 5000, ...(options || {}) })

export const notifyWarning = (message, options) =>
  notify({ type: 'warning', message, duration: 3200, ...(options || {}) })

export const notifyError = (message, options) =>
  notify({ type: 'error', message, duration: 4800, ...(options || {}) })

export const resolveErrorMessage = (e, fallback) => {
  if (!e) return fallback || '操作失败'
  return e.friendlyMessage || e.response?.data?.detail || e.message || fallback || '操作失败'
}
