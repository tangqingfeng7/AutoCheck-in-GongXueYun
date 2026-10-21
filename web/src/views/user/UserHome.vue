<template>
  <div class="user-home">
    <TaskStatusPanel v-if="me.bound" self @status="syncTaskStatus" />

    <div class="profile-card">
      <div class="profile-main">
        <div class="profile-avatar">
          <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" stroke-width="1.8" fill="none">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
        <div class="profile-content">
          <div class="profile-title-row">
            <h2 class="profile-name">{{ auth.phone || '工学云用户' }}</h2>
            <span class="status-pill" :class="me.bound ? 'pill-success' : 'pill-warning'">
              <span class="pill-dot"></span>
              {{ me.bound ? '已绑定账号' : '尚未绑定账号' }}
            </span>
          </div>
          <p class="profile-subtitle">
            {{ me.bound ? '自动化打卡与报告托管已就绪' : '请前往设置绑定工学云账号以开启任务' }}
          </p>
        </div>
      </div>

      <div class="profile-actions">
        <div class="status-summary-box">
          <span class="status-summary-label">运行状态</span>
          <span class="status-summary-val" :class="'val-' + latestStatus">
            <span class="indicator-dot"></span>
            {{ latestStatusText }}
          </span>
        </div>
        <div class="button-group">
          <button class="pill-btn" :disabled="loading" @click="loadAll" title="刷新数据">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none">
              <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            <span>刷新</span>
          </button>
          <button class="pill-btn primary" @click="router.push('/u/settings')">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <span>设置</span>
          </button>
        </div>
      </div>
    </div>

    <div class="section-card">
      <div class="section-head">
        <h3 class="section-title">任务下发</h3>
      </div>

      <div class="task-grid">
        <button 
          class="task-tile" 
          :disabled="!me.bound || !!runLoading" 
          @click="runTask('')"
        >
          <div class="task-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
          </div>
          <div class="task-meta">
            <div class="task-name">执行全部</div>
            <div class="task-hint">打卡与当日报告</div>
          </div>
          <span v-if="runLoading === 'all'" class="running-indicator">运行中</span>
        </button>

        <button 
          class="task-tile" 
          :disabled="!me.bound || !!runLoading" 
          @click="runTask('clock_in')"
        >
          <div class="task-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div class="task-meta">
            <div class="task-name">仅打卡</div>
            <div class="task-hint">上下班签到打卡</div>
          </div>
          <span v-if="runLoading === 'clock_in'" class="running-indicator">运行中</span>
        </button>

        <button 
          class="task-tile" 
          :disabled="!me.bound || !!runLoading" 
          @click="runTask('daily_report')"
        >
          <div class="task-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>
          <div class="task-meta">
            <div class="task-name">提交日报</div>
            <div class="task-hint">提交今日实习日报</div>
          </div>
          <span v-if="runLoading === 'daily_report'" class="running-indicator">运行中</span>
        </button>

        <button 
          class="task-tile" 
          :disabled="!me.bound || !!runLoading" 
          @click="runTask('report')"
        >
          <div class="task-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
          </div>
          <div class="task-meta">
            <div class="task-name">周期报告</div>
            <div class="task-hint">全检日周月报</div>
          </div>
          <span v-if="runLoading === 'report'" class="running-indicator">运行中</span>
        </button>
      </div>

      <div v-if="!me.bound" class="inline-warning">
        <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>尚未绑定工学云账号，请先进入设置绑定账号以执行任务。</span>
      </div>
    </div>

    <div class="dual-columns">
      <div class="column-card">
        <div class="column-head">
          <h3 class="section-title">实习日报</h3>
          <button 
            class="action-text-btn" 
            :disabled="!me.bound || generating" 
            @click="generateDailyReport"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            <span>{{ generating ? '生成中...' : '自动生成' }}</span>
          </button>
        </div>

        <div class="editor-pane">
          <textarea 
            v-model="dailyContent" 
            class="plain-textarea" 
            rows="6" 
            placeholder="输入或自动生成日报内容后提交..."
          ></textarea>
          <div class="editor-bottom-bar">
            <span class="count-text">{{ dailyContent.length }} 字</span>
            <div class="editor-btns">
              <button 
                v-if="dailyContent" 
                class="ghost-btn" 
                @click="dailyContent = ''"
              >
                清空
              </button>
              <button 
                class="commit-btn" 
                :disabled="!me.bound || !dailyContent.trim() || submitting" 
                @click="submitDailyReport"
              >
                {{ submitting ? '提交中...' : '提交日报' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="column-card">
        <div class="column-head">
          <h3 class="section-title">执行记录</h3>
        </div>

        <div v-if="!executions.length" class="empty-state">
          <span>暂无执行记录</span>
        </div>

        <div v-else class="log-list">
          <div v-for="(item, index) in executions" :key="index" class="log-item">
            <div class="log-indicator" :class="'dot-' + (item.status || 'unknown')"></div>
            <div class="log-details">
              <div class="log-header-line">
                <span class="log-task">{{ item.task_type || '打卡' }}</span>
                <span class="log-tag" :class="'tag-' + (item.status || 'unknown')">
                  {{ item.status || '未知' }}
                </span>
              </div>
              <div class="log-msg">{{ item.message || '-' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AlipayVerificationDialog
      v-model="verificationVisible"
      :register-url="verification?.registerUrl || ''"
      :verification-type="verification?.verificationType || 'account'"
      :continuing="verificationContinuing"
      @continue="continueClockIn"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { userHttp } from '../../api/userHttp'
import AlipayVerificationDialog from '../../components/AlipayVerificationDialog.vue'
import TaskStatusPanel from '../../components/TaskStatusPanel.vue'
import { useUserAuthStore } from '../../stores/userAuth'
import { notifyError, notifyInfo, notifySuccess, resolveErrorMessage } from '../../utils/notify'

const router = useRouter()
const auth = useUserAuthStore()

const loading = ref(false)
const generating = ref(false)
const submitting = ref(false)
const runLoading = ref('')
const me = ref({ app_phone: '', bound: false, task_user: null })
const executions = ref([])
const syncTaskStatus = snapshot => {
  if (Array.isArray(snapshot.last_results)) executions.value = snapshot.last_results
}
const dailyContent = ref('')
const verificationVisible = ref(false)
const verificationContinuing = ref(false)
const verification = ref(null)

const latestStatus = computed(() => {
  if (!executions.value.length) return 'none'
  if (executions.value.some(entry => entry.status === 'fail')) return 'fail'
  if (executions.value.some(entry => entry.status === 'pending')) return 'pending'
  if (executions.value.some(entry => entry.status === 'success')) return 'success'
  return 'skip'
})

const latestStatusText = computed(() => {
  if (latestStatus.value === 'pending') return '结果待服务端确认'
  if (latestStatus.value === 'success') return '成功'
  if (latestStatus.value === 'fail') return '异常'
  if (latestStatus.value === 'skip') return '跳过'
  return '就绪'
})

const loadMe = async () => {
  const res = await userHttp.get('/app/me')
  me.value = {
    app_phone: res.data?.app_phone || auth.phone,
    bound: !!res.data?.bound,
    task_user: res.data?.task_user || null,
  }
}

const loadExecution = async () => {
  const res = await userHttp.get('/app/execution')
  executions.value = Array.isArray(res.data?.results) ? res.data.results : []
}

const loadAll = async () => {
  loading.value = true
  try {
    await loadMe()
    if (me.value.bound) {
      await loadExecution()
    } else {
      executions.value = []
    }
  } catch (e) {
    notifyError(resolveErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const showAlipayVerification = (results) => {
  const item = (Array.isArray(results) ? results : []).find((entry) => {
    const details = entry?.details
    const verificationType = String(details?.verification_type || 'account')
    return (
      entry?.status === 'fail' &&
      (verificationType === 'face' || details?.outRegisterNo) &&
      String(details?.registerUrl || '').startsWith('alipays://')
    )
  })
  if (!item) return false

  const targetType = String(item.details?.target_type || 'START').toUpperCase()
  verification.value = {
    outRegisterNo: String(item.details.outRegisterNo || ''),
    registerUrl: String(item.details.registerUrl),
    verificationType: String(item.details?.verification_type || 'account'),
    attendanceDate: String(item.details?.createTime || '').slice(0, 10),
    targetType: ['START', 'END'].includes(targetType) ? targetType : 'START',
  }
  verificationVisible.value = true
  return true
}

const runTask = async (taskType) => {
  runLoading.value = taskType || 'all'
  try {
    const res = await userHttp.post('/app/run', taskType ? { task_type: taskType } : {})
    const needsVerification = showAlipayVerification(res.data?.results)
    if (needsVerification) {
      notifyInfo('需要安全验证')
    } else {
      notifySuccess('已触发执行')
    }
    await loadExecution()
    await loadMe()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '执行失败'))
  } finally {
    runLoading.value = ''
  }
}

const continueClockIn = async () => {
  if (!verification.value || verificationContinuing.value) return
  verificationContinuing.value = true
  try {
    const res = await userHttp.post('/app/clock-in/alipay/continue', {
      out_register_no: verification.value.outRegisterNo,
      target_type: verification.value.targetType,
      verification_type: verification.value.verificationType,
      attendance_date: verification.value.attendanceDate || null,
    })
    const result = res.data?.result
    if (showAlipayVerification([result])) {
      notifyInfo('仍需验证，信息已更新')
      return
    }
    if (['success', 'skip'].includes(result?.status)) {
      verificationVisible.value = false
      verification.value = null
      notifySuccess(result?.message || '打卡完成')
      await loadExecution()
      await loadMe()
      return
    }
    if (result?.status === 'pending') {
      if (result.details?.verification_confirmed) {
        verificationVisible.value = false
        verification.value = null
      }
      notifyInfo(result.message || '考勤记录待服务端确认')
      await loadExecution()
      await loadMe()
      return
    }
    notifyError(result?.message || '继续打卡失败')
  } catch (e) {
    notifyError(resolveErrorMessage(e, '继续打卡失败'))
  } finally {
    verificationContinuing.value = false
  }
}

const generateDailyReport = async () => {
  generating.value = true
  try {
    const res = await userHttp.post('/app/reports/daily/generate')
    dailyContent.value = String(res.data?.content || '')
    notifySuccess('已生成')
  } catch (e) {
    notifyError(resolveErrorMessage(e, '生成失败'))
  } finally {
    generating.value = false
  }
}

const submitDailyReport = async () => {
  submitting.value = true
  try {
    await userHttp.post('/app/reports/daily/submit', { content: dailyContent.value })
    notifySuccess('已提交')
    await loadExecution()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '提交失败'))
  } finally {
    submitting.value = false
  }
}

loadAll()
</script>

<style scoped>
.user-home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.profile-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--card-shadow);
}

.profile-main {
  display: flex;
  align-items: center;
  gap: 16px;
}

.profile-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(120, 120, 128, 0.1);
  color: var(--el-text-color-regular);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.profile-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.profile-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.profile-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--el-text-color-primary);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.status-pill.pill-success {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}
