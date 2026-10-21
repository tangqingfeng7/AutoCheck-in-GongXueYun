import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../web/package.json', import.meta.url))
const { parse, compileTemplate } = require('@vue/compiler-sfc')
const source = fs.readFileSync(new URL('../web/src/components/TaskStatusPanel.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'TaskStatusPanel.vue', id: 'test' }).errors, [])
assert.match(descriptor.template.content, /@click="clearVerificationSessions">清空授权事务/)
const body = descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
const factory = new Function('ref', 'onMounted', 'onUnmounted', 'watch', 'defineProps', 'defineEmits', 'ElMessage', 'ElMessageBox', 'http', 'userHttp', `${body}
return { state, error, loading, busyId, clearing, authorization, authorizationVisible, load, clearVerificationSessions, openVerification, checkVerification }`)

function fixture(self = true) {
  const props = { self, userId: self ? null : 7 }
  const calls = [], messages = []
  let sessions = [{ id: 'fixture', state: 'awaiting_verification' }]
  const client = {
    get: async path => { calls.push(['get', path]); return { data: { verification_sessions: sessions } } },
    delete: async path => { calls.push(['delete', path]); sessions = []; return { data: { cleared: 1 } } }
  }
  const box = { confirm: async () => {} }
  const vm = factory(value => ({ value }), () => {}, () => {}, () => {}, () => props, () => () => {},
    { success: text => messages.push(text) }, box, client, client)
  return { vm, props, calls, messages, box, client }
}

for (const self of [true, false]) {
  const { vm, calls, messages } = fixture(self)
  await vm.load()
  vm.authorization.value = { id: 'fixture' }; vm.authorizationVisible.value = true
  await vm.clearVerificationSessions()
  assert.deepEqual(calls[1], ['delete', self ? '/app/verification-sessions' : '/users/7/verification-sessions'])
  assert.deepEqual(vm.state.value.verification_sessions, [])
  assert.equal(vm.authorizationVisible.value, false)
  assert.equal(vm.authorization.value, null)
  assert.equal(messages[0], '已清理 1 条授权事务')
  await vm.load()
  assert.deepEqual(vm.state.value.verification_sessions, [])
}
for (const reason of ['cancel', 'close']) {
  const { vm, calls, box } = fixture()
  await vm.load(); box.confirm = async () => { throw reason }
  await vm.clearVerificationSessions()
  assert.equal(calls.length, 1); assert.equal(vm.state.value.verification_sessions.length, 1)
  assert.equal(vm.error.value, ''); assert.equal(vm.clearing.value, false)
}
{
  const { vm, client } = fixture()
  await vm.load(); client.delete = async () => { throw { response: { data: { detail: 'fixture failure' } } } }
  await vm.clearVerificationSessions()
  assert.equal(vm.state.value.verification_sessions.length, 1)
  assert.equal(vm.error.value, 'fixture failure'); assert.equal(vm.clearing.value, false)
}
{
  const { vm, calls, box } = fixture()
  await vm.load()
  let confirm
  box.confirm = () => new Promise(resolve => { confirm = resolve })
  const pending = vm.clearVerificationSessions()
  await vm.load(); await vm.clearVerificationSessions(); await vm.openVerification({}); await vm.checkVerification({})
  assert.equal(calls.length, 1)
  confirm(); await pending
  assert.equal(calls.length, 2)
}
{
  const { vm, calls, box, props } = fixture(false)
  await vm.load()
  box.confirm = async () => { props.userId = 8 }
  await vm.clearVerificationSessions()
  assert.equal(calls.length, 1)
}
console.log('PASS: user/admin clear, refresh persistence, cancel/close, failure preservation, busy guards, account switch, Vue template compilation')
