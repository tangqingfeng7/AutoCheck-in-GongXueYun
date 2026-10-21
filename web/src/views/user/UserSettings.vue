<template>
  <div class="page">
    <el-card class="page-card" shadow="never">
      <template #header>
        <div class="page-header">
          <div class="page-title">我的配置</div>
          <div class="page-actions">
            <el-button :loading="loading" @click="load">刷新</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
            <el-button @click="back">返回</el-button>
          </div>
        </div>
      </template>

      <el-form label-width="92px" v-loading="loading">
        <el-divider>账号</el-divider>
        <el-form-item label="工学云账号">
          <template v-if="bound">
            <div class="bind-row">
              <el-input :model-value="me.phone" readonly />
              <el-button class="bind-action" @click="startRebind">更换绑定</el-button>
            </div>
          </template>
          <template v-else>
            <div class="bind-form">
              <el-input v-model="bindPhone" placeholder="请输入工学云账号/手机号" autocomplete="username" />
              <el-input
                v-model="bindPassword"
                type="password"
                show-password
                placeholder="请输入工学云密码"
                autocomplete="current-password"
              />
              <el-button type="primary" :loading="binding" @click="bind">绑定</el-button>
            </div>
            <div class="bind-hint">平台登录账号仅用于进入用户端，绑定工学云账号后才能执行打卡/报告。</div>
          </template>
        </el-form-item>
        <el-form-item v-if="bound" label="工学云密码">
          <el-input v-model="password" type="password" show-password placeholder="留空表示不修改（用于打卡/报告登录）" />
        </el-form-item>

        <el-divider>打卡</el-divider>
        <el-form-item label="启用打卡">
          <el-switch v-model="clockInEnabled" />
        </el-form-item>
        <el-form-item label="打卡地址">
          <div class="address-row">
            <el-input v-model="clockInAddress" placeholder="请输入详细地址或搜索关键词" @keyup.enter="searchPlace" />
            <el-button type="primary" :loading="geocodeSearchLoading" @click="searchPlace">搜索位置</el-button>
            <el-button @click="autoFillAddress" :loading="addressLoading" type="success" plain>自动获取</el-button>
          </div>
        </el-form-item>
        <el-row class="location-grid" :gutter="10">
          <el-col :xs="24" :sm="12">
            <el-form-item label="纬度">
              <el-input v-model="clockInLatitude" placeholder="例如：30.572800" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="经度">
              <el-input v-model="clockInLongitude" placeholder="例如：104.066800" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row class="location-grid" :gutter="10">
          <el-col :xs="24" :sm="8">
            <el-form-item label="省份">
              <el-input v-model="clockInProvince" placeholder="省份" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="城市">
              <el-input v-model="clockInCity" placeholder="城市" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="区域">
              <el-input v-model="clockInArea" placeholder="区县" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="上班时间">
          <el-time-picker v-model="startTime" value-format="HH:mm" format="HH:mm" />
        </el-form-item>
        <el-form-item label="下班时间">
          <el-time-picker v-model="endTime" value-format="HH:mm" format="HH:mm" />
        </el-form-item>
        <el-form-item v-if="bound" label="补卡日期">
          <div class="clockin-backfill">
            <div class="clockin-backfill-row">
              <el-select v-model="clockInMakeupType" class="clockin-type-select" placeholder="补卡类型" @change="syncClockInTargetFromOptions">
                <el-option label="上班" value="START" />
                <el-option label="下班" value="END" />
              </el-select>
              <el-select v-model="clockInTargetDates" :loading="clockInPeriodLoading" multiple collapse-tags collapse-tags-tooltip filterable placeholder="选择待补日期">
                <el-option v-for="item in filteredClockInPeriodOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button :loading="clockInPeriodLoading" @click="loadClockInMissingDays">刷新缺卡</el-button>
              <el-button type="warning" :loading="clockInMakeupLoading" :disabled="!clockInTargetDates.length" @click="makeupClockIn">补选中</el-button>
              <el-button type="danger" :loading="clockInMakeupAllLoading" :disabled="!filteredClockInPeriodOptions.length" @click="makeupAllClockIn">全部待补</el-button>
            </div>
            <el-progress
              v-if="clockInMakeupAllLoading || clockInMakeupAllPercent > 0"
              class="clockin-backfill-progress"
              :percentage="clockInMakeupAllPercent"
              :status="clockInMakeupAllPercent >= 100 ? 'success' : undefined"
            />
            <div class="clockin-backfill-hint">
              已获取 {{ clockInRecordCount }} 条打卡记录，{{ clockInMakeupTypeLabel }}待补 {{ filteredClockInPeriodOptions.length }} 天，已选 {{ clockInTargetDates.length }} 天
            </div>
          </div>
        </el-form-item>

        <el-divider>报告</el-divider>
        <el-form-item label="启用日报">
          <el-switch v-model="dailyEnabled" />
        </el-form-item>
        <el-form-item v-if="dailyEnabled" label="日报提交时间">
          <el-time-select v-model="dailySubmitTime" start="00:00" step="00:01" end="23:59" />
        </el-form-item>
        <el-form-item label="补交日期">
          <div class="report-backfill">
            <div class="report-backfill-row">
              <el-select v-model="reportTargets.daily" :loading="reportPeriodLoading.daily" filterable placeholder="选择未提交日报日期">
                <el-option v-for="item in reportPeriodOptions.daily" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button :loading="reportPeriodLoading.daily" :disabled="!bound || !isReportEnabled('daily') || !!reportMakeupAllLoading" @click="loadReportPeriodOptions('daily')">刷新待补</el-button>
              <el-button type="danger" :loading="reportMakeupAllLoading === 'daily'" :disabled="!bound || !isReportEnabled('daily') || !!reportRunLoading || !!reportActionLoading || (!!reportMakeupAllLoading && reportMakeupAllLoading !== 'daily') || !reportPendingCount('daily')" @click="makeupAllReports('daily')">补全部日报</el-button>
            </div>
            <el-progress
              v-if="reportMakeupAllInProgress('daily')"
              class="report-backfill-progress"
              :percentage="reportMakeupAllPercent"
              :status="reportMakeupAllPercent >= 100 ? 'success' : undefined"
            />
            <div class="report-backfill-hint">{{ isReportEnabled('daily') ? `日报待补 ${reportPendingCount('daily')} 个周期` : '日报未开启，不获取待补周期' }}</div>
          </div>
        </el-form-item>
        <el-form-item label="立即执行">
          <div class="report-now-row">
            <el-button :loading="reportActionLoading === 'daily_generate'" :disabled="!bound || !isReportEnabled('daily') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.daily" @click="generateReport('daily')">
              AI生成日报
            </el-button>
            <el-button type="primary" :loading="reportActionLoading === 'daily_submit'" :disabled="!bound || !isReportEnabled('daily') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.daily || !reportPreview.daily.trim()" @click="submitReport('daily')">
              提交日报
            </el-button>
            <el-button
              type="success"
              :disabled="!bound || !isReportEnabled('daily') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.daily"
              :loading="reportRunLoading === 'daily_report'"
              @click="runReportNow('daily_report')"
            >
              立即执行日报
            </el-button>
            <span class="report-now-hint">调用 AI 生成日报后立即提交。</span>
          </div>
          <el-input v-model="reportPreview.daily" class="report-preview-input" type="textarea" :rows="5" resize="none" placeholder="点击 AI生成日报，或手动填写后提交" />
        </el-form-item>
        <el-form-item label="启用周报">
          <el-switch v-model="weeklyEnabled" />
        </el-form-item>
        <el-form-item label="补交周">
          <div class="report-backfill">
            <div class="report-backfill-row">
              <el-select v-model="reportTargets.weekly" :loading="reportPeriodLoading.weekly" filterable placeholder="选择未提交周报周期">
                <el-option v-for="item in reportPeriodOptions.weekly" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button :loading="reportPeriodLoading.weekly" :disabled="!bound || !isReportEnabled('weekly') || !!reportMakeupAllLoading" @click="loadReportPeriodOptions('weekly')">刷新待补</el-button>
              <el-button type="danger" :loading="reportMakeupAllLoading === 'weekly'" :disabled="!bound || !isReportEnabled('weekly') || !!reportRunLoading || !!reportActionLoading || (!!reportMakeupAllLoading && reportMakeupAllLoading !== 'weekly') || !reportPendingCount('weekly')" @click="makeupAllReports('weekly')">补全部周报</el-button>
            </div>
            <el-progress
              v-if="reportMakeupAllInProgress('weekly')"
              class="report-backfill-progress"
              :percentage="reportMakeupAllPercent"
              :status="reportMakeupAllPercent >= 100 ? 'success' : undefined"
            />
            <div class="report-backfill-hint">{{ isReportEnabled('weekly') ? `周报待补 ${reportPendingCount('weekly')} 个周期` : '周报未开启，不获取待补周期' }}</div>
          </div>
        </el-form-item>
        <el-form-item label="立即执行">
          <div class="report-now-row">
            <el-button :loading="reportActionLoading === 'weekly_generate'" :disabled="!bound || !isReportEnabled('weekly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.weekly" @click="generateReport('weekly')">
              AI生成周报
            </el-button>
            <el-button type="primary" :loading="reportActionLoading === 'weekly_submit'" :disabled="!bound || !isReportEnabled('weekly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.weekly || !reportPreview.weekly.trim()" @click="submitReport('weekly')">
              提交周报
            </el-button>
            <el-button
              type="success"
              :disabled="!bound || !isReportEnabled('weekly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.weekly"
              :loading="reportRunLoading === 'weekly_report'"
              @click="runReportNow('weekly_report')"
            >
              立即执行周报
            </el-button>
            <span class="report-now-hint">绕过计划时间，立即生成并提交周报。</span>
          </div>
          <el-input v-model="reportPreview.weekly" class="report-preview-input" type="textarea" :rows="5" resize="none" placeholder="点击 AI生成周报，或手动填写后提交" />
        </el-form-item>
        <el-form-item label="启用月报">
          <el-switch v-model="monthlyEnabled" />
        </el-form-item>
        <el-form-item label="补交月份">
          <div class="report-backfill">
            <div class="report-backfill-row">
              <el-select v-model="reportTargets.monthly" :loading="reportPeriodLoading.monthly" filterable placeholder="选择未提交月报月份">
                <el-option v-for="item in reportPeriodOptions.monthly" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-button :loading="reportPeriodLoading.monthly" :disabled="!bound || !isReportEnabled('monthly') || !!reportMakeupAllLoading" @click="loadReportPeriodOptions('monthly')">刷新待补</el-button>
              <el-button type="danger" :loading="reportMakeupAllLoading === 'monthly'" :disabled="!bound || !isReportEnabled('monthly') || !!reportRunLoading || !!reportActionLoading || (!!reportMakeupAllLoading && reportMakeupAllLoading !== 'monthly') || !reportPendingCount('monthly')" @click="makeupAllReports('monthly')">补全部月报</el-button>
            </div>
            <el-progress
              v-if="reportMakeupAllInProgress('monthly')"
              class="report-backfill-progress"
              :percentage="reportMakeupAllPercent"
              :status="reportMakeupAllPercent >= 100 ? 'success' : undefined"
            />
            <div class="report-backfill-hint">{{ isReportEnabled('monthly') ? `月报待补 ${reportPendingCount('monthly')} 个周期` : '月报未开启，不获取待补周期' }}</div>
          </div>
        </el-form-item>
        <el-form-item label="立即执行">
          <div class="report-now-row">
            <el-button :loading="reportActionLoading === 'monthly_generate'" :disabled="!bound || !isReportEnabled('monthly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.monthly" @click="generateReport('monthly')">
              AI生成月报
            </el-button>
            <el-button type="primary" :loading="reportActionLoading === 'monthly_submit'" :disabled="!bound || !isReportEnabled('monthly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.monthly || !reportPreview.monthly.trim()" @click="submitReport('monthly')">
              提交月报
            </el-button>
            <el-button
              type="success"
              :disabled="!bound || !isReportEnabled('monthly') || !!reportRunLoading || !!reportMakeupAllLoading || !reportTargets.monthly"
              :loading="reportRunLoading === 'monthly_report'"
              @click="runReportNow('monthly_report')"
            >
              立即执行月报
            </el-button>
            <span class="report-now-hint">绕过计划时间，立即生成并提交月报。</span>
          </div>
          <el-input v-model="reportPreview.monthly" class="report-preview-input" type="textarea" :rows="5" resize="none" placeholder="点击 AI生成月报，或手动填写后提交" />
        </el-form-item>

        <el-divider>推送</el-divider>
        <el-divider content-position="left">Server酱</el-divider>
        <el-form-item label="启用 Server酱">
          <el-switch v-model="pushNotifications[0].enabled" />
        </el-form-item>
        <el-form-item label="SendKey">
          <el-input v-model="pushNotifications[0].sendKey" placeholder="请输入 Server酱 SendKey" clearable />
        </el-form-item>
        <el-divider content-position="left">QQ 邮箱 SMTP</el-divider>
        <el-form-item label="启用 SMTP">
          <el-switch v-model="pushNotifications[1].enabled" />
        </el-form-item>
        <el-form-item label="收件邮箱">
          <el-input v-model="pushNotifications[1].to" placeholder="例如：demo@qq.com" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { userHttp } from '../../api/userHttp'