html.dark .status-pill.pill-success {
  background: rgba(48, 209, 88, 0.18);
  color: #30d158;
}

.status-pill.pill-warning {
  background: rgba(255, 149, 0, 0.12);
  color: #ff9500;
}
html.dark .status-pill.pill-warning {
  background: rgba(255, 214, 10, 0.18);
  color: #ffd60a;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: currentColor;
}

.profile-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.profile-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-summary-box {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: right;
}

.status-summary-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.status-summary-val {
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.indicator-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
}

.val-success { color: var(--el-color-success); }
.val-success .indicator-dot { background: var(--el-color-success); }
.val-fail { color: var(--el-color-danger); }
.val-fail .indicator-dot { background: var(--el-color-danger); }

.button-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pill-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-pill);
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.pill-btn:hover {
  background: rgba(120, 120, 128, 0.08);
}

.pill-btn:active {
  transform: scale(0.97);
}

.pill-btn.primary {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #ffffff;
}

.pill-btn.primary:hover {
  opacity: 0.9;
}

.section-card {
  padding: 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--card-shadow);
}

.section-head {
  margin-bottom: 14px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  letter-spacing: -0.01em;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.task-tile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(120, 120, 128, 0.04);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.task-tile:hover:not(:disabled) {
  background: rgba(120, 120, 128, 0.08);
  border-color: var(--el-border-color);
}

.task-tile:active:not(:disabled) {
  transform: scale(0.98);
}

.task-tile:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.task-icon {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-sm);
  background: rgba(120, 120, 128, 0.08);
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.task-meta {
  flex: 1;
  min-width: 0;
}

.task-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.task-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.running-indicator {
  font-size: 11px;
  color: var(--el-color-primary);
  font-weight: 500;
}

.inline-warning {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: rgba(255, 149, 0, 0.1);
  color: var(--el-color-warning);
  font-size: 12px;
}

.dual-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.column-card {
  padding: 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--card-shadow);
  display: flex;
  flex-direction: column;
}

