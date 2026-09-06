<template>
  <div v-if="run" class="run-detail">
    <!-- 信息条 -->
    <div class="card card-pad info-bar">
      <div class="info-main">
        <div class="info-title">
          <span class="badge badge-lg" :style="statusStyle(run.status)"><i class="dot" />{{ statusLabel(run.status) }}</span>
          <h2>{{ run.pipeline_name }}</h2>
          <span class="tag">#{{ run.id }}</span>
          <span class="tag">{{ run.trigger }}</span>
        </div>
        <div class="info-sub">
          <span>commit: <code>{{ run.commit_msg }}</code></span>
          <span>by {{ run.commit_author }}</span>
          <span v-if="run.stats?.pass_rate != null">通过率 {{ run.stats.pass_rate }}%</span>
          <span v-if="run.stats?.coverage != null">覆盖率 {{ run.stats.coverage }}%</span>
          <span>耗时 {{ fmtDuration(run.stats?.duration_ms) }}</span>
          <span>{{ fmtTime(run.finished_at) }}</span>
        </div>
      </div>
      <div class="info-actions">
        <button class="btn btn-sm" :disabled="aiBusy || !finished" @click="analyze">
          {{ aiBusy === 'analyze' ? 'AI 分析中…' : '✦ AI 失败归因' }}
        </button>
        <button class="btn btn-sm" :disabled="aiBusy || !finished" @click="makeReport">
          {{ aiBusy === 'report' ? '生成中…' : '📄 AI 执行报告' }}
        </button>
      </div>
    </div>

    <div class="run-grid">
      <!-- DAG 状态图 -->
      <div class="card dag-card">
        <div class="card-title card-pad" style="padding-bottom: 0">
          <span>流水线拓扑</span>
          <span class="legend">
            <span><i style="background:#F5B301" />执行中</span>
            <span><i style="background:#16A34A" />成功</span>
            <span><i style="background:#DC2626" />失败</span>
            <span><i style="background:#D6D3D1" />等待/阻断</span>
          </span>
        </div>
        <div ref="dagEl" class="dag-canvas" />
      </div>

      <!-- 门禁 + AI -->
      <div class="right-col">
        <div class="card card-pad gate-card">
          <div class="card-title"><span>⏳ 质量门禁</span>
            <span v-if="gateNode" class="badge" :style="gateBadgeStyle">
              {{ gatePassed ? '已通过' : '未通过' }}
            </span>
          </div>
          <template v-if="gateChecks.length">
            <div v-for="(c, i) in gateChecks" :key="i" class="gate-check" :class="c.passed ? 'pass' : 'fail'">
              <span class="gate-mark">{{ c.passed ? '✓' : '✕' }}</span>
              <span class="gate-name">{{ c.name }}</span>
              <span class="gate-expr">{{ c.actual }} {{ c.op }} {{ c.threshold }}</span>
            </div>
          </template>
          <div v-else-if="gateNode" class="gate-waiting">
            <span class="cursor-blink" style="vertical-align: middle" />
            {{ gateNode.status === 'running' ? '门禁评估中…' : '等待测试指标产出' }}
          </div>
          <div v-else class="gate-waiting">该流水线未配置质量门禁节点</div>
        </div>

        <div class="card card-pad ai-card">
          <div class="card-title"><span>✦ DeepSeek 智能分析</span></div>
          <div v-if="aiOutput" class="ai-output md" v-html="aiHtml" />
          <div v-else class="ai-placeholder">
            <p>执行结束后可使用：</p>
            <p>· <b>AI 失败归因</b> — 解析失败日志，定位根因并给出修复建议</p>
            <p>· <b>AI 执行报告</b> — 自动生成面向管理层的执行总结</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志终端 -->
    <div class="card terminal-card">
      <div class="terminal-head">
        <div class="node-tabs">
          <button class="node-tab" :class="{ active: logFilter === null }" @click="logFilter = null">全部</button>
          <button v-for="n in run.nodes" :key="n.node_id" class="node-tab"
                  :class="{ active: logFilter === n.node_id }" @click="logFilter = n.node_id">
            <i class="tab-dot" :style="{ background: STATUS_META[n.status]?.color }" />
            {{ n.name }}
          </button>
        </div>
      </div>
      <div ref="terminalEl" class="terminal">
        <div class="t-head"><span class="t-dot" /><span class="t-dot" /><span class="t-dot" /></div>
        <div v-for="(l, i) in filteredLogs" :key="i" class="log-line" :class="`level-${l.level}`">
          <span class="log-node" v-if="l.node_name && logFilter === null">[{{ l.node_name }}] </span>{{ l.message }}
        </div>
        <div v-if="isRunning" class="log-line"><span class="cursor-blink" /></div>
      </div>
    </div>
  </div>
  <div v-else class="empty">加载中…</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Graph } from '@antv/x6'
