<template>
  <el-card class="page-card">
    <template #header>
      <div class="page-header">
        <div class="page-title">系统设置</div>
        <div class="page-actions">
          <el-button @click="goBack">返回</el-button>
        </div>
      </div>
    </template>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="邮件通知" name="notifications">
        <el-form :model="smtpForm" label-width="120px" v-loading="notificationLoading">
          <el-alert
            title="QQ 邮箱 SMTP 由管理员统一配置。授权码留空会保留并使用服务器已保存的值；测试邮件发往当前填写的 QQ 邮箱。"
            type="info"
            :closable="false"
            style="margin-bottom: 16px;"
          />

          <el-form-item label="启用 SMTP">
            <el-switch v-model="smtpForm.enabled" />
          </el-form-item>
          <el-form-item label="QQ 邮箱">
            <el-input v-model="smtpForm.username" placeholder="例如：demo@qq.com" />
          </el-form-item>
          <el-form-item label="授权码">
            <el-input v-model="smtpForm.password" type="password" show-password autocomplete="new-password" :placeholder="smtpForm.hasPassword ? '已配置，留空保留原授权码' : '请输入 QQ 邮箱授权码'" />
          </el-form-item>
          <el-form-item label="发件人名称">
            <el-input v-model="smtpForm.from" placeholder="例如：工学云签到通知" />
          </el-form-item>

          <el-form-item>
            <div class="settings-actions">
              <el-button type="primary" :loading="notificationSaving" @click="saveNotifications">保存</el-button>
              <el-button :loading="smtpTesting" @click="testSmtp">测试发送</el-button>
            </div>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="AI 大模型" name="ai">
        <el-form :model="aiForm" label-width="140px" v-loading="aiLoading">
          <el-form-item label="Model">
            <el-input v-model="aiForm.model" placeholder="gpt-4o-mini" />
          </el-form-item>
          <el-form-item label="API URL">
            <el-input v-model="aiForm.apiUrl" placeholder="https://api.openai.com/ 或 https://api-inference.modelscope.cn/v1" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="aiForm.apikey"
              type="password"
              show-password
              clearable
              :placeholder="aiForm.hasApiKey ? '已保存，留空则沿用旧 Key' : '请输入 API Key'"
            />
          </el-form-item>

          <el-form-item>
            <div class="settings-actions">
              <el-button type="primary" :loading="aiSaving" @click="saveAiSettings">保存</el-button>
              <el-button :loading="aiTesting" @click="testAiSettings">测试 AI</el-button>
              <el-button @click="applyModelScopePreset">魔搭预设</el-button>
              <el-tag v-if="aiTestStatus" size="small" :type="aiTestStatus === 'ok' ? 'success' : 'danger'">
                {{ aiTestStatus === 'ok' ? '可用' : '不可用' }}
              </el-tag>
              <span v-if="aiTestLatencyMs !== null" class="ai-test-meta">延迟：{{ aiTestLatencyMs }}ms</span>
            </div>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="网络代理" name="proxy">
        <el-form :model="proxyForm" label-width="140px" v-loading="proxyLoading">
          <el-alert
            title="代理仅用于手动补卡请求；正常定时打卡、报告提交、缺卡查询和登录不会使用代理。"
            type="info"
            :closable="false"
            style="margin-bottom: 16px;"
          />

          <el-form-item label="启用代理">
            <el-switch v-model="proxyForm.enabled" />
          </el-form-item>
          <el-form-item label="动态代理接口">
            <el-input
              v-model="proxyForm.apiUrl"
              type="textarea"
              :rows="4"
              resize="vertical"
              placeholder="http://capi.51daili.com/traffic/getip?...&accessName=...&accessPassword=..."
            />
          </el-form-item>
          <el-form-item label="缓存秒数">
            <el-input-number v-model="proxyForm.ttlSeconds" :min="0" :max="600" :step="1" />
          </el-form-item>
          <el-form-item label="接口超时秒数">
            <el-input-number v-model="proxyForm.apiTimeoutSeconds" :min="0" :max="30" :step="1" />
          </el-form-item>
          <el-form-item label="静态代理列表">
            <el-input
              v-model="proxyForm.proxyUrls"
              type="textarea"
              :rows="4"
              resize="vertical"
              placeholder="http://user:pass@1.2.3.4:8080"
            />
          </el-form-item>

          <el-form-item>
            <div class="settings-actions">
              <el-button type="primary" :loading="proxySaving" @click="saveProxy">保存</el-button>
            </div>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '../api/http'