.column-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.action-text-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  border: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-primary);
  cursor: pointer;
  padding: 0;
}

.action-text-btn:hover:not(:disabled) {
  opacity: 0.8;
}

.action-text-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.editor-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

.plain-textarea {
  width: 100%;
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--el-border-color);
  background: rgba(120, 120, 128, 0.04);
  color: var(--el-text-color-primary);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s ease;
}

.plain-textarea:focus {
  border-color: var(--el-color-primary);
  background: var(--el-bg-color);
}

.editor-bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.count-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.editor-btns {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ghost-btn {
  background: transparent;
  border: none;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.ghost-btn:hover {
  color: var(--el-color-danger);
}

.commit-btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-pill);
  border: none;
  background: var(--el-color-primary);
  color: #ffffff;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.commit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.commit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
}

.log-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: rgba(120, 120, 128, 0.04);
}

.log-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}

.dot-success { background: var(--el-color-success); }
.dot-fail { background: var(--el-color-danger); }
.dot-skip { background: var(--el-color-info); }
.dot-unknown { background: var(--el-text-color-placeholder); }

.log-details {
  flex: 1;
  min-width: 0;
}

.log-header-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.log-task {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.log-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
}

.tag-success { color: var(--el-color-success); background: rgba(52, 199, 89, 0.1); }
.tag-fail { color: var(--el-color-danger); background: rgba(255, 59, 48, 0.1); }
.tag-skip { color: var(--el-color-info); background: rgba(142, 142, 147, 0.1); }
.tag-unknown { color: var(--el-text-color-placeholder); }

.log-msg {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  line-height: 1.4;
  word-break: break-word;
}

@media (max-width: 820px) {
  .profile-card {
    flex-direction: column;
    align-items: stretch;
  }
  .profile-actions {
    justify-content: space-between;
  }
  .dual-columns {
    grid-template-columns: 1fr;
  }
}
</style>