import { notifySuccess, notifyError, notifyWarning, notifyInfo, resolveErrorMessage } from '../../utils/notify'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const me = ref({ phone: '' })
const bound = ref(false)

const bindPhone = ref('')
const bindPassword = ref('')
const binding = ref(false)

const password = ref('')
const clockInEnabled = ref(true)
const clockInAddress = ref('')
const addressLoading = ref(false)
const clockInLatitude = ref('')
const clockInLongitude = ref('')
const clockInProvince = ref('')
const clockInCity = ref('')
const clockInArea = ref('')
const geocodeSearchLoading = ref(false)
const startTime = ref('07:30')
const endTime = ref('18:00')
const clockInPeriodLoading = ref(false)
const clockInMakeupLoading = ref(false)
const clockInMakeupAllLoading = ref(false)
const clockInMakeupAllPercent = ref(0)
const clockInMakeupType = ref('START')
const clockInPeriodOptions = ref([])
const clockInTargetDates = ref([])
const clockInRecordCount = ref(0)
const dailyEnabled = ref(false)
const dailySubmitTime = ref('12:00')
const weeklyEnabled = ref(false)
const monthlyEnabled = ref(false)
const reportRunLoading = ref('')
const reportActionLoading = ref('')
const reportPeriodLoading = reactive({ daily: false, weekly: false, monthly: false })
const reportPeriodOptions = reactive({ daily: [], weekly: [], monthly: [] })
const reportMakeupAllLoading = ref('')
const reportMakeupAllPercent = ref(0)
const reportMakeupAllProgressKey = ref('')
const pushNotifications = reactive([
  { type: 'Server', enabled: false, sendKey: '' },
  { type: 'SMTP', enabled: false, to: '' },
])
const CLOCKIN_MAKEUP_REQUEST_TIMEOUT = 0
const REPORT_MAKEUP_REQUEST_TIMEOUT = 0
const _today = new Date()
const _pad2 = (n) => String(n).padStart(2, '0')
const _todayDate = `${_today.getFullYear()}-${_pad2(_today.getMonth() + 1)}-${_pad2(_today.getDate())}`
const _todayMonth = `${_today.getFullYear()}-${_pad2(_today.getMonth() + 1)}`
const reportTargets = reactive({ daily: _todayDate, weekly: _todayDate, monthly: _todayMonth })
const reportPreview = reactive({ daily: '', weekly: '', monthly: '' })
let clockInMakeupAllTimer = null
let reportMakeupAllTimer = null
let geocodeSearchAbort = null