import { marked } from 'marked'
import { api, RunSocket, STATUS_META, NODE_TYPES, formatDuration, formatTime, ssePost } from '../api.js'

const route = useRoute()
const run = ref(null)
const dagEl = ref(null)
const terminalEl = ref(null)
const logs = ref([])
const logFilter = ref(null)
const aiOutput = ref('')
const aiBusy = ref(null)

let graph = null
let socket = null
let pollTimer = null
const seenLogKeys = new Set()

function pushLog(ev) {
  const key = `${ev.ts}|${ev.node_id}|${ev.message}`
  if (seenLogKeys.has(key)) return
  seenLogKeys.add(key)
  logs.value.push(ev)
}

function resetLogs(history) {
  logs.value = []
  seenLogKeys.clear()
  history.forEach(pushLog)
}

const finished = computed(() => ['success', 'failed'].includes(run.value?.status))
const isRunning = computed(() => ['running', 'pending'].includes(run.value?.status))
const nodeStatusMap = computed(() => {
  const m = {}
  run.value?.nodes?.forEach((n) => { m[n.node_id] = n })
  return m
})

const gateNode = computed(() => run.value?.nodes?.find((n) => n.node_type === 'gate'))
const gateChecks = computed(() => gateNode.value?.gate_result?.checks || [])
const gatePassed = computed(() => gateNode.value?.gate_result?.passed)

const gateBadgeStyle = computed(() => gatePassed.value
  ? { color: '#15803D', background: '#DCFCE7' }
  : { color: '#B91C1C', background: '#FEE2E2' })

const filteredLogs = computed(() => {
  if (logFilter.value === null) return logs.value.filter((l) => l.type === 'log')
  return logs.value.filter((l) => l.type === 'log' && l.node_id === logFilter.value)
})

const aiHtml = computed(() => marked.parse(aiOutput.value || ''))

const statusStyle = (s) => {
  const m = STATUS_META[s] || STATUS_META.pending
  return { color: m.color, background: m.bg }
}
const statusLabel = (s) => STATUS_META[s]?.label || s
const fmtDuration = formatDuration
const fmtTime = formatTime

function statusColor(status) {
  return {
    success: '#16A34A', failed: '#DC2626', running: '#F5B301',
    pending: '#D6D3D1', skipped: '#A8A29E',
  }[status] || '#D6D3D1'
}

