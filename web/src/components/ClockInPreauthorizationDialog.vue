<script setup>
import { computed, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'

const visible = defineModel({ type: Boolean, default: false })

const props = defineProps({
  directUrl: { type: String, default: '' },
  browserUrl: { type: String, default: '' },
  startedAt: { type: String, default: '' },
  expiresAt: { type: String, default: '' },
  targetDate: { type: String, default: '' },
  targetType: { type: String, default: '' },
  completing: { type: Boolean, default: false },
})

const emit = defineEmits(['complete', 'closed'])

const safeDirectUrl = computed(() => {
  const value = String(props.directUrl || '').trim()
  return value.startsWith('alipays://') ? value : ''
})

const safeBrowserUrl = computed(() => {
  const value = String(props.browserUrl || '').trim()
  return value.startsWith('https://ds.alipay.com/') ? value : ''
})

const qrDataUrl = shallowRef('')
const qrError = shallowRef(false)
let qrGeneration = 0

watch(safeBrowserUrl, async (value) => {
  const generation = ++qrGeneration
  qrDataUrl.value = ''
  qrError.value = false
  if (!value) return
  try {
    const dataUrl = await QRCode.toDataURL(value, {
      width: 260,
      margin: 1,
      errorCorrectionLevel: 'M',
    })
    if (generation === qrGeneration) qrDataUrl.value = dataUrl
  } catch {
    if (generation === qrGeneration) qrError.value = true
  }
}, { immediate: true })

const targetLabel = computed(() => {
  if (props.targetType === 'START') return '上班'
  if (props.targetType === 'END') return '下班'
  return '补卡'
})

const formatDateTime = (value) => {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(parsed)
}

const startedAtLabel = computed(() => formatDateTime(props.startedAt))
const expiresAtLabel = computed(() => formatDateTime(props.expiresAt))

const openBrowser = () => {
  if (!safeBrowserUrl.value || props.completing) return
  window.open(safeBrowserUrl.value, '_blank', 'noopener,noreferrer')
}

const openAlipay = () => {
  if (!safeDirectUrl.value || props.completing) return
  window.location.assign(safeDirectUrl.value)
}

const copyAuthorizationLink = async () => {
  const value = safeBrowserUrl.value || safeDirectUrl.value
  if (!value || props.completing) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      textarea.remove()
      if (!copied) throw new Error('copy failed')
    }
    ElMessage.success('授权链接已复制')
  } catch {
    ElMessage.error('复制失败，请使用浏览器打开')
  }
}

const beforeClose = (done) => {
  if (!props.completing) done()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="完成支付宝预授权"
    width="min(92vw, 520px)"
    :before-close="beforeClose"
    :close-on-click-modal="!completing"
    :close-on-press-escape="!completing"
    :show-close="!completing"
    append-to-body
    @closed="emit('closed')"
  >
    <div class="authorization-content">
      <div class="target-summary">
        <span class="target-date">{{ targetDate }}</span>
        <el-tag size="small" type="info">{{ targetLabel }}</el-tag>
      </div>
      <p class="authorization-message">
        选择一种方式打开支付宝并完成当次授权，返回本页后再确认完成。
      </p>
      <div v-if="qrDataUrl" class="qr-panel">
        <img :src="qrDataUrl" alt="支付宝预授权二维码" class="authorization-qr" />
        <strong>使用手机支付宝扫描此二维码</strong>
        <small>本二维码覆盖上方显示的全部打卡目标</small>
      </div>
      <div class="authorization-meta">
        <div class="meta-row">
          <span>发起时间</span>
          <strong>{{ startedAtLabel }}</strong>
        </div>
        <div class="meta-row">
          <span>有效期至</span>
          <strong>{{ expiresAtLabel }}</strong>
        </div>
      </div>
      <el-alert
        v-if="qrError"
        title="二维码生成失败，请使用下方按钮打开授权页面"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="!safeDirectUrl && !safeBrowserUrl"
        title="授权链接不可用，请关闭后重新发起"
        type="error"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <div class="authorization-actions">
        <el-button
          :disabled="!safeBrowserUrl || completing"
          @click="openBrowser"
        >
          浏览器打开
        </el-button>
        <el-button
          :disabled="(!safeBrowserUrl && !safeDirectUrl) || completing"
          @click="copyAuthorizationLink"
        >
          复制链接
        </el-button>
        <el-button
          :disabled="!safeDirectUrl || completing"
          @click="openAlipay"
        >
          支付宝打开
        </el-button>
        <el-button
          type="primary"
          :loading="completing"
          :disabled="(!safeDirectUrl && !safeBrowserUrl) || completing"
          @click="emit('complete')"
        >
          我已完成授权
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.authorization-content {
  display: grid;
  gap: 14px;
}

.target-summary {
  display: flex;
  align-items: center;
  gap: 10px;
}

.target-date {
  font-size: 18px;
  font-weight: 750;
  color: var(--el-text-color-primary);
}

.authorization-message {
  margin: 0;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.qr-panel {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  color: #303133;
  text-align: center;
}

.authorization-qr {
  width: min(260px, 72vw);
  height: auto;
  aspect-ratio: 1;
  image-rendering: pixelated;
}

.qr-panel small {
  color: #606266;
}

.authorization-meta {
  display: grid;
  gap: 8px;
  padding: 10px 0;
  border-top: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.meta-row strong {
  color: var(--el-text-color-primary);
  text-align: right;
}

.authorization-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.authorization-actions :deep(.el-button) {
  margin-left: 0;
}

@media (max-width: 520px) {
  .authorization-actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .authorization-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