const resetClockInMakeupAllProgress = () => {
  if (clockInMakeupAllTimer) {
    clearInterval(clockInMakeupAllTimer)
    clockInMakeupAllTimer = null
  }
  clockInMakeupAllPercent.value = 0
}

const startClockInMakeupAllProgress = (total) => {
  resetClockInMakeupAllProgress()
  const count = Math.max(Number(total || 0), 1)
  const estimatedMs = Math.max(count * 2200, 3000)
  const startedAt = Date.now()
  clockInMakeupAllPercent.value = 3
  clockInMakeupAllTimer = setInterval(() => {
    const elapsed = Date.now() - startedAt
    clockInMakeupAllPercent.value = Math.min(95, Math.max(3, Math.round((elapsed / estimatedMs) * 95)))
  }, 300)
}

const finishClockInMakeupAllProgress = () => {
  if (clockInMakeupAllTimer) {
    clearInterval(clockInMakeupAllTimer)
    clockInMakeupAllTimer = null
  }
  clockInMakeupAllPercent.value = 100
  window.setTimeout(() => {
    if (!clockInMakeupAllLoading.value) clockInMakeupAllPercent.value = 0
  }, 1200)
}

const resetReportMakeupAllProgress = () => {
  if (reportMakeupAllTimer) {
    clearInterval(reportMakeupAllTimer)
    reportMakeupAllTimer = null
  }
  reportMakeupAllPercent.value = 0
  reportMakeupAllProgressKey.value = ''
}

