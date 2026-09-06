<template>
  <div class="login-page">
    <div
      v-for="(bg, i) in backgrounds"
      :key="bg"
      class="bg-layer"
      :class="{ active: i === bgIndex }"
      :style="{ backgroundImage: `url(${bg})` }"
    />
    <div class="login-overlay" />

    <div class="login-card">
      <!-- 左：品牌展示区 -->
      <div class="brand-pane">
        <div class="brand-top">
          <MapleLogo :size="54" />
          <h1 class="brand-title">Maple Pipeline</h1>
          <div class="brand-badge">CI 质量门禁流水线平台</div>
        </div>

        <div class="brand-features">
          <div class="feature-item">
            <span class="feature-icon">⑂</span>
            <span>DAG 流水线编排 · 并行调度 · 失败阻断</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">✦</span>
            <span>DeepSeek 驱动的智能归因与报告生成</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">▤</span>
            <span>质量门禁卡点 · 测试左移 · AI 助手</span>
          </div>
        </div>

        <p class="brand-slogan">每一片枫叶，都记录一次质量交付 🍁</p>
      </div>

      <!-- 右：表单区 -->
      <div class="form-pane">
        <div class="tabs">
          <button type="button" class="tab" :class="{ active: mode === 'login' }" @click="mode = 'login'">登 录</button>
          <button type="button" class="tab" :class="{ active: mode === 'register' }" @click="mode = 'register'">注 册</button>
        </div>

        <form class="login-form" @submit.prevent="submit">
          <div class="field">
            <label>用户名</label>
            <input v-model.trim="form.username" class="input"
                   autocomplete="username" placeholder="输入你的用户名" />
          </div>

          <div class="field">
            <label>密码</label>
            <div class="pwd-wrap">
              <input v-model="form.password" class="input pwd-input"
                     :type="showPwd ? 'text' : 'password'"
                     :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
                     placeholder="输入你的密码" />
              <button type="button" class="eye-btn" :title="showPwd ? '隐藏密码' : '显示密码'" @click="showPwd = !showPwd">
                <svg v-if="showPwd" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
                <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              </button>
            </div>
          </div>

          <div v-if="mode === 'register'" class="field">
            <label>确认密码</label>
            <input v-model="form.confirm" class="input" type="password"
                   autocomplete="new-password" placeholder="再次输入密码" />
          </div>

          <div v-if="error" class="error-tip">{{ error }}</div>

          <button type="submit" class="submit-btn" :disabled="busy">
            {{ busy ? '请稍候…' : (mode === 'login' ? '登 录' : '注 册') }}
          </button>
        </form>

        <p class="switch-line">
          <template v-if="mode === 'login'">还没有账号？<a @click="mode = 'register'">立即注册</a></template>
          <template v-else>已有账号？<a @click="mode = 'login'">直接登录</a></template>
        </p>
      </div>
    </div>

    <div class="bg-dots">
      <button
        v-for="(bg, i) in backgrounds"
        :key="bg"
        class="bg-dot"
        :class="{ active: i === bgIndex }"
        :title="`背景 ${i + 1} / ${backgrounds.length}`"
        :aria-label="`切换到背景 ${i + 1}`"
        @click="jumpTo(i)"
      />
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapleLogo from '../components/MapleLogo.vue'
import { api, auth } from '../api.js'

const route = useRoute()
const router = useRouter()
const mode = ref('login')
const busy = ref(false)
const error = ref('')
const showPwd = ref(false)
const form = reactive({ username: '', password: '', confirm: '' })

const backgrounds = [
  '/bg/bg-1.jpg', '/bg/bg-2.jpg', '/bg/bg-3.jpg', '/bg/bg-4.jpg',
  '/bg/bg-5.jpg', '/bg/bg-6.jpg', '/bg/bg-7.jpg', '/bg/bg-8.jpg',
  '/bg/bg-9.jpg',
]
const bgIndex = ref(Math.floor(Math.random() * backgrounds.length))
let bgTimer = null

function startTimer() {
  clearInterval(bgTimer)
  bgTimer = setInterval(() => {
    bgIndex.value = (bgIndex.value + 1) % backgrounds.length
  }, 10000)
}

function jumpTo(i) {
  bgIndex.value = i
  startTimer()
}

onMounted(startTimer)
onBeforeUnmount(() => clearInterval(bgTimer))

