<template>
  <div class="auth-page">
    <div class="auth-box">
      <div class="auth-brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" stroke="white" stroke-linecap="round" stroke-linejoin="round" />
            <path d="m9 13 2 2 4-4" stroke="white" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" />
          </svg>
        </div>
        <div class="brand-text">
          <h1 class="brand-title">工学云管理平台</h1>
          <p class="brand-sub">后台控制台</p>
        </div>
      </div>

      <div class="auth-card">
        <el-form :model="form" class="auth-form" @keyup.enter="submit">
          <div class="form-field">
            <label class="field-label">账号</label>
            <el-input 
              v-model="form.username" 
              placeholder="请输入管理员账号" 
              autocomplete="username"
              size="large"
            />
          </div>

          <div class="form-field">
            <label class="field-label">密码</label>
            <el-input 
              v-model="form.password" 
              type="password" 
              show-password 
              placeholder="请输入管理密码" 
              autocomplete="current-password"
              size="large"
            />
          </div>

          <el-button 
            type="primary" 
            class="submit-btn" 
            :loading="loading" 
            @click="submit"
          >
            登录
          </el-button>
        </el-form>
      </div>

      <div class="auth-footer">
        <span class="footer-hint">用户端入口：</span>
        <button class="footer-link" @click="router.push('/u/login')">进入用户工作台 &rarr;</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { notifyWarning, notifyError, resolveErrorMessage } from '../utils/notify'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  username: '',
  password: ''
})

const loading = ref(false)

const submit = async () => {
  if (!form.username || !form.password) {
    notifyWarning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const res = await http.post('/auth/login', {
      username: form.username,
      password: form.password,
    })
    if (!res.data?.role) throw new Error('login response missing role')
    auth.setAuth(res.data?.token || 'cookie', res.data?.username, res.data?.role, res.data?.permissions)
    router.replace('/')
  } catch (e) {
    notifyError(resolveErrorMessage(e, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background-color: var(--el-bg-color-page);
}

.auth-box {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.auth-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 12px;
}

.brand-logo {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  display: block;
  color: var(--el-text-color-primary) !important;
  -webkit-text-fill-color: initial !important;
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  color: var(--el-text-color-primary);
  letter-spacing: -0.2px;
}

.brand-sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0;
}

.auth-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: var(--radius-lg);
  padding: 28px 24px;
  box-shadow: var(--shadow-card);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.submit-btn {
  width: 100%;
  height: 42px;
  font-size: 14px;
  font-weight: 600;
  margin-top: 4px;
}

.auth-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.footer-hint {
  color: var(--el-text-color-secondary);
}

.footer-link {
  background: transparent;
  border: none;
  color: var(--el-color-primary);
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  font-size: 13px;
}

.footer-link:hover {
  text-decoration: underline;
}
</style>