const startReportMakeupAllProgress = (key, total) => {
  resetReportMakeupAllProgress()
  const count = Math.max(Number(total || 0), 1)
  const estimatedMs = Math.max(count * 4500, 5000)
  const startedAt = Date.now()
  reportMakeupAllProgressKey.value = key
  reportMakeupAllPercent.value = 3
  reportMakeupAllTimer = setInterval(() => {
    const elapsed = Date.now() - startedAt
    reportMakeupAllPercent.value = Math.min(95, Math.max(3, Math.round((elapsed / estimatedMs) * 95)))
  }, 300)
}

const finishReportMakeupAllProgress = () => {
  if (reportMakeupAllTimer) {
    clearInterval(reportMakeupAllTimer)
    reportMakeupAllTimer = null
  }
  reportMakeupAllPercent.value = 100
  window.setTimeout(() => {
    if (!reportMakeupAllLoading.value) resetReportMakeupAllProgress()
  }, 1200)
}

const _ensureObj = (v) => (v && typeof v === 'object' ? v : {})
const _firstText = (...values) => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}
const _addressObjectFromSearchResult = (result) => {
  if (!result || typeof result !== 'object') return {}
  const raw = result.raw && typeof result.raw === 'object' ? result.raw : {}
  return _ensureObj(
    result.address ||
    raw.address ||
    raw.address_components ||
    raw.addressComponent ||
    raw.result?.address_components ||
    raw.regeocode?.addressComponent
  )
}
const assignAddressParts = (address) => {
  const addr = _ensureObj(address)
  const province = _firstText(addr.province, addr.state)
  const city = _firstText(addr.city, addr.town, addr.county)
  const area = _firstText(addr.district, addr.county, addr.suburb)
  if (province) clockInProvince.value = province
  if (city) clockInCity.value = city
  if (area) clockInArea.value = area
}
const applyGeocodeSearchResult = (result, fallbackLabel) => {
  const lat = Number(result?.y)
  const lon = Number(result?.x)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    notifyWarning('搜索结果经纬度无效，请换一个关键词')
    return false
  }
  clockInLatitude.value = lat.toFixed(6)
  clockInLongitude.value = lon.toFixed(6)
  const address = _addressObjectFromSearchResult(result)
  assignAddressParts(address)
  const label = _firstText(result?.label, result?.raw?.formatted_address, result?.raw?.display_name, fallbackLabel)
  if (label) clockInAddress.value = label
  return true
}
const normalizePushNotifications = (items) => {
  const list = Array.isArray(items) ? items : []
  const map = new Map(
    list
      .filter((item) => item && typeof item === 'object' && item.type)
      .map((item) => [item.type, { ...item }])
  )
  const server = map.get('Server') || {}
  const smtp = map.get('SMTP') || {}
  return [
    {
      type: 'Server',
      enabled: !!server.enabled,
      sendKey: typeof server.sendKey === 'string' ? server.sendKey : '',
    },
    {
      type: 'SMTP',
      enabled: !!smtp.enabled,
      to: typeof smtp.to === 'string' ? smtp.to : '',
    },
  ]
}
const assignPushNotifications = (items) => {
  const next = normalizePushNotifications(items)
  pushNotifications.splice(0, pushNotifications.length, ...next)
}