function buildGraph() {
  if (!dagEl.value || !run.value) return
  const pipelineDag = run.value.pipeline_dag
  if (!pipelineDag) return
  if (graph) { graph.dispose() }
  graph = new Graph({
    container: dagEl.value,
    interacting: false,
    grid: false,
    panning: { enabled: true },
    mousewheel: { enabled: true, modifiers: 'ctrl', minScale: 0.4, maxScale: 2 },
  })
  for (const n of pipelineDag.nodes) {
    const nr = nodeStatusMap.value[n.id]
    const color = statusColor(nr?.status || 'pending')
    const icon = nr?.status === 'running' ? '⏳' : nr?.status === 'success' ? '✓' : nr?.status === 'failed' ? '✕' : NODE_TYPES[n.type]?.icon || ''
    graph.addNode({
      id: n.id,
      x: n.x, y: n.y, width: 168, height: 56,
      data: { type: n.type },
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'text', selector: 'title' },
        { tagName: 'text', selector: 'sub' },
      ],
      attrs: {
        body: {
          rx: 12, ry: 12, fill: nr?.status === 'running' ? '#FFFBEB' : '#fff',
          stroke: color, strokeWidth: 2,
          class: nr?.status === 'running' ? 'flow-running' : '',
        },
        title: {
          refX: 14, refY: 13, fill: '#1C1917', fontSize: 13, fontWeight: '600', textAnchor: 'start',
          text: `${icon} ${n.name}`,
          textWrap: { width: -28, height: 20, ellipsis: true },
        },
        sub: {
          refX: 14, refY: 33, fill: '#78716C', fontSize: 11, textAnchor: 'start',
          text: nr?.duration_ms ? `${NODE_TYPES[n.type]?.label || n.type} · ${formatDuration(nr.duration_ms)}` : (NODE_TYPES[n.type]?.label || n.type),
          textWrap: { width: -28, height: 16, ellipsis: true },
        },
      },
    })
  }
  for (const e of pipelineDag.edges) {
    graph.addEdge({
      source: { cell: e.source }, target: { cell: e.target },
      attrs: { line: { stroke: '#D6D3D1', strokeWidth: 2, targetMarker: { name: 'block', args: { size: 8 } } } },
    })
  }
  graph.centerContent()
}

function scrollTerminal() {
  nextTick(() => {
    if (terminalEl.value) terminalEl.value.scrollTop = terminalEl.value.scrollHeight
  })
}

async function refreshRun() {
  const data = await api.run(route.params.id)
  const oldDag = run.value?.pipeline_dag
  run.value = { ...data, pipeline_dag: oldDag }
  if (data.report_md && !aiOutput.value) aiOutput.value = data.report_md
}

function paintNode(nodeId, name, status) {
  if (!graph) return
  const cell = graph.getCellById(nodeId)
  if (!cell) return
  const color = statusColor(status)
  const meta = run.value?.pipeline_dag?.nodes?.find((n) => n.id === nodeId)
  const type = cell.getData?.()?.type || meta?.type
  const icon = status === 'running' ? '⏳' : status === 'success' ? '✓' : status === 'failed' ? '✕' : NODE_TYPES[type]?.icon || ''
  cell.attr({
    body: {
      stroke: color,
      fill: status === 'running' ? '#FFFBEB' : '#fff',
      class: status === 'running' ? 'flow-running' : '',
    },
    title: { text: `${icon} ${name}` },
  })
}

function applyNodeStatus(event) {
  const n = run.value?.nodes?.find((x) => x.node_id === event.node_id)
  if (n) {
    n.status = event.status
    n.duration_ms = event.duration_ms || n.duration_ms
    n.metrics = event.metrics || n.metrics
    if (event.gate_result) n.gate_result = event.gate_result
  }
  paintNode(event.node_id, event.name, event.status)
}

async function pollOnce() {
  if (!run.value || !isRunning.value) return
  try {
    const data = await api.run(route.params.id)
    const oldDag = run.value.pipeline_dag
    run.value = { ...data, pipeline_dag: oldDag }
    data.nodes?.forEach((n) => paintNode(n.node_id, n.name, n.status))
    const history = await api.runLogs(route.params.id)
    const known = logs.value.length
    if (history.length > known) resetLogs(history)
  } catch { /* 后端暂时不可达 */ }
}

async function analyze() {
  aiBusy.value = 'analyze'
  aiOutput.value = ''
  await ssePost(`/api/ai/analyze-failure/${route.params.id}`, {}, {
    onChunk: (c) => { aiOutput.value += c },
    onDone: () => {},
    onError: (e) => { aiOutput.value = `> 调用失败：${e}\n\n请检查 backend/.env 中的 DEEPSEEK_API_KEY 是否有效。` },
  })
  aiBusy.value = null
}

