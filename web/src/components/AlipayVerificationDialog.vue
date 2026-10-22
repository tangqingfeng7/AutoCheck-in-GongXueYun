<script setup>
import { computed } from 'vue'

const visible = defineModel({ type: Boolean, default: false })
const props = defineProps({
  registerUrl: { type: String, default: '' },
  verificationType: { type: String, default: 'account' },
  continuing: { type: Boolean, default: false },
})
const emit = defineEmits(['continue'])
const isFaceVerification = computed(() => props.verificationType === 'face')

const safeRegisterUrl = computed(() => {
  const value = String(props.registerUrl || '').trim()
  return value.startsWith('alipays://') ? value : ''
})

const openAlipay = () => {
  if (!safeRegisterUrl.value || props.continuing) return
  window.location.assign(safeRegisterUrl.value)
}

const beforeClose = (done) => {
  if (!props.continuing) done()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="isFaceVerification ? '支付宝人脸识别' : '支付宝安全验证'"
    width="min(92vw, 480px)"
    :before-close="beforeClose"
    :close-on-click-modal="!continuing"
    :close-on-press-escape="!continuing"
    :show-close="!continuing"
    append-to-body
  >
    <div class="verification-content">
      <div class="verification-status">
        {{ isFaceVerification ? '人脸识别待完成' : '安全验证待完成' }}
      </div>
      <div class="verification-message">
        {{ isFaceVerification
          ? '请在支付宝完成人脸识别，返回后确认服务器考勤记录。'
          : '请在支付宝完成本人验证，后台将自动检测并续提一次，无需手动操作。' }}
      </div>
      <p v-if="!isFaceVerification">后台每 3 秒检测授权状态；仅支持已保存原请求且能识别官方验证响应的事务。续提后以服务端考勤记录确认成功，超时不重复发送。</p>
      <el-alert
        v-if="!safeRegisterUrl"
        title="验证链接不可用，请关闭后重新发起打卡"
        type="error"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <div class="verification-actions">
        <el-button :disabled="!safeRegisterUrl || continuing" @click="openAlipay">
          {{ isFaceVerification ? '前往支付宝人脸识别' : '前往支付宝验证' }}
        </el-button>
        <el-button type="primary" :loading="continuing" @click="emit('continue')">
          {{ isFaceVerification ? '识别完成，检查考勤' : '验证完成，检查考勤' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.verification-content {
  display: grid;
  gap: 12px;
}

.verification-status {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.verification-message {
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.verification-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.verification-actions :deep(.el-button) {
  margin-left: 0;
}

@media (max-width: 520px) {
  .verification-actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .verification-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