const startRebind = () => {
  bound.value = false
  bindPhone.value = ''
  bindPassword.value = ''
}

const bind = async () => {
  const phone = String(bindPhone.value || '').trim()
  const pw = String(bindPassword.value || '').trim()
  if (!phone || phone.length < 4) {
    notifyError('请填写正确的工学云账号')
    return
  }
  if (!pw || pw.length < 6) {
    notifyError('工学云密码至少 6 位')
    return
  }
  binding.value = true
  try {
    await userHttp.post('/app/bind', { task_phone: phone, task_password: pw })
    bindPassword.value = ''
    notifySuccess('绑定成功')
    await load()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '绑定失败'))
  } finally {
    binding.value = false
  }
}

const autoFillAddress = async () => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  addressLoading.value = true
  try {
    const res = await userHttp.get('/app/account-address')
    if (res.data?.address) {
      clockInAddress.value = res.data.address
      const latitude = Number.parseFloat(res.data?.latitude)
      const longitude = Number.parseFloat(res.data?.longitude)
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        clockInLatitude.value = latitude.toFixed(6)
        clockInLongitude.value = longitude.toFixed(6)
      } else {
        await searchPlace({ silent: true })
      }
      notifySuccess('已自动填充打卡地址')
    } else {
      notifyError('未获取到有效地址')
    }
  } catch (e) {
    notifyError(resolveErrorMessage(e, '获取地址失败'))
  } finally {
    addressLoading.value = false
  }
}

const searchPlace = async (options = {}) => {
  const q = String(clockInAddress.value || '').trim()
  if (!q) {
    notifyWarning('请输入要搜索的地点')
    return false
  }
  if (geocodeSearchAbort) geocodeSearchAbort.abort()
  geocodeSearchAbort = new AbortController()
  geocodeSearchLoading.value = true
  try {
    const res = await userHttp.get('/geocode/search', {
      params: { q },
      signal: geocodeSearchAbort.signal,
    })
    const results = Array.isArray(res.data?.results) ? res.data.results : []
    if (!results.length) {
      if (!options.silent) notifyWarning('没有搜索到结果，请换一个关键词')
      return false
    }
    const applied = applyGeocodeSearchResult(results[0], q)
    if (applied && !options.silent) notifySuccess('已定位到搜索结果')
    return applied
  } catch (e) {
    if (e?.code !== 'ERR_CANCELED' && !options.silent) {
      notifyError(resolveErrorMessage(e, '搜索位置失败'))
    }
    return false
  } finally {
    geocodeSearchLoading.value = false
  }
}