import { notifyError, notifyInfo, notifySuccess, notifyWarning, resolveErrorMessage } from '../utils/notify'

const router = useRouter()
const activeTab = ref('notifications')
const notificationLoading = ref(false)
const notificationSaving = ref(false)
const smtpTesting = ref(false)
const aiLoading = ref(false)
const aiSaving = ref(false)
const aiTesting = ref(false)
const aiTestStatus = ref('')
const aiTestLatencyMs = ref(null)
const proxyLoading = ref(false)
const proxySaving = ref(false)

const smtpForm = reactive({
  enabled: true,
  username: '',
  password: '',
  hasPassword: false,
  from: '工学云签到通知',
})

const proxyForm = reactive({
  enabled: false,
  apiUrl: '',
  ttlSeconds: 55,
  apiTimeoutSeconds: 10,
  proxyUrls: '',
})

const aiForm = reactive({
  apiUrl: 'https://api.openai.com/',
  apikey: '',
  model: 'gpt-4o-mini',
  hasApiKey: false,
})

const loadNotificationSettings = async () => {
  notificationLoading.value = true
  try {
    const res = await http.get('/settings/notifications')
    const smtp = res.data?.smtp || {}
    smtpForm.enabled = !!smtp.enabled
    smtpForm.username = String(smtp.username || '')
    smtpForm.password = ''
    smtpForm.hasPassword = !!smtp.hasPassword
    smtpForm.from = String(smtp.from || '工学云签到通知')
  } catch (error) {
    notifyError(`加载通知设置失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    notificationLoading.value = false
  }
}

const loadProxySettings = async () => {
  proxyLoading.value = true
  try {
    const res = await http.get('/settings/proxy')
    const proxy = res.data?.proxy || {}
    proxyForm.enabled = !!proxy.enabled
    proxyForm.apiUrl = String(proxy.apiUrl || '')
    proxyForm.ttlSeconds = Number(proxy.ttlSeconds ?? 55)
    proxyForm.apiTimeoutSeconds = Number(proxy.apiTimeoutSeconds ?? 10)
    proxyForm.proxyUrls = String(proxy.proxyUrls || '')
  } catch (error) {
    notifyError(`加载代理设置失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    proxyLoading.value = false
  }
}

const loadAiSettings = async () => {
  aiLoading.value = true
  try {
    const res = await http.get('/settings/ai')
    const ai = res.data?.ai || {}
    aiForm.apiUrl = String(ai.apiUrl || 'https://api.openai.com/')
    aiForm.apikey = ''
    aiForm.model = String(ai.model || 'gpt-4o-mini')
    aiForm.hasApiKey = !!ai.hasApiKey
    aiTestStatus.value = ''
    aiTestLatencyMs.value = null
  } catch (error) {
    notifyError(`加载 AI 设置失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    aiLoading.value = false
  }
}

const buildNotificationPayload = () => ({
  smtp: {
    enabled: !!smtpForm.enabled,
    username: String(smtpForm.username || '').trim(),
    password: String(smtpForm.password || '').trim(),
    from: String(smtpForm.from || '').trim(),
  },
})

const buildProxyPayload = () => ({
  proxy: {
    enabled: !!proxyForm.enabled,
    apiUrl: String(proxyForm.apiUrl || '').trim(),
    ttlSeconds: Number(proxyForm.ttlSeconds || 0),
    apiTimeoutSeconds: Number(proxyForm.apiTimeoutSeconds || 0),
    proxyUrls: String(proxyForm.proxyUrls || '').trim(),
  },
})

const buildAiPayload = () => ({
  ai: {
    apiUrl: String(aiForm.apiUrl || '').trim(),
    apikey: String(aiForm.apikey || '').trim(),
    model: String(aiForm.model || '').trim(),
  },
})

const validateForTest = () => {
  if (!String(smtpForm.username || '').trim()) {
    notifyWarning('请先填写 QQ 邮箱')
    return false
  }
  if (!smtpForm.hasPassword && !String(smtpForm.password || '').trim()) {
    notifyWarning('测试发送前请先填写授权码')
    return false
  }
  if (!String(smtpForm.from || '').trim()) {
    notifyWarning('请先填写发件人名称')
    return false
  }
  return true
}

const validateProxy = () => {
  if (!proxyForm.enabled) return true
  if (String(proxyForm.apiUrl || '').trim() || String(proxyForm.proxyUrls || '').trim()) return true
  notifyWarning('启用代理时请填写动态代理接口或静态代理列表')
  return false
}

const validateAiSettings = () => {
  if (!String(aiForm.apiUrl || '').trim()) {
    notifyWarning('请先填写 AI API URL')
    return false
  }
  if (!String(aiForm.model || '').trim()) {
    notifyWarning('请先填写 AI Model')
    return false
  }
  if (!aiForm.hasApiKey && !String(aiForm.apikey || '').trim()) {
    notifyWarning('请先填写 AI API Key')
    return false
  }
  return true
}

const flushUiMessage = async () => {
  await nextTick()
  await new Promise((resolve) => requestAnimationFrame(() => resolve()))
}

const goBack = () => {
  notifyInfo('正在返回上一页')
  router.back()
}

const saveNotifications = async () => {
  notificationSaving.value = true
  try {
    notifyInfo('正在保存通知设置')
    await flushUiMessage()
    await http.patch('/settings/notifications', buildNotificationPayload())
    notifySuccess('保存成功')
    await loadNotificationSettings()
  } catch (error) {
    notifyError(`保存失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    notificationSaving.value = false
  }
}

const saveProxy = async () => {
  if (!validateProxy()) return
  proxySaving.value = true
  try {
    notifyInfo('正在保存代理设置')
    await flushUiMessage()
    await http.patch('/settings/proxy', buildProxyPayload())
    notifySuccess('保存成功')
    await loadProxySettings()
  } catch (error) {
    notifyError(`保存失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    proxySaving.value = false
  }
}

const saveAiSettings = async () => {
  if (!validateAiSettings()) return
  aiSaving.value = true
  try {
    notifyInfo('正在保存 AI 设置')
    await flushUiMessage()
    await http.patch('/settings/ai', buildAiPayload())
    notifySuccess('保存成功')
    await loadAiSettings()
  } catch (error) {
    notifyError(`保存失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    aiSaving.value = false
  }
}

const testAiSettings = async () => {
  if (!validateAiSettings()) return
  aiTesting.value = true
  aiTestStatus.value = ''
  aiTestLatencyMs.value = null
  try {
    notifyInfo('正在测试 AI')
    await flushUiMessage()
    const res = await http.post('/settings/ai/test', buildAiPayload())
    aiTestStatus.value = res.data?.ok ? 'ok' : 'fail'
    aiTestLatencyMs.value = typeof res.data?.latency_ms === 'number' ? res.data.latency_ms : null
    notifySuccess('AI 可用')
  } catch (error) {
    aiTestStatus.value = 'fail'
    notifyError(resolveErrorMessage(error, 'AI 测试失败'))
  } finally {
    aiTesting.value = false
  }
}

const applyModelScopePreset = () => {
  aiForm.apiUrl = 'https://api-inference.modelscope.cn/v1'
  aiForm.model = 'Qwen/Qwen3-Next-80B-A3B-Instruct'
  aiTestStatus.value = ''
  aiTestLatencyMs.value = null
  notifySuccess('已填入魔搭预设')
}

const testSmtp = async () => {
  if (!validateForTest()) return
  smtpTesting.value = true
  try {
    notifyInfo('正在发送测试邮件')
    await flushUiMessage()
    const res = await http.post('/settings/notifications/smtp/test', buildNotificationPayload())
    notifySuccess(`测试发送成功：已发送到 ${res.data?.to || smtpForm.username}`)
  } catch (error) {
    notifyError(`测试发送失败：${resolveErrorMessage(error, '请求失败')}`)
  } finally {
    smtpTesting.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadNotificationSettings(), loadAiSettings(), loadProxySettings()])
})
</script>

<style scoped>
.settings-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.ai-test-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.page-header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.page-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.2px;
  color: var(--el-text-color-primary);
}
.page-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
:deep(.el-form) {
  max-width: 680px;
  padding-top: 8px;
}

</style>
