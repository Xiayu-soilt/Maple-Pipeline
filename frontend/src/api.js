const BASE = ''

const TOKEN_KEY = 'maple_token'
const USER_KEY = 'maple_user'

export const auth = {
  token: () => localStorage.getItem(TOKEN_KEY) || '',
  user: () => { try { return JSON.parse(localStorage.getItem(USER_KEY)) } catch { return null } },
  save(token, username) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify({ username }))
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
  loggedIn() { return !!localStorage.getItem(TOKEN_KEY) },
}

function redirectToLogin() {
  auth.clear()
  if (!location.pathname.startsWith('/login')) {
    location.href = '/login'
  }
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const token = auth.token()
  if (token) headers.Authorization = `Bearer ${token}`
  const resp = await fetch(BASE + path, { ...options, headers })
  if (resp.status === 401 && !path.startsWith('/api/auth/')) {
    redirectToLogin()
    throw new Error('登录已过期，请重新登录')
  }
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`
    try { msg = (await resp.json()).detail || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return resp.json()
}

export const api = {
  health: () => fetch('/').then(r => r.ok),
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username, password) =>
    request('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request('/api/auth/me'),
  dashboard: () => request('/api/dashboard'),
  pipelines: () => request('/api/pipelines'),
  pipeline: (id) => request(`/api/pipelines/${id}`),
  createPipeline: (data) => request('/api/pipelines', { method: 'POST', body: JSON.stringify(data) }),
  updatePipeline: (id, data) => request(`/api/pipelines/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePipeline: (id) => request(`/api/pipelines/${id}`, { method: 'DELETE' }),
  triggerRun: (id, body = {}) => request(`/api/pipelines/${id}/run`, { method: 'POST', body: JSON.stringify(body) }),
  runs: (pipelineId = null) => request(`/api/runs${pipelineId ? `?pipeline_id=${pipelineId}` : ''}`),
  run: (id) => request(`/api/runs/${id}`),
  runLogs: (id) => request(`/api/runs/${id}/logs`),
  gateAdvice: (pipelineId) => request('/api/ai/gate-advice', { method: 'POST', body: JSON.stringify({ pipeline_id: pipelineId }) }),
  reports: () => request('/api/reports'),
  uploadFile: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const resp = await fetch('/api/uploads', { method: 'POST', body: form })
    if (!resp.ok) {
      let msg = `HTTP ${resp.status}`
      try { msg = (await resp.json()).detail || msg } catch { /* ignore */ }
      throw new Error(msg)
    }
    return resp.json()
  },
}

export async function ssePost(path, body, { onChunk, onDone, onError } = {}) {
  const resp = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    const msg = `HTTP ${resp.status}`
    onError?.(msg)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop()
    for (const part of parts) {
      if (!part.startsWith('data:')) continue
      try {
        const { type, data } = JSON.parse(part.slice(5))
        if (type === 'chunk') onChunk?.(data)
        else if (type === 'done') onDone?.(data)
        else if (type === 'error') onError?.(data)
      } catch { /* ignore malformed */ }
    }
  }
}

export class RunSocket {
  constructor(runId, handlers) {
    this.runId = runId
    this.handlers = handlers
    this.ws = null
    this.closed = false
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${proto}://${location.host}/ws/runs/${this.runId}?token=${encodeURIComponent(auth.token())}`)
    this.ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        this.handlers[event.type]?.(event)
      } catch { /* ignore */ }
    }
    this.ws.onclose = () => {
      if (!this.closed) setTimeout(() => this.connect(), 2000)
    }
  }

  close() {
    this.closed = true
    this.ws?.close()
  }
}

export const NODE_TYPES = {
  checkout: { label: '拉取代码', icon: '⎇', color: '#64748B', group: '源码与构建' },
  code_lint: { label: '代码检查', icon: '‹›', color: '#0891B2', group: '源码与构建' },
  build: { label: '构建', icon: '⚙', color: '#7C3AED', group: '源码与构建' },
  db_migration: { label: '数据库迁移', icon: '⇉', color: '#0D9488', group: '源码与构建' },
  test: { label: '自动化测试', icon: '✓', color: '#0EA5E9', group: '自动化测试' },
  api_test: { label: '接口测试', icon: '⇄', color: '#0284C7', group: '自动化测试' },
  e2e_test: { label: 'UI 自动化', icon: '◫', color: '#4F46E5', group: '自动化测试' },
  perf_test: { label: '性能测试', icon: '⚡', color: '#EA580C', group: '自动化测试' },
  scan: { label: '安全扫描', icon: '⛨', color: '#8B5CF6', group: '质量与发布' },
  gate: { label: '质量门禁', icon: '⏳', color: '#F5B301', group: '质量与发布' },
  approval: { label: '人工审批', icon: '✍', color: '#B45309', group: '质量与发布' },
  artifact: { label: '制品发布', icon: '⬡', color: '#2563EB', group: '质量与发布' },
  deploy: { label: '部署', icon: '▲', color: '#16A34A', group: '质量与发布' },
  health_check: { label: '冒烟检查', icon: '♥', color: '#059669', group: '质量与发布' },
  notify: { label: '通知', icon: '✉', color: '#DB2777', group: '通用' },
  custom: { label: '自定义', icon: '★', color: '#78716C', group: '通用' },
}

export const NODE_GROUPS = ['源码与构建', '自动化测试', '质量与发布', '通用']

export function defaultConfig(type) {
  return {
    test: { command: 'pytest tests/ --alluredir=reports/allure --cov=app' },
    api_test: { command: 'pytest tests/api/ --alluredir=reports/allure-api' },
    e2e_test: { command: 'npx playwright test tests/e2e/' },
    perf_test: { command: 'locust -f locustfile.py --headless -u 200 -r 20 -t 60s' },
    code_lint: { command: 'ruff check app/ && npx eslint src/ --quiet' },
    scan: { command: 'bandit -r app/ -f json -o reports/bandit.json && pip-audit -q' },
    build: { command: 'pip install -r requirements.txt && python -m build --wheel' },
    db_migration: { command: 'alembic upgrade head' },
    artifact: { command: 'docker build -t registry.internal/app:1.0.0 . && docker push registry.internal/app:1.0.0' },
    health_check: { command: 'curl -sf http://staging.internal/healthz' },
    notify: { command: 'python scripts/notify.py --channel dingtalk' },
    custom: { command: 'bash scripts/task.sh' },
    gate: { pass_rate_min: 100, coverage_min: 80, issues_max: 0 },
    deploy: { environment: 'staging' },
    approval: { approvers: 'qa-lead@example.com' },
  }[type] || {}
}

export const COMMAND_TYPES = ['build', 'test', 'api_test', 'e2e_test', 'perf_test', 'code_lint', 'scan', 'db_migration', 'artifact', 'health_check', 'notify', 'custom']

export const STATUS_META = {
  pending: { label: '等待', color: '#A8A29E', bg: '#F5F5F4' },
  running: { label: '执行中', color: '#B45309', bg: '#FEF3C7' },
  success: { label: '成功', color: '#15803D', bg: '#DCFCE7' },
  failed: { label: '失败', color: '#B91C1C', bg: '#FEE2E2' },
  skipped: { label: '被阻断', color: '#78716C', bg: '#F5F5F4' },
}

export function formatDuration(ms) {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
}

export function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts + (ts.endsWith('Z') ? '' : 'Z')).toLocaleString('zh-CN', { hour12: false })
}
