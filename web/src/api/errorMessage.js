const BACKEND_UNAVAILABLE_MESSAGE =
  '后端服务不可用，请确认 8147 服务已启动，并检查 VITE_API_PROXY_TARGET 是否指向正确地址'

const normalizeResponseMessage = (data) => {
  if (!data) return ''
  if (typeof data === 'string') return data.trim()
  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => {
        if (typeof item === 'string') return item.trim()
        if (item && typeof item === 'object' && typeof item.msg === 'string') return item.msg.trim()
        return ''
      })
      .filter(Boolean)
      .join('；')
  }
  if (typeof data?.detail === 'string') return data.detail.trim()
  if (typeof data?.message === 'string') return data.message.trim()
  return ''
}

export const resolveApiErrorMessage = (error) => {
  const response = error?.response
  const dataMessage = normalizeResponseMessage(response?.data)
  if (dataMessage) return dataMessage

  if (!response || error?.code === 'ERR_NETWORK') {
    return BACKEND_UNAVAILABLE_MESSAGE
  }

  if (Number(response.status || 0) >= 500) {
    return BACKEND_UNAVAILABLE_MESSAGE
  }

  return error?.message || '请求失败'
}