async function makeReport() {
  aiBusy.value = 'report'
  aiOutput.value = ''
  await ssePost(`/api/ai/report/${route.params.id}`, {}, {
    onChunk: (c) => { aiOutput.value += c },
    onDone: () => {},
    onError: (e) => { aiOutput.value = `> 调用失败：${e}` },
  })
  aiBusy.value = null
}

watch(filteredLogs, scrollTerminal, { deep: false })

onMounted(async () => {
  const data = await api.run(route.params.id)
  const p = await api.pipeline(data.pipeline_id)
  run.value = { ...data, pipeline_dag: p.dag }
  if (data.report_md) aiOutput.value = data.report_md
  await nextTick()
  buildGraph()

  const history = await api.runLogs(route.params.id)
  resetLogs(history)
  scrollTerminal()

  socket = new RunSocket(route.params.id, {
    log: (ev) => { pushLog(ev); scrollTerminal() },
    node_status: applyNodeStatus,
    run_status: async (ev) => {
      if (run.value) {
        run.value.status = ev.status
        if (ev.stats) run.value.stats = ev.stats
      }
      if (['success', 'failed'].includes(ev.status)) {
        setTimeout(refreshRun, 600)
      }
    },
  })
  socket.connect()
  pollTimer = setInterval(pollOnce, 4000)
})

onBeforeUnmount(() => {
  socket?.close()
  clearInterval(pollTimer)
  graph?.dispose()
})
</script>

<style scoped>
.run-detail { display: flex; flex-direction: column; gap: 14px; height: 100%; }
.info-bar { display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
.info-title { display: flex; align-items: center; gap: 10px; }
.info-title h2 { font-size: 16px; }
.badge-lg { font-size: 13px; padding: 5px 14px; }
.info-sub { display: flex; gap: 14px; font-size: 12.5px; color: var(--ink-500); margin-top: 8px; flex-wrap: wrap; }
.info-sub code { background: var(--ink-100); padding: 1px 6px; border-radius: 5px; font-family: var(--mono); font-size: 11.5px; }
.info-actions { display: flex; gap: 8px; }
.run-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 14px; min-height: 300px; flex: 1; }
.dag-card { overflow: hidden; display: flex; flex-direction: column; }
.dag-canvas { flex: 1; min-height: 280px; }
.legend { display: flex; gap: 12px; font-size: 11.5px; color: var(--ink-500); font-weight: 400; }
.legend span { display: flex; align-items: center; gap: 4px; }
.legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.right-col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.gate-check {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px;
  border-radius: 9px; margin-bottom: 7px; font-size: 12.5px;
}
.gate-check.pass { background: #F0FDF4; color: #15803D; }
.gate-check.fail { background: #FEF2F2; color: #B91C1C; }
.gate-mark { font-weight: 800; width: 14px; }
.gate-name { font-weight: 600; }
.gate-expr { margin-left: auto; font-family: var(--mono); font-size: 12px; }
.gate-waiting { color: var(--ink-500); font-size: 12.5px; padding: 8px 0; }
.ai-card { flex: 1; overflow-y: auto; min-height: 160px; }
.ai-placeholder { font-size: 12.5px; color: var(--ink-500); line-height: 2; }
.terminal-card { display: flex; flex-direction: column; height: 330px; flex-shrink: 0; overflow: hidden; }
.terminal-head { padding: 10px 14px 0; }
.node-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.node-tab {
  border: 1px solid var(--ink-100); background: var(--ink-50); border-radius: 999px;
  padding: 4px 12px; font-size: 12px; cursor: pointer; color: var(--ink-700);
  display: flex; align-items: center; gap: 6px; transition: all 0.15s; font-weight: 600;
}
.node-tab:hover { border-color: var(--sun-500); }
.node-tab.active { background: var(--sun-100); border-color: var(--sun-500); color: #92400E; }
.tab-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
</style>

<style>
.flow-running { animation: breathe 1.2s ease-in-out infinite; }
@keyframes breathe { 50% { opacity: 0.5; } }
</style>
