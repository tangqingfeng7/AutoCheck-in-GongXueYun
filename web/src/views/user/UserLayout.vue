<template>
  <div class="user-layout">
    <header class="user-header">
      <div class="user-header-main">
        <div class="user-brand" @click="router.push('/u')">
          <div class="user-brand-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" stroke="white" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <span class="user-brand-title">工学云个人门户</span>
        </div>

        <nav class="user-nav-pills">
          <button 
            class="user-nav-btn" 
            :class="{ 'is-active': route.path === '/u' }" 
            @click="router.push('/u')"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
              <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            </svg>
            <span>工作台</span>
          </button>
          <button 
            class="user-nav-btn" 
            :class="{ 'is-active': route.path === '/u/preauthorizations' }" 
            @click="router.push('/u/preauthorizations')"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            <span>预授权</span>
          </button>
          <button 
            class="user-nav-btn" 
            :class="{ 'is-active': route.path === '/u/settings' }" 
            @click="router.push('/u/settings')"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <span>设置</span>
          </button>
        </nav>

        <div class="user-actions">
          <span class="user-phone-text">{{ auth.phone || '已登录' }}</span>
          <button class="user-logout-btn" @click="logout" title="退出登录">
            退出
          </button>
        </div>
      </div>
    </header>

    <main class="user-body">
      <router-view />
    </main>

    <nav class="mobile-bottom-bar">
      <button class="mobile-tab-btn" :class="{ 'is-active': route.path === '/u' }" @click="router.push('/u')">
        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
          <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
        </svg>
        <span>工作台</span>
      </button>
      <button class="mobile-tab-btn" :class="{ 'is-active': route.path === '/u/preauthorizations' }" @click="router.push('/u/preauthorizations')">
        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        <span>预授权</span>
      </button>
      <button class="mobile-tab-btn" :class="{ 'is-active': route.path === '/u/settings' }" @click="router.push('/u/settings')">
        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
        <span>设置</span>
      </button>
    </nav>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { userHttp } from '../../api/userHttp'
import { useUserAuthStore } from '../../stores/userAuth'

const route = useRoute()
const router = useRouter()
const auth = useUserAuthStore()

const logout = async () => {
  try {
    await userHttp.post('/app/auth/logout')
  } catch {}
  auth.logout()
  router.replace('/u/login')
}
</script>

<style scoped>
.user-layout {
  min-height: 100vh;
  min-height: 100dvh;
  background-color: var(--el-bg-color-page);
  display: flex;
  flex-direction: column;
}

.user-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--nav-bg);
  backdrop-filter: var(--surface-blur);
  -webkit-backdrop-filter: var(--surface-blur);
  border-bottom: 1px solid var(--el-border-color);
}

.user-header-main {
  max-width: 1080px;
  margin: 0 auto;
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.user-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.user-brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-brand-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--el-text-color-primary);
}

.user-nav-pills {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(120, 120, 128, 0.08);
  padding: 3px;
  border-radius: var(--radius-pill);
}

.user-nav-btn {
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

.user-nav-btn:hover {
  color: var(--el-text-color-primary);
}

.user-nav-btn.is-active {
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.user-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-phone-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  font-family: var(--font-mono);
}

.user-logout-btn {
  background: transparent;
  border: none;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-danger);
  cursor: pointer;
  padding: 4px 8px;
}

.user-logout-btn:hover {
  opacity: 0.8;
}

.user-body {
  flex: 1;
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 20px;
}

.mobile-bottom-bar {
  display: none;
}

@media (max-width: 768px) {
  .user-header-main {
    padding: 10px 16px;
  }
  .user-nav-pills {
    display: none;
  }
  .user-body {
    padding: 16px 14px 74px 14px;
  }
  .mobile-bottom-bar {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 90;
    height: 56px;
    background: var(--nav-bg);
    backdrop-filter: var(--surface-blur);
    -webkit-backdrop-filter: var(--surface-blur);
    border-top: 1px solid var(--el-border-color);
    justify-content: space-around;
    align-items: center;
    padding-bottom: env(safe-area-inset-bottom);
  }
  .mobile-tab-btn {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    background: transparent;
    border: none;
    color: var(--el-text-color-secondary);
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    padding: 6px 0;
  }
  .mobile-tab-btn.is-active {
    color: var(--el-color-primary);
  }
}
</style>
