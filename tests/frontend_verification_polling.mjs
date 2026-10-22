import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../web/package.json', import.meta.url))
const { parse, compileTemplate } = require('@vue/compiler-sfc')
const source = fs.readFileSync(new URL('../web/src/components/TaskStatusPanel.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'TaskStatusPanel.vue', id: 'poll-test' }).errors, [])
assert.doesNotMatch(descriptor.template.content, /resumeVerification|授权完成，续提一次/)
assert.match(descriptor.template.content, /每 3 秒持续刷新/)
const body = descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
const factory = new Function('ref', 'onMounted', 'onUnmounted', 'watch', 'defineProps', 'defineEmits', 'ElMessage', 'ElMessageBox', 'http', 'userHttp', 'setInterval', 'clearInterval', `${body}\nreturn { load, state, loading }`)
for (const self of [true, false]) {
  let mount, unmount, tick, delay, active = 0, maxActive = 0, calls = 0, finish, cleared
  const client = { get: path => {
    assert.equal(path, self ? '/app/task-status' : '/users/7/task-status')
    calls++; active++; maxActive = Math.max(maxActive, active)
    return new Promise(resolve => { finish = () => { active--; resolve({ data: { verification_sessions: [] } }) } })
  } }
  const vm = factory(value => ({ value }), cb => { mount = cb }, cb => { unmount = cb }, () => {},
    () => ({ self, userId: self ? null : 7 }), () => () => {}, {}, {}, client, client,
    (cb, ms) => { tick = cb; delay = ms; return 99 }, id => { cleared = id })
  mount(); assert.equal(delay, 3000); assert.equal(calls, 1)
  await tick(); assert.equal(calls, 1) // Never overlap an in-flight response.
  finish(); await new Promise(resolve => setImmediate(resolve))
  const next = tick(); assert.equal(calls, 2); finish(); await next
  const third = tick(); assert.equal(calls, 3); finish(); await third
  assert.equal(maxActive, 1); assert.equal(vm.loading.value, false)
  unmount(); assert.equal(cleared, 99)
}
console.log('PASS: user/admin 3-second continuous polling, no request overlap, unmount cleanup, Vue template compilation')
