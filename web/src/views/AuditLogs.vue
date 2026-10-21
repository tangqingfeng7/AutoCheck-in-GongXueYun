<template>
  <el-card class="page-card">
    <template #header>
      <div class="page-header">
        <div class="page-header-left">
          <div class="page-title">系统审计与安全追踪日志</div>
          <div class="page-subtitle">追溯系统关键管理动作、任务执行记录与配置变更痕迹</div>
        </div>
        <div class="page-actions">
          <el-input
            v-model="query"
            placeholder="搜索操作者 / 触发动作"
            clearable
            class="audit-search-input"
            @keyup.enter="onSearch"
          >
            <template #prefix>
              <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </template>
          </el-input>
          <el-button @click="onSearch">搜索</el-button>
          <el-button @click="resetSearch">重置</el-button>
          <el-button 
            type="danger" 
            plain 
            :loading="clearing" 
            :disabled="loading || total === 0" 
            @click="clearLogs"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="margin-right: 4px;">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            清空日志
          </el-button>
        </div>
      </div>
    </template>

    <div class="table-wrap">
      <el-table :data="items" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="序号" width="70" align="center" />
        <el-table-column prop="created_at" label="操作时间" width="180">
          <template #default="scope">
            <span class="audit-time-text">{{ scope.row.created_at }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actor" label="操作人" width="150">
          <template #default="scope">
            <div class="actor-cell">
              <span class="actor-dot"></span>
              <span class="actor-name">{{ scope.row.actor }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="触发动作" min-width="160">
          <template #default="scope">
            <el-tag size="small" effect="plain" class="action-tag">{{ scope.row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_user_id" label="目标用户 ID" width="120" align="center">
          <template #default="scope">
            <span class="target-id-pill">{{ scope.row.target_user_id ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="详情 Payload" min-width="260">
          <template #default="scope">
            <div class="detail-box">
              <pre class="detail">{{ scope.row.detailText }}</pre>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100, 200]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="fetchLogs"
        @current-change="fetchLogs"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { http } from '../api/http'
import { notifyError, notifySuccess, resolveErrorMessage } from '../utils/notify'

const items = ref([])
const loading = ref(false)
const clearing = ref(false)
const query = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
let fetchAbort = null

const stringify = (v) => {
  try {
    return JSON.stringify(v ?? {}, null, 0)
  } catch {
    return String(v ?? '')
  }
}

const fetchLogs = async () => {
  if (fetchAbort) fetchAbort.abort()
  fetchAbort = new AbortController()
  loading.value = true
  try {
    const res = await http.get('/audit-logs/page', {
      params: {
        page: page.value,
        pageSize: pageSize.value,
        query: query.value ? query.value.trim() : undefined,
      },
      signal: fetchAbort.signal,
    })
    const raw = res.data?.items || []
    items.value = raw.map(i => ({ ...i, detailText: stringify(i.detail) }))
    total.value = res.data?.total ?? raw.length
  } catch (e) {
    if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
    notifyError(resolveErrorMessage(e, '获取审计日志失败'))
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.value = 1
  fetchLogs()
}

const resetSearch = () => {
  query.value = ''
  page.value = 1
  fetchLogs()
}

const clearLogs = async () => {
  try {
    await ElMessageBox.confirm('确定要清空所有审计日志吗？清空后将无法恢复。', '警告', {
      confirmButtonText: '确定清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  clearing.value = true
  try {
    await http.delete('/audit-logs')
    notifySuccess('审计日志已清空')
    page.value = 1
    fetchLogs()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '清空审计日志失败'))
  } finally {
    clearing.value = false
  }
}

onMounted(fetchLogs)
</script>

<style scoped>
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

.audit-search-input {
  width: 220px;
}

.audit-time-text {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--el-text-color-regular);
}

.actor-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.actor-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand-primary);
}

.actor-name {
  font-weight: 600;
  font-size: 13px;
}

.action-tag {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

.target-id-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-xs);
  background: var(--el-border-color-extra-light);
  border: 1px solid var(--el-border-color-light);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.detail-box {
  max-height: 80px;
  overflow: auto;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid var(--el-border-color-light);
}

.detail {
  margin: 0;
  font-size: 11px;
  font-family: var(--font-mono);
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-regular);
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
