import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './api.js'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { title: '登录', public: true } },
  { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { title: '仪表盘' } },
  { path: '/pipelines', name: 'pipelines', component: () => import('./views/PipelineListView.vue'), meta: { title: '流水线' } },
  { path: '/pipelines/:id/edit', name: 'editor', component: () => import('./views/PipelineEditorView.vue'), meta: { title: '编排流水线' } },
  { path: '/runs/:id', name: 'run', component: () => import('./views/RunDetailView.vue'), meta: { title: '执行详情' } },
  { path: '/reports', name: 'reports', component: () => import('./views/ReportsView.vue'), meta: { title: '报告中心' } },
  { path: '/ai', name: 'ai', component: () => import('./views/AIAssistantView.vue'), meta: { title: 'AI 助手' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!to.meta.public && !auth.loggedIn()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.loggedIn()) {
    return { path: '/' }
  }
})

export default router
