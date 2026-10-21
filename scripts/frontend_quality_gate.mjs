import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const WEB_SRC = path.join(ROOT, 'web', 'src')

const failures = []

const sourceFiles = (dir) => {
  const out = []
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, item.name)
    if (item.isDirectory()) {
      out.push(...sourceFiles(full))
    } else if (/\.(vue|js)$/.test(item.name)) {
      out.push(full)
    }
  }
  return out
}

const rel = (file) => path.relative(ROOT, file).replaceAll(path.sep, '/')

const read = (file) => fs.readFileSync(file, 'utf8')
const removedMfaPattern = /\bmfa_code\b|\bmfa_enabled\b|\bmfa_totp_secret\b|\bmfa_confirmed_at\b|\/auth\/mfa\b|\bone-time-code\b|SecuritySettings|账号安全|\bTOTP\b|\bMFA\b/i

for (const file of sourceFiles(WEB_SRC)) {
  const text = read(file)
  const relative = rel(file)

  if (/\bv-html\b/.test(text)) {
    failures.push(`${relative} uses v-html; render untrusted content as text`)
  }
  if (/\bdebugger\b/.test(text)) {
    failures.push(`${relative} contains debugger statement`)
  }
  if (/\bconsole\.(log|debug)\s*\(/.test(text)) {
    failures.push(`${relative} contains console.log/debug`)
  }
  if (/localStorage\.setItem\([^)]*(token|auth|password|secret)/i.test(text)) {
    failures.push(`${relative} may persist auth material in localStorage`)
  }
  if (/(invite|invitation|邀请)/i.test(text)) {
    failures.push(`${relative} introduces user invitation surface`)
  }
  if (removedMfaPattern.test(text)) {
    failures.push(`${relative} must not reintroduce removed MFA surface`)
  }
}

const login = read(path.join(WEB_SRC, 'views', 'Login.vue'))
if (removedMfaPattern.test(login)) {
  failures.push('web/src/views/Login.vue must not expose removed MFA fields')
}

const router = read(path.join(WEB_SRC, 'router', 'index.js'))
if (router.includes('SecuritySettings.vue') || router.includes('/security')) {
  failures.push('web/src/router/index.js must not expose removed MFA security route')
}

if (fs.existsSync(path.join(WEB_SRC, 'views', 'SecuritySettings.vue'))) {
  failures.push('web/src/views/SecuritySettings.vue must be removed with the MFA surface')
}

const http = read(path.join(WEB_SRC, 'api', 'http.js'))
if (!http.includes("'X-CSRF-Token': csrfToken")) {
  failures.push('web/src/api/http.js must attach CSRF token for unsafe methods')
}

if (failures.length > 0) {
  console.error('Frontend quality gate failed:')
  for (const failure of failures) {
    console.error(`- ${failure}`)
  }
  process.exit(1)
}

console.log('Frontend quality gate passed')
