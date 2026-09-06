<template>
  <div v-if="isLoginPage" class="login-shell">
    <RouterView />
  </div>

  <div v-else class="layout">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <MapleLogo :size="36" />
        <div>
          <div class="brand-name">Maple</div>
          <div class="brand-sub">Pipeline · 质量门禁平台</div>
        </div>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-item"
                    active-class="active">
          <span class="nav-icon" v-html="item.icon" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <MapleLogo :size="16" />
        <span>CI · 测试左移 · AI 驱动</span>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar-title">{{ route.meta.title || 'Maple Pipeline' }}</div>
        <div class="topbar-right">
          <span class="tag">DeepSeek 已接入</span>
          <span class="tag" :style="backendOk === null ? '' : backendOk ? 'background:#DCFCE7;color:#15803D' : 'background:#FEE2E2;color:#B91C1C'">
            {{ backendLabel }}
          </span>
          <div v-if="currentUser" class="user-chip" :title="`当前用户：${currentUser}`">
            <span class="user-avatar">{{ avatarChar }}</span>
            <span class="user-name">{{ currentUser }}</span>
          </div>
          <button class="btn btn-sm" @click="logout">退出</button>
        </div>
      </header>
      <main class="content">
        <RouterView v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MapleLogo from './components/MapleLogo.vue'
import { api, auth } from './api.js'

const route = useRoute()
const router = useRouter()
const backendOk = ref(null)
const backendLabel = computed(() =>
  backendOk.value === null ? '检测中' : backendOk.value ? '后端在线' : '后端离线')

const isLoginPage = computed(() => route.path === '/login')
const currentUser = ref(auth.user()?.username || '')
const avatarChar = computed(() => (currentUser.value || 'M').charAt(0).toUpperCase())

const navItems = [
  { to: '/', label: '仪表盘', icon: '▦' },
  { to: '/pipelines', label: '流水线', icon: '⑂' },
  { to: '/reports', label: '报告中心', icon: '▤' },
  { to: '/ai', label: 'AI 助手', icon: '✦' },
]

function logout() {
  auth.clear()
  currentUser.value = ''
  router.replace('/login')
}

// localStorage 非响应式，登录/退出靠路由变化时同步
watch(() => route.path, () => {
  const cached = auth.user()?.username || ''
  if (cached !== currentUser.value) currentUser.value = cached
})

onMounted(async () => {
  if (isLoginPage.value) return
  try {
    await api.health()
    backendOk.value = true
  } catch {
    backendOk.value = false
  }
  if (auth.loggedIn()) {
    try {
      const me = await api.me()
      currentUser.value = me.username
      auth.save(auth.token(), me.username)
    } catch { /* token 失效时 request 会自动跳登录页 */ }
  }
})
</script>

<style scoped>
.login-shell { height: 100vh; }
.user-chip { display: inline-flex; align-items: center; gap: 8px; }
.user-avatar {
  width: 26px; height: 26px; border-radius: 50%;
  background: linear-gradient(135deg, #F59E0B, #B45309);
  color: #fff; font-size: 13px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.user-name { font-size: 13px; font-weight: 600; color: var(--ink-700); }
</style>
