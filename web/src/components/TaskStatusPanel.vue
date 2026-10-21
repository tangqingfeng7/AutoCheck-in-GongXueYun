<template>
  <el-card class="task-status" shadow="never">
    <template #header><div class="status-heading"><strong>任务状态面板</strong><el-button :loading="loading" @click="load">刷新状态</el-button></div></template>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="state">
      <p>调度器：<el-tag :type="state.scheduler_running ? 'success' : 'danger'">{{ state.scheduler_running ? '运行中' : '未运行' }}</el-tag>
        自动打卡：{{ state.enabled ? '已启用' : '已停用' }}</p>
      <p v-for="job in state.jobs" :key="job.type">下次{{ job.type === 'start' ? '上班' : '下班' }}：{{ formatTime(job.next_run) }}</p>
      <p>最近执行：{{ state.last_run || '尚无记录' }} · {{ state.last_status || '-' }}</p>
      <p>进程保活：{{ ({healthy: '正常', restarting: '正在恢复', degraded: '服务异常，未强杀进程', stale: '心跳过期', unknown: '无心跳记录'})[state.watchdog?.state] || state.watchdog?.state }}（仅当前开机期间）</p>
      <p v-for="(result, i) in state.last_results" :key="i">{{ result.task_type }}：{{ result.message }}
        <el-tag v-if="result.details?.record_confirmed" type="success">服务端记录已确认 {{ result.details.server_time }}</el-tag>
      </p>
      <p>漏执行检测：{{ state.monitor ? `${state.monitor.day} · ${formatEpoch(state.monitor.checked_at)}` : '计划时间过后 5 分钟开始，只读检查，不自动补签' }}</p>
      <p v-for="check in state.monitor?.checks || []" :key="check.target_type">{{ check.target_type === 'START' ? '上班' : '下班' }}：{{ check.record_confirmed ? '服务端记录已确认' : check.confirmation_state === 'missing' ? '未查到记录，已进入提醒流程' : '查询不可用，不能判断是否漏卡' }}
        <span v-if="check.incident_id && check.record_confirmed"> · 异常已恢复，通知：{{ mailLabel(check.notification_state || 'queued') }}</span>
      </p>
      <h4>本次授权事务（可在刷新页面后继续检查）</h4>
      <p v-if="!state.verification_sessions?.length">暂无待处理授权；只有签到实际触发验证时才会创建事务。</p>
      <div v-for="item in state.verification_sessions || []" :key="item.id" class="verification-item">
        <p>{{ item.attendance_date }} · {{ item.target_type === 'START' ? '上班' : '下班' }} · {{ verificationLabel(item.state) }}</p>
        <p v-if="item.server_time">服务端记录：{{ item.server_time }}</p>
        <p v-if="item.last_checked">上次检查：{{ formatEpoch(item.last_checked) }}；两次检查至少间隔 15 秒。</p>
        <p v-if="['verification_query_failed', 'record_query_failed'].includes(item.check_state)">官方查询暂不可用，仍是待确认，不代表签到失败或验证通过。</p>
        <el-button v-if="['awaiting_verification', 'verified_pending_record'].includes(item.state)" :loading="busyId === item.id" @click="openVerification(item)">查看授权二维码和链接</el-button>
        <el-button v-if="item.state !== 'record_confirmed'" :loading="busyId === item.id" @click="checkVerification(item)">我已完成授权，仅检查记录</el-button>
      </div>
      <el-dialog v-model="authorizationVisible" title="本次签到授权" width="min(92vw, 520px)" append-to-body @closed="authorization = null">
        <template v-if="authorization">
          <p>{{ verificationLabel(authorization.state) }}。完成验证后返回检查，授权完成不等于签到成功。</p>
          <img :src="authorization.qr_data_url" alt="本次支付宝授权二维码" style="width: 280px; max-width: 100%" />
          <p><a :href="authorization.browser_url" target="_blank" rel="noopener noreferrer">打开支付宝验证</a></p>
          <el-input :model-value="authorization.direct_url" readonly aria-label="本次授权链接" />
          <el-button @click="copyAuthorization">复制授权链接</el-button>
          <el-button :loading="busyId === authorization.id" @click="checkVerification(authorization)">我已完成授权，仅检查记录</el-button>
        </template>
      </el-dialog>
      <template v-if="state.mail">
        <h4>最近邮件投递（租户范围）</h4>
        <p v-if="!state.mail.length">暂无邮件队列记录</p>
        <el-table :data="state.mail.slice(0, 5)">
          <el-table-column label="投递状态"><template #default="scope">{{ mailLabel(scope.row.status) }}</template></el-table-column>
          <el-table-column prop="attempts" label="尝试次数" />
          <el-table-column label="更新时间"><template #default="scope">{{ formatEpoch(scope.row.updated_at) }}</template></el-table-column>
          <el-table-column prop="error" label="错误类型" />
        </el-table>
      </template>
      <small>状态每 30 秒刷新；邮件“已接受”表示 SMTP 接受，不等于保证进入收件箱。</small>
    </template>
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { http } from '../api/http'
import { userHttp } from '../api/userHttp'
const props = defineProps({ userId: { type: Number, default: null }, self: Boolean })
const emit = defineEmits(['status'])
const state = ref(null)
const error = ref('')
const loading = ref(false)
const busyId = ref(null)
const authorization = ref(null)
const authorizationVisible = ref(false)
let timer
let disposed = false
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '无已加载任务'
const formatEpoch = value => value ? formatTime(new Date(value * 1000).toISOString()) : '-'
const mailLabel = value => ({ sent: 'SMTP 已接受', retry: '等待重试', queued: '已入队', sending: '发送中', failed: '发送失败', uncertain: '投递结果未知，请查收', expired: '已过期', cancelled: '旧提醒已取消', pending_enqueue: '等待入队', enqueue_failed: '入队失败，稍后再试', disabled: '未启用邮件通知' }[value] || value)
const verificationLabel = value => ({ awaiting_verification: '等待本人验证', verified_pending_record: '验证已确认，等待考勤记录', record_confirmed: '考勤记录已确认', expired: '授权链接已过期，可检查记录', superseded: '已由新事务替代' }[value] || value)
const client = () => props.self ? userHttp : http
const sessionPath = id => props.self ? `/app/verification-sessions/${id}` : `/users/${props.userId}/verification-sessions/${id}`
const openVerification = async item => {
  busyId.value = item.id
  try { authorization.value = (await client().get(sessionPath(item.id))).data; authorizationVisible.value = true; error.value = '' }
  catch (e) { error.value = e.response?.data?.detail || '授权链接加载失败，请先检查记录' }
  finally { busyId.value = null }
}
const checkVerification = async item => {
  busyId.value = item.id
  try {
    const data = (await client().post(`${sessionPath(item.id)}/check`)).data
    if (data.state === 'record_confirmed' || data.state === 'expired') { authorizationVisible.value = false; authorization.value = null }
    else if (authorization.value?.id === item.id) authorization.value = { ...authorization.value, ...data }
    await load()
  } catch (e) { error.value = e.response?.data?.detail || '本次授权尚无法确认' }
  finally { busyId.value = null }
}
const copyAuthorization = async () => {
  try { await navigator.clipboard.writeText(authorization.value?.direct_url || '') }
  catch { error.value = '复制失败，请选中链接手动复制' }
}
const load = async () => {
  if (loading.value || (!props.self && !props.userId)) return
  loading.value = true
  try {
    const response = await (props.self ? userHttp : http).get(props.self ? '/app/task-status' : `/users/${props.userId}/task-status`)
    if (!disposed) {
      state.value = response.data; error.value = ''
      emit('status', state.value)
      if (authorization.value) {
        const session = state.value.verification_sessions?.find(item => item.id === authorization.value.id)
        if (!session || ['expired', 'record_confirmed', 'superseded'].includes(session.state)) {
          authorizationVisible.value = false; authorization.value = null
        }
      }
    }
  } catch { if (!disposed) error.value = '状态加载失败，请检查服务和登录状态' }
  finally { loading.value = false }
}
watch(() => props.userId, () => { authorizationVisible.value = false; authorization.value = null; load() })
onMounted(() => { load(); timer = setInterval(load, 30000) })
onUnmounted(() => { disposed = true; clearInterval(timer) })
</script>

<style scoped>
.task-status { margin-bottom: 18px; }
.status-heading { display: flex; justify-content: space-between; align-items: center; }
p { overflow-wrap: anywhere; }
small { color: var(--el-text-color-secondary); }
</style>
