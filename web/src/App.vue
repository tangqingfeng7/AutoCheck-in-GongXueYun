<template>
  <el-container class="layout-container" :class="{ 'is-plain': isPlainPage }">
    <el-header v-if="showAdminHeader" class="header">
      <div class="header-inner">
        <div class="header-left">
          <button v-if="isMobile" class="mobile-toggle-btn" @click="drawerVisible = true" aria-label="打开菜单">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          </button>
          
          <div class="brand" @click="go('/')">
            <div class="brand-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" stroke="white" stroke-linecap="round" stroke-linejoin="round" />
                <path d="m9 13 2 2 4-4" stroke="white" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" />
              </svg>
            </div>
            <span class="brand-title">工学云管理平台</span>
          </div>

          <nav v-if="!isMobile && isAuthed" class="nav-links">
            <button 
              class="nav-item" 
              :class="{ 'is-active': route.path === '/' || route.path.startsWith('/edit') || route.path === '/create' }"
              @click="go('/')"
            >
              <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              <span>用户管理</span>
            </button>
            <button 
              v-if="canReadAudit" 
              class="nav-item" 
              :class="{ 'is-active': route.path === '/audit' }"
              @click="go('/audit')"
            >
              <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
              <span>审计日志</span>
            </button>
            <button 
              v-if="canManageSettings" 
              class="nav-item" 
              :class="{ 'is-active': route.path.startsWith('/settings') }"
              @click="go('/settings')"
            >
              <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              <span>系统设置</span>
            </button>
          </nav>
        </div>

        <div class="header-actions">
          <div class="theme-toggle-wrap" @click="toggleTheme" title="切换暗色/亮色">
            <button class="theme-toggle-btn">
              <svg v-if="isDark" viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
                <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
            </button>
          </div>

          <template v-if="!isMobile && isAuthed">
            <div class="user-pill">
              <span class="user-name">{{ username || '管理员' }}</span>
              <span class="role-badge" :class="'role-' + (auth.role || 'viewer')">{{ roleLabel }}</span>
            </div>
            <button class="logout-btn" @click="logout" title="退出登录">
              退出
            </button>
          </template>
        </div>
      </div>
    </el-header>

    <el-main>
      <div class="page" :class="{ 'is-plain-page': isPlainPage }">
        <router-view />
      </div>
    </el-main>

    <el-drawer v-if="showAdminHeader" v-model="drawerVisible" title="控制台导航" direction="rtl" size="80%">
      <div class="drawer-body">
        <div v-if="isAuthed" class="drawer-user-card">
          <div class="drawer-avatar">
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div class="drawer-user-info">
            <div class="drawer-user-name">{{ username || '已登录' }}</div>
            <span class="role-badge" :class="'role-' + (auth.role || 'viewer')">{{ roleLabel }}</span>
          </div>
        </div>

        <div class="drawer-nav-list">
          <button v-if="isAuthed" class="drawer-nav-btn" :class="{ 'is-active': route.path === '/' }" @click="navTo('/')">
            <span>用户管理</span>
          </button>
          <button v-if="isAuthed && canReadAudit" class="drawer-nav-btn" :class="{ 'is-active': route.path === '/audit' }" @click="navTo('/audit')">
            <span>审计日志</span>
          </button>
          <button v-if="isAuthed && canManageSettings" class="drawer-nav-btn" :class="{ 'is-active': route.path.startsWith('/settings') }" @click="navTo('/settings')">
            <span>系统设置</span>
          </button>
        </div>

        <div class="drawer-footer">
          <button v-if="isAuthed" class="drawer-logout-btn" @click="logout">
            退出登录
          </button>
        </div>
      </div>
    </el-drawer>
  </el-container>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { http } from './api/http'

