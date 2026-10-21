<template>
  <div class="auth-page">
    <div class="auth-box">
      <div class="auth-brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" stroke="white" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
        <div class="brand-text">
          <h1 class="brand-title">工学云个人门户</h1>
          <p class="brand-sub">打卡与报告工作台登录</p>
        </div>
      </div>

      <div class="auth-card">
        <el-form :model="form" class="auth-form" @keyup.enter="submit">
          <div class="form-field">
            <label class="field-label">手机号 / 账号</label>
            <el-input 
              v-model="form.phone" 
              placeholder="请输入手机号或账号" 
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
              placeholder="请输入密码" 
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
        <span>还没有账号？</span>
        <button class="footer-link" @click="router.push('/u/register')">注册账号</button>
        <span class="footer-divider">&middot;</span>
        <button class="footer-link secondary" @click="router.push('/login')">管理后台</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { userHttp } from '../../api/userHttp'
import { useUserAuthStore } from '../../stores/userAuth'
import { notifyError, notifyWarning, resolveErrorMessage } from '../../utils/notify'

const router = useRouter()
const route = useRoute()
const auth = useUserAuthStore()
const loading = ref(false)

const form = reactive({
  phone: '',
  password: '',
})

const resolveUserRedirect = () => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && (redirect === '/u' || redirect.startsWith('/u/')) ? redirect : '/u'
}

const submit = async () => {
  if (!form.phone || !form.password) {
    notifyWarning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const res = await userHttp.post('/app/auth/login', {
      phone: form.phone,
      password: form.password,
    })
    if (!res.data?.phone) throw new Error('login response missing phone')
    auth.setAuth(res.data?.token || 'cookie', res.data?.phone, res.data?.user_id)
    router.replace(resolveUserRedirect())
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
  gap: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.footer-divider {
  color: var(--el-text-color-placeholder);
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

.footer-link.secondary {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.footer-link:hover {
  text-decoration: underline;
}
</style>