const load = async () => {
  loading.value = true
  try {
    const res = await userHttp.get('/app/me')
    bound.value = !!res.data?.bound
    me.value = bound.value ? (res.data?.task_user || {}) : { phone: '' }
    const ci = _ensureObj(me.value.clockIn)
    const loc = _ensureObj(ci.location)
    const schedule = _ensureObj(ci.schedule)
    clockInEnabled.value = me.value.enable_clockin !== false
    clockInAddress.value = String(loc.address || '')
    clockInLatitude.value = String(loc.latitude || '')
    clockInLongitude.value = String(loc.longitude || '')
    clockInProvince.value = String(loc.province || '')
    clockInCity.value = String(loc.city || '')
    clockInArea.value = String(loc.area || '')
    startTime.value = String(schedule.startTime || '07:30')
    endTime.value = String(schedule.endTime || '18:00')
    const rs = _ensureObj(me.value.reportSettings)
    dailyEnabled.value = !!_ensureObj(rs.daily).enabled
    dailySubmitTime.value = String(_ensureObj(rs.daily).submitTime || '12:00')
    weeklyEnabled.value = !!_ensureObj(rs.weekly).enabled
    monthlyEnabled.value = !!_ensureObj(rs.monthly).enabled
    assignPushNotifications(me.value.pushNotifications)
    if (bound.value) {
      await Promise.all([loadClockInMissingDays(), loadAllReportPeriodOptions()])
    }
  } catch (e) {
    notifyError(resolveErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const save = async () => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  const clockIn = _ensureObj(me.value.clockIn)
  const location = _ensureObj(clockIn.location)
  const schedule = _ensureObj(clockIn.schedule)
  location.address = String(clockInAddress.value || '').trim()
  location.latitude = String(clockInLatitude.value || '').trim()
  location.longitude = String(clockInLongitude.value || '').trim()
  location.province = String(clockInProvince.value || '').trim()
  location.city = String(clockInCity.value || '').trim()
  location.area = String(clockInArea.value || '').trim()
  schedule.startTime = String(startTime.value || '07:30')
  schedule.endTime = String(endTime.value || '18:00')
  clockIn.location = location
  clockIn.schedule = schedule

  const reportSettings = _ensureObj(me.value.reportSettings)
  reportSettings.daily = {
    ..._ensureObj(reportSettings.daily),
    enabled: !!dailyEnabled.value,
    submitTime: String(dailySubmitTime.value || '12:00'),
  }
  reportSettings.weekly = { ..._ensureObj(reportSettings.weekly), enabled: !!weeklyEnabled.value }
  reportSettings.monthly = { ..._ensureObj(reportSettings.monthly), enabled: !!monthlyEnabled.value }

  saving.value = true
  try {
    await userHttp.patch('/app/me', {
      password: String(password.value || '').trim() || undefined,
      enable_clockin: !!clockInEnabled.value,
      clockIn,
      reportSettings,
      pushNotifications: normalizePushNotifications(pushNotifications),
    })
    password.value = ''
    notifySuccess('已保存')
    await load()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

const reportLabelMap = { daily: '日报', weekly: '周报', monthly: '月报' }
const reportKeys = ['daily', 'weekly', 'monthly']
const isReportEnabled = (key) => {
  if (key === 'daily') return !!dailyEnabled.value
  if (key === 'weekly') return !!weeklyEnabled.value
  if (key === 'monthly') return !!monthlyEnabled.value
  return false
}
const clockInMakeupTypeLabel = computed(() => (clockInMakeupType.value === 'END' ? '下班' : '上班'))
const reportPendingCount = (key) => (Array.isArray(reportPeriodOptions[key]) ? reportPeriodOptions[key].length : 0)
const reportMakeupAllInProgress = (key) => reportMakeupAllProgressKey.value === key && (reportMakeupAllLoading.value === key || reportMakeupAllPercent.value > 0)
const clearReportPeriodOptions = (key) => {
  reportPeriodOptions[key] = []
  reportTargets[key] = ''
}
const filteredClockInPeriodOptions = computed(() => {
  const options = Array.isArray(clockInPeriodOptions.value) ? clockInPeriodOptions.value : []
  return options
    .filter((item) => Array.isArray(item.missing_types) && item.missing_types.includes(clockInMakeupType.value))
    .map((item) => ({ ...item, label: `${item.value}（缺${clockInMakeupTypeLabel.value}）` }))
})
const syncClockInTargetFromOptions = () => {
  const options = filteredClockInPeriodOptions.value
  if (!options.length) {
    clockInTargetDates.value = []
    return
  }
  const validValues = new Set(options.map((item) => item.value))
  const selected = Array.isArray(clockInTargetDates.value) ? clockInTargetDates.value : []
  clockInTargetDates.value = selected.filter((item) => validValues.has(item))
  if (!clockInTargetDates.value.length) {
    clockInTargetDates.value = [options[0].value]
  }
}

const loadClockInMissingDays = async () => {
  if (!bound.value) return
  clockInPeriodLoading.value = true
  try {
    const res = await userHttp.get('/app/clock-in/missing-days')
    clockInPeriodOptions.value = Array.isArray(res.data?.options) ? res.data.options : []
    clockInRecordCount.value = Number(res.data?.record_count || 0)
    syncClockInTargetFromOptions()
  } catch (e) {
    clockInPeriodOptions.value = []
    clockInRecordCount.value = 0
    clockInTargetDates.value = []
    notifyWarning(resolveErrorMessage(e, '获取缺卡日期失败'))
  } finally {
    clockInPeriodLoading.value = false
  }
}

const makeupClockIn = async () => {
  const targetDates = Array.isArray(clockInTargetDates.value) ? clockInTargetDates.value : []
  if (!targetDates.length) {
    notifyWarning('暂无可补卡日期')
    return
  }
  clockInMakeupLoading.value = true
  try {
    const res = await userHttp.post('/app/clock-in/makeup', {
      target_dates: targetDates,
      target_type: clockInMakeupType.value,
    }, { timeout: CLOCKIN_MAKEUP_REQUEST_TIMEOUT })
    const result = res.data?.result || {}
    if (result.status === 'success') {
      notifySuccess(result.message || '补卡完成')
    } else if (result.status === 'skip') {
      notifyWarning(result.message || '已跳过补卡')
    } else {
      notifyError(result.message || '补卡失败')
    }
    await loadClockInMissingDays()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '补卡失败'))
  } finally {
    clockInMakeupLoading.value = false
  }
}

const makeupAllClockIn = async () => {
  if (!filteredClockInPeriodOptions.value.length) {
    notifyWarning('暂无待补卡日期')
    return
  }
  clockInMakeupAllLoading.value = true
  startClockInMakeupAllProgress(filteredClockInPeriodOptions.value.length)
  try {
    const res = await userHttp.post('/app/clock-in/makeup-all', {
      target_type: clockInMakeupType.value,
    }, { timeout: CLOCKIN_MAKEUP_REQUEST_TIMEOUT })
    const result = res.data?.result || {}
    if (result.status === 'success') {
      notifySuccess(result.message || '全部补卡完成')
    } else if (result.status === 'skip') {
      notifyWarning(result.message || '已跳过补卡')
    } else {
      notifyError(result.message || '全部补卡失败')
    }
    finishClockInMakeupAllProgress()
    await loadClockInMissingDays()
  } catch (e) {
    resetClockInMakeupAllProgress()
    notifyError(resolveErrorMessage(e, '全部补卡失败'))
  } finally {
    clockInMakeupAllLoading.value = false
  }
}

const getReportTarget = (key) => String(reportTargets[key] || '').trim() || undefined
const hasReportTarget = (key) => !!getReportTarget(key)
const syncReportTargetFromOptions = (key) => {
  const options = Array.isArray(reportPeriodOptions[key]) ? reportPeriodOptions[key] : []
  if (!options.length) {
    reportTargets[key] = ''
    return
  }
  if (!options.some((item) => item.value === reportTargets[key])) {
    reportTargets[key] = options[0].value
  }
}

const loadReportPeriodOptions = async (key) => {
  if (!bound.value) return
  if (!isReportEnabled(key)) {
    clearReportPeriodOptions(key)
    notifyWarning(`${reportLabelMap[key] || '报告'}未开启，不获取待补周期`)
    return
  }
  reportPeriodLoading[key] = true
  try {
    const res = await userHttp.get(`/app/reports/${key}/missing-periods`)
    reportPeriodOptions[key] = Array.isArray(res.data?.options) ? res.data.options : []
    syncReportTargetFromOptions(key)
  } catch (e) {
    reportPeriodOptions[key] = []
    reportTargets[key] = ''
    notifyWarning(resolveErrorMessage(e, `获取${reportLabelMap[key] || '报告'}未提交周期失败`))
  } finally {
    reportPeriodLoading[key] = false
  }
}

const loadAllReportPeriodOptions = async () => {
  if (!bound.value) return
  reportKeys.filter((key) => !isReportEnabled(key)).forEach(clearReportPeriodOptions)
  await Promise.all(reportKeys.filter(isReportEnabled).map((key) => loadReportPeriodOptions(key)))
}

const generateReport = async (key) => {
  const label = reportLabelMap[key] || '报告'
  if (!isReportEnabled(key)) {
    notifyWarning(`${label}未开启`)
    return
  }
  if (!hasReportTarget(key)) {
    notifyWarning(`暂无可补交的${label}周期`)
    return
  }
  reportActionLoading.value = `${key}_generate`
  try {
    const res = await userHttp.post(`/app/reports/${key}/generate`, null, {
      params: { target_period: getReportTarget(key) },
    })
    reportPreview[key] = String(res.data?.content || '')
    notifySuccess(`${label}已生成`)
  } catch (e) {
    notifyError(resolveErrorMessage(e, `${label}生成失败`))
  } finally {
    reportActionLoading.value = ''
  }
}

const submitReport = async (key) => {
  const label = reportLabelMap[key] || '报告'
  if (!isReportEnabled(key)) {
    notifyWarning(`${label}未开启`)
    return
  }
  if (!hasReportTarget(key)) {
    notifyWarning(`暂无可补交的${label}周期`)
    return
  }
  const content = String(reportPreview[key] || '').trim()
  if (!content) {
    notifyError(`请先生成或填写${label}内容`)
    return
  }
  reportActionLoading.value = `${key}_submit`
  try {
    const res = await userHttp.post(`/app/reports/${key}/submit`, {
      content,
      target_period: getReportTarget(key),
    })
    notifySuccess(`提交成功：${res.data?.title || label}`)
    await loadReportPeriodOptions(key)
  } catch (e) {
    notifyError(resolveErrorMessage(e, `${label}提交失败`))
  } finally {
    reportActionLoading.value = ''
  }
}

const makeupAllReports = async (key) => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  const label = reportLabelMap[key] || '报告'
  if (!isReportEnabled(key)) {
    clearReportPeriodOptions(key)
    notifyWarning(`${label}未开启`)
    return
  }
  const total = reportPendingCount(key)
  if (!total) {
    notifyWarning(`暂无待补交${label}周期`)
    return
  }
  reportMakeupAllLoading.value = key
  startReportMakeupAllProgress(key, total)
  try {
    notifyInfo(`正在补交全部待补${label}`)
    const res = await userHttp.post(`/app/reports/${key}/makeup-all`, null, {
      timeout: REPORT_MAKEUP_REQUEST_TIMEOUT,
    })
    const result = res.data?.result || {}
    if (result.status === 'success') {
      notifySuccess(result.message || `全部${label}补交完成`)
    } else if (result.status === 'skip') {
      notifyWarning(result.message || `已跳过${label}补交`)
    } else {
      notifyError(result.message || `全部${label}补交失败`)
    }
    finishReportMakeupAllProgress()
    await loadReportPeriodOptions(key)
  } catch (e) {
    resetReportMakeupAllProgress()
    notifyError(resolveErrorMessage(e, `全部${label}补交失败`))
  } finally {
    reportMakeupAllLoading.value = ''
  }
}

const runReportNow = async (taskType) => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  const labelMap = {
    daily_report: '日报',
    weekly_report: '周报',
    monthly_report: '月报',
  }
  const reportKeyMap = {
    daily_report: 'daily',
    weekly_report: 'weekly',
    monthly_report: 'monthly',
  }
  const label = labelMap[taskType] || '报告'
  const key = reportKeyMap[taskType]
  if (!isReportEnabled(key)) {
    notifyWarning(`${label}未开启`)
    return
  }
  if (!hasReportTarget(key)) {
    notifyWarning(`暂无可补交的${label}周期`)
    return
  }
  reportRunLoading.value = taskType
  try {
    const res = await userHttp.post('/app/run', {
      task_type: taskType,
      force_report: true,
      target_period: getReportTarget(key),
    })
    const results = Array.isArray(res.data?.results) ? res.data.results : []
    const first = results[0] || {}
    if (first.status === 'success') {
      if (first.report_content && key && reportPreview[key] !== undefined) {
        reportPreview[key] = first.report_content
      }
      notifySuccess(first.message || `${label}已提交`)
    } else if (first.status === 'skip') {
      notifyWarning(first.message || `${label}已跳过`)
    } else {
      notifyError(first.message || `${label}执行失败`)
    }
    if (key) await loadReportPeriodOptions(key)
  } catch (e) {
    notifyError(resolveErrorMessage(e, `${label}执行失败`))
  } finally {
    reportRunLoading.value = ''
  }
}