const isDark = ref(false)
const isMobile = ref(false)
const drawerVisible = ref(false)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isAuthed = computed(() => auth.isAuthed)
const canReadAudit = computed(() => auth.can('audit:read'))
const canManageSettings = computed(() => auth.can('settings:manage'))
const username = computed(() => auth.username)
const isLogin = computed(() => route.path === '/login')
const isUserRoute = computed(() => route.path.startsWith('/u'))
const isPlainPage = computed(() => isLogin.value || isUserRoute.value)
const showAdminHeader = computed(() => !isPlainPage.value)

const roleLabel = computed(() => {
  if (auth.role === 'admin') return '管理员'
  if (auth.role === 'operator') return '操作员'
  if (auth.role === 'viewer') return '只读'
  return '未授权'
})

const applyTheme = () => {
  const on = !!isDark.value
  document.documentElement.classList.toggle('dark', on)
  localStorage.setItem('theme', on ? 'dark' : 'light')
}

const toggleTheme = () => {
  isDark.value = !isDark.value
  applyTheme()
}

const go = (path) => {
  router.push(path)
}

const navTo = (path) => {
  drawerVisible.value = false
  router.push(path)
}

const logout = async () => {
  drawerVisible.value = false
  try {
    await http.post('/auth/logout')
  } catch {}
  auth.logout()
  router.replace('/login')
}

let removeMqListener = null

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'dark' || saved === 'light') {
    isDark.value = saved === 'dark'
  } else {
    isDark.value = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches || false
  }
  applyTheme()

  const mq = window.matchMedia?.('(max-width: 768px)')
  const update = () => {
    isMobile.value = !!mq?.matches
    if (!isMobile.value) drawerVisible.value = false
  }
  update()
  mq?.addEventListener?.('change', update)
  removeMqListener = () => mq?.removeEventListener?.('change', update)
})

onUnmounted(() => removeMqListener?.())
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.header {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 52px !important;
  padding: 0 20px;
  background: var(--nav-bg);
  backdrop-filter: var(--surface-blur);
  -webkit-backdrop-filter: var(--surface-blur);
  border-bottom: 1px solid var(--el-border-color);
  display: flex;
  align-items: center;
}

.header-inner {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.brand-icon {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--el-text-color-primary);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(120, 120, 128, 0.08);
  padding: 3px;
  border-radius: var(--radius-pill);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-pill);
  cursor: pointer;
  transition: all 0.2s ease;
}

.nav-item:hover {
  color: var(--el-text-color-primary);
}

.nav-item.is-active {
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.theme-toggle-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.theme-toggle-btn:hover {
  color: var(--el-text-color-primary);
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  background: rgba(120, 120, 128, 0.08);
  border-radius: var(--radius-pill);
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.role-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
}

.logout-btn {
  background: transparent;
  border: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-danger);
  cursor: pointer;
  padding: 4px 8px;
}

.logout-btn:hover {
  opacity: 0.8;
}

.el-main {
  flex: 1;
  padding: 24px 20px !important;
  background: var(--el-bg-color-page);
}

.layout-container.is-plain .el-main {
  padding: 0 !important;
}

.page {
  max-width: 1200px;
  margin: 0 auto;
}

.page.is-plain-page {
  max-width: 100%;
  margin: 0;
}

.mobile-toggle-btn {
  background: transparent;
  border: none;
  padding: 4px;
  color: var(--el-text-color-primary);
  cursor: pointer;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.drawer-user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(120, 120, 128, 0.08);
  border-radius: var(--radius-md);
}

.drawer-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drawer-user-name {
  font-size: 14px;
  font-weight: 600;
}

.drawer-nav-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.drawer-nav-btn {
  padding: 10px 14px;
  font-size: 14px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--el-text-color-primary);
  cursor: pointer;
  text-align: left;
}

.drawer-nav-btn.is-active {
  background: var(--el-color-primary);
  color: #fff;
}

.drawer-logout-btn {
  width: 100%;
  padding: 10px;
  font-size: 14px;
  border: none;
  border-radius: var(--radius-md);
  background: rgba(255, 59, 48, 0.1);
  color: var(--el-color-danger);
  cursor: pointer;
}
</style>