async function submit() {
  error.value = ''
  if (!/^[A-Za-z0-9_]{3,20}$/.test(form.username)) {
    error.value = '用户名需为 3-20 位字母 / 数字 / 下划线'
    return
  }
  if (form.password.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  if (mode.value === 'register' && form.password !== form.confirm) {
    error.value = '两次输入的密码不一致'
    return
  }

  busy.value = true
  try {
    if (mode.value === 'register') {
      await api.register(form.username, form.password)
    }
    const { token, username } = await api.login(form.username, form.password)
    auth.save(token, username)
    router.replace(route.query.redirect || '/')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 22px;
  background: #451A03;
  position: relative;
}
.bg-layer {
  position: absolute; inset: 0;
  background-position: center;
  background-size: cover;
  opacity: 0;
  transition: opacity 1.6s ease;
}
.bg-layer.active { opacity: 1; }
.login-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(120deg, rgba(69, 26, 3, 0.55) 0%, rgba(69, 26, 3, 0.35) 50%, rgba(120, 53, 15, 0.45) 100%);
  z-index: 1;
}

.bg-dots { position: relative; z-index: 1; display: flex; gap: 11px; }
.bg-dot {
  width: 10px; height: 10px; border-radius: 999px; border: none; padding: 0;
  background: rgba(255, 255, 255, 0.42); cursor: pointer;
  box-shadow: 0 1px 5px rgba(0, 0, 0, 0.4);
  transition: width 0.25s, background 0.25s;
}
.bg-dot:hover { background: rgba(255, 255, 255, 0.75); }
.bg-dot.active { width: 28px; background: #fff; }

.login-card {
  position: relative; z-index: 1;
  display: flex; width: 880px; max-width: 94vw; min-height: 520px;
  border-radius: 22px; overflow: hidden;
  box-shadow: 0 24px 60px rgba(69, 26, 3, 0.45);
}

/* ---------- 左侧品牌区 ---------- */
.brand-pane {
  flex: 0 0 44%;
  background: linear-gradient(165deg, #B45309 0%, #92400E 55%, #78350F 100%);
  color: #fff;
  display: flex; flex-direction: column; justify-content: space-between;
  padding: 44px 38px 32px;
  text-align: center;
}
.brand-top { display: flex; flex-direction: column; align-items: center; }
.brand-title {
  font-size: 24px; font-weight: 800; letter-spacing: 1px; margin-top: 14px;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
}
.brand-badge {
  margin-top: 10px; font-size: 12.5px; padding: 5px 14px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.16); backdrop-filter: blur(4px);
}

.brand-features { display: flex; flex-direction: column; gap: 12px; margin: 26px 0; }
.feature-item {
  display: flex; align-items: center; gap: 10px; text-align: left;
  font-size: 13px; padding: 11px 16px; border-radius: 12px;
  background: rgba(255, 255, 255, 0.13); backdrop-filter: blur(6px);
}
.feature-icon {
  width: 26px; height: 26px; border-radius: 8px; flex-shrink: 0;
  background: rgba(255, 255, 255, 0.22);
  display: inline-flex; align-items: center; justify-content: center; font-size: 14px;
}

.brand-slogan { font-size: 12px; opacity: 0.85; font-style: italic; }

/* ---------- 右侧表单区 ---------- */
.form-pane {
  flex: 1; background: #FFFDF8;
  display: flex; flex-direction: column; justify-content: center;
  padding: 44px 46px 34px;
}

.tabs {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
  background: #F5EFE6; padding: 6px; border-radius: 999px; margin-bottom: 30px;
}
.tab {
  border: none; background: transparent; padding: 10px 0; border-radius: 999px;
  font-size: 14.5px; font-weight: 600; color: #8B8378; cursor: pointer;
  transition: all 0.2s; letter-spacing: 2px;
}
.tab.active {
  background: #fff; color: #92400E;
  box-shadow: 0 3px 8px rgba(146, 64, 14, 0.16);
}

.login-form { display: flex; flex-direction: column; gap: 18px; }
.field label {
  display: block; font-size: 13px; font-weight: 600; color: #5C4033; margin-bottom: 7px;
}
.field .input {
  width: 100%; height: 46px; padding: 0 14px;
  border: 1.5px solid #E0DCD6; border-radius: 12px;
  background: #fff; font-size: 14px; outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}
.field .input:focus {
  border-color: #F59E0B;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
}

.pwd-wrap { position: relative; }
.pwd-input { padding-right: 46px; }
.eye-btn {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  width: 34px; height: 34px; border: none; background: transparent; border-radius: 8px;
  color: #A8A29E; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
}
.eye-btn:hover { color: #B45309; background: #FEF3C7; }

.error-tip {
  background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA;
  padding: 10px 14px; border-radius: 10px; font-size: 13px;
}

.submit-btn {
  margin-top: 6px; height: 48px; border: none; border-radius: 999px;
  background: linear-gradient(135deg, #F59E0B 0%, #EA580C 100%);
  color: #fff; font-size: 16px; font-weight: 700; letter-spacing: 8px; text-indent: 8px;
  cursor: pointer; transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 6px 18px rgba(234, 88, 12, 0.35);
}
.submit-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 22px rgba(234, 88, 12, 0.45); }
.submit-btn:disabled { opacity: 0.7; cursor: not-allowed; }

.switch-line { text-align: center; font-size: 13px; color: #A8A29E; margin-top: 22px; }
.switch-line a { color: #B45309; font-weight: 700; cursor: pointer; }
.switch-line a:hover { text-decoration: underline; }

/* ---------- 响应式 ---------- */
@media (max-width: 768px) {
  .login-card { flex-direction: column; min-height: unset; }
  .brand-pane { flex: none; padding: 30px 24px 22px; }
  .brand-features { display: none; }
  .brand-slogan { margin-top: 12px; }
  .form-pane { padding: 30px 26px 26px; }
}
</style>