const back = () => router.push('/u')

watch(
  () => [dailyEnabled.value, weeklyEnabled.value, monthlyEnabled.value].join('|'),
  () => {
    reportKeys.filter((key) => !isReportEnabled(key)).forEach(clearReportPeriodOptions)
  }
)

onUnmounted(() => {
  resetClockInMakeupAllProgress()
  resetReportMakeupAllProgress()
  if (geocodeSearchAbort) geocodeSearchAbort.abort()
})

load()
</script>

<style scoped>
.page {
  padding: 14px 12px;
}
.bind-row {
  width: 100%;
  display: flex;
  gap: 10px;
  align-items: center;
}
.bind-action {
  flex: 0 0 auto;
}
.bind-form {
  width: 100%;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.bind-form :deep(.el-input) {
  flex: 1 1 160px;
}
.bind-hint {
  width: 100%;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.address-row {
  width: 100%;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.address-row :deep(.el-input) {
  flex: 1 1 260px;
}
.location-grid {
  width: 100%;
}
.clockin-backfill {
  width: 100%;
}
.clockin-backfill-row {
  width: 100%;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.clockin-backfill-row :deep(.el-select) {
  flex: 1 1 220px;
}
.clockin-backfill-row :deep(.clockin-type-select) {
  flex: 0 0 120px;
}
.clockin-backfill-progress {
  margin-top: 10px;
  max-width: 520px;
}
.clockin-backfill-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.report-backfill {
  width: 100%;
}
.report-backfill-row {
  width: 100%;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.report-backfill-row :deep(.el-select) {
  flex: 1 1 220px;
}
.report-backfill-progress {
  margin-top: 10px;
  max-width: 520px;
}
.report-backfill-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.report-now-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.report-now-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.report-preview-input {
  margin-top: 10px;
}
.header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.title {
  font-weight: 700;
  font-size: 16px;
}
.sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.2px;
  color: var(--el-text-color-primary);
}
.sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.save-btn {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
  border: none !important;
  box-shadow: 0 0 15px -2px rgba(16, 185, 129, 0.4);
}
.save-btn:hover {
  transform: translateY(-1px);
}
.clockin-backfill, .report-backfill {
  padding: 12px 14px;
  background: var(--el-border-color-extra-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--radius-md);
}
:deep(.el-form-item) {
  margin-bottom: 20px;
}

</style>
