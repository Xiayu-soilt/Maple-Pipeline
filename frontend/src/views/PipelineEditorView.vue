<template>
  <div class="editor">
    <!-- 工具栏 -->
    <div class="editor-toolbar card">
      <div class="toolbar-left">
        <button class="btn btn-sm" @click="$router.push('/pipelines')">← 返回</button>
        <span class="pipe-name-edit">{{ pipeline?.name }}</span>
        <span class="tag">{{ pipeline?.branch }}</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-sm" @click="autoLayout">⊞ 整理布局</button>
        <button class="btn btn-sm" @click="fitView">⛶ 适应画布</button>
        <button class="btn btn-sm" :disabled="advising" @click="getAdvice">{{ advising ? 'AI 分析中…' : '✦ AI 门禁建议' }}</button>
        <button class="btn btn-sm" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        <button class="btn btn-sm btn-primary" @click="run">▶ 运行</button>
      </div>
    </div>

    <div class="editor-body">
      <!-- 节点面板 -->
      <div class="node-panel card">
        <div class="panel-title">节点类型</div>
        <div class="node-panel-scroll">
          <template v-for="g in groupedTypes" :key="g.group">
            <div class="panel-group-title">{{ g.group }}</div>
            <div v-for="[type, meta] in g.types" :key="type" class="node-item"
                 draggable="true" @dragstart="dragType = type" @dragend="dragType = null" @click="addNode(type)">
              <span class="node-item-icon" :style="{ background: meta.color + '18', color: meta.color }">{{ meta.icon }}</span>
              <div>
                <div class="node-item-name">{{ meta.label }}</div>
                <div class="node-item-desc">{{ typeDesc[type] || '' }}</div>
              </div>
            </div>
          </template>
        </div>
        <div class="panel-tip">拖拽到画布任意位置，或点击快速添加</div>
      </div>

      <!-- 画布 -->
      <div class="canvas-wrap card" @dragover.prevent @drop="dropNode">
        <div ref="canvasEl" class="canvas" />
        <div class="canvas-tip">空白处拖拽平移 · 滚轮缩放 · 拖动节点圆点连线</div>
        <div v-if="!pipeline?.dag?.nodes?.length" class="canvas-empty">
          从左侧拖入第一个节点，例如「拉取代码」
        </div>
      </div>

      <!-- 属性面板 -->
      <div class="prop-panel card">
        <div class="panel-title">属性</div>
        <template v-if="selectedNode">
          <div class="prop-field">
            <label class="field-label">节点名称</label>
            <input v-model="selectedNode.name" class="input" @change="syncNode" />
          </div>
          <div class="prop-field">
            <label class="field-label">类型（可切换）</label>
            <select v-model="selectedNode.type" class="select" @change="onTypeChange">
              <option v-for="(meta, t) in NODE_TYPES" :key="t" :value="t">{{ meta.label }}</option>
            </select>
          </div>
          <div class="prop-field">
            <label class="field-label">节点 ID</label>
            <input v-model="selectedNode.id" class="input mono" @change="onIdChange" />
          </div>

          <template v-if="COMMAND_TYPES.includes(selectedNode.type)">
            <div class="prop-field">
              <label class="field-label">执行命令</label>
              <input v-model="selectedNode.config.command" class="input mono" placeholder="pytest / npm run build" @change="syncNode" />
            </div>

            <div class="ai-cmd-box">
              <div class="ai-cmd-head">
                <span class="ai-cmd-head-title">✦ AI 生成命令</span>
                <span class="ai-cmd-head-sub">描述需求，AI 帮你写</span>
              </div>
              <div class="ai-cmd-input-row">
                <input v-model="cmdRequirement" class="input" placeholder="如：跑订单模块接口测试并生成 allure 报告" @keyup.enter="genCommand" />
                <button class="btn btn-sm btn-ai" :disabled="cmdGenerating" @click="genCommand">
                  {{ cmdGenerating ? '生成中…' : '✦ 生成' }}
                </button>
              </div>
            </div>

            <div v-if="cmdRaw && (cmdGenerating || cmdError)" class="ai-cmd-stream">
              <div class="stream-head">
                <span class="stream-dot" /><span class="stream-dot" /><span class="stream-dot" />
                <span class="stream-title">DeepSeek 流式输出</span>
              </div>
              <pre class="stream-body">{{ cmdRaw }}<span v-if="cmdGenerating" class="cursor-blink" /></pre>
            </div>

            <div v-if="cmdResult && !cmdGenerating" class="ai-cmd-result">
              <div class="ai-result-head">
                <span class="ai-result-badge">✦ AI 建议</span>
                <span class="ai-result-node">{{ NODE_TYPES[selectedNode.type]?.label || selectedNode.type }}</span>
                <button class="ai-result-close" title="收起" @click="cmdResult = null">✕</button>
              </div>

              <div class="cmd-block">
                <div class="cmd-block-bar">
                  <span class="cmd-tag-main">▶ 推荐命令</span>
                  <button class="mini-btn" @click="copyText(cmdResult.command, 'main')">
                    {{ copied === 'main' ? '✓ 已复制' : '⧉ 复制' }}
                  </button>
                </div>
                <pre class="cmd-code">{{ cmdResult.command }}</pre>
              </div>

              <div v-if="cmdResult.explanation" class="ai-explain">
                <span>💡</span>
                <span>{{ cmdResult.explanation }}</span>
              </div>

              <div v-if="cmdResult.tips" class="ai-tips">
                <span>⚠</span>
                <span>{{ cmdResult.tips }}</span>
              </div>

              <template v-if="cmdResult.alternatives?.length">
                <div class="alt-title">备选方案</div>
                <div v-for="(alt, i) in cmdResult.alternatives" :key="i" class="cmd-block alt">
                  <div class="cmd-block-bar">
                    <span class="cmd-tag-alt">备选 {{ i + 1 }}</span>
                    <span class="alt-actions">
                      <button class="mini-btn" @click="copyText(alt, `alt-${i}`)">{{ copied === `alt-${i}` ? '✓ 已复制' : '⧉ 复制' }}</button>
                      <button class="mini-btn use" @click="useCommand(alt)">↪ 使用</button>
                    </span>
                  </div>
                  <pre class="cmd-code">{{ alt }}</pre>
                </div>
              </template>

              <div class="ai-cmd-actions">
                <button class="btn btn-sm btn-primary" @click="applyAiCommand">✓ 应用推荐命令</button>
              </div>
            </div>

            <p v-if="cmdError" class="ai-cmd-error">✕ {{ cmdError }}</p>
          </template>

          <template v-if="selectedNode.type === 'gate'">
            <div class="prop-field">
              <label class="field-label">单测通过率阈值（%）</label>
              <input v-model.number="selectedNode.config.pass_rate_min" type="number" class="input" @change="syncNode" />
            </div>
            <div class="prop-field">
              <label class="field-label">覆盖率阈值（%）</label>
              <input v-model.number="selectedNode.config.coverage_min" type="number" class="input" @change="syncNode" />
            </div>
            <div class="prop-field">
              <label class="field-label">安全风险数上限</label>
              <input v-model.number="selectedNode.config.issues_max" type="number" class="input" placeholder="不检查则留空" @change="syncNode" />
            </div>
            <p class="prop-hint">任一指标不达标，门禁失败并阻断下游节点。聚合 单测/接口/UI 测试三类节点的指标。</p>
          </template>

          <template v-if="selectedNode.type === 'deploy'">
            <div class="prop-field">
              <label class="field-label">目标环境</label>
              <select v-model="selectedNode.config.environment" class="select" @change="syncNode">
                <option>staging</option>
                <option>prod</option>
              </select>
            </div>
          </template>

          <template v-if="selectedNode.type === 'approval'">
            <div class="prop-field">
              <label class="field-label">审批人（逗号分隔邮箱）</label>
              <input v-model="selectedNode.config.approvers" class="input" placeholder="qa-lead@example.com" @change="syncNode" />
            </div>
            <p class="prop-hint">演示环境自动审批通过；故障演练时模拟「审批驳回」。</p>
          </template>

          <button class="btn btn-sm btn-danger mt-16" style="width: 100%" @click="removeSelectedNode">删除此节点</button>
        </template>

        <template v-else-if="selectedEdge">
          <p class="prop-hint">已选中一条连线，按 Delete 键或点击下方按钮删除。</p>
          <button class="btn btn-sm btn-danger mt-16" style="width: 100%" @click="removeSelectedEdge">删除连线</button>
        </template>

        <div v-else class="prop-empty">
          <div class="prop-empty-icon">🍁</div>
          点击画布中的节点编辑属性
          <p class="prop-hint">从节点右侧圆点拖出连线；选中后按 Delete 删除。</p>
        </div>
      </div>
    </div>

    <!-- AI 建议弹窗 -->
    <div v-if="advice" class="modal-mask" @click.self="advice = null">
      <div class="card modal">
        <h3>✦ AI 质量门禁建议</h3>
        <p class="advice-text">{{ advice.advice }}</p>
        <div v-for="(r, i) in advice.rules || []" :key="i" class="advice-rule">
          <span class="tag">{{ ruleName(r.metric) }}</span>
          <span class="advice-threshold">≥ {{ r.threshold }}%</span>
          <span class="advice-reason">{{ r.reason }}</span>
        </div>
        <p v-if="advice.risk" class="advice-risk">⚠ {{ advice.risk }}</p>
        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px">
          <button class="btn" @click="advice = null">关闭</button>
          <button class="btn btn-primary" @click="applyAdvice">一键应用到门禁节点</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Graph } from '@antv/x6'
import { api, NODE_TYPES, NODE_GROUPS, COMMAND_TYPES, defaultConfig, ssePost } from '../api.js'

const route = useRoute()
const router = useRouter()
const pipeline = ref(null)
const canvasEl = ref(null)
const selectedNode = ref(null)
const selectedEdge = ref(null)
const dragType = ref(null)
const saving = ref(false)
const advising = ref(false)
const advice = ref(null)
const cmdRequirement = ref('')
const cmdGenerating = ref(false)
const cmdRaw = ref('')
const cmdResult = ref(null)
const cmdError = ref('')
const copied = ref('')

let graph = null

const groupedTypes = computed(() => NODE_GROUPS.map((g) => ({
  group: g,
  types: Object.entries(NODE_TYPES).filter(([, m]) => m.group === g),
})))

const typeDesc = {
  checkout: '克隆仓库、切分支',
  code_lint: 'ruff/eslint 静态检查',
  build: '安装依赖并构建',
  db_migration: 'alembic 数据库变更',
  test: '执行单测/接口测试',
  api_test: 'pytest 接口自动化',
  e2e_test: 'Playwright UI 测试',
  perf_test: 'locust 压测',
  scan: '依赖与代码安全扫描',
  gate: '通过率/覆盖率卡点',
  approval: '发布前人工确认',
  artifact: '构建镜像并推送',
  deploy: '发布到目标环境',
  health_check: '部署后接口冒烟',
  notify: '钉钉/邮件通知',
  custom: '执行自定义脚本',
}

const ruleName = (m) => ({ pass_rate: '通过率', coverage: '覆盖率' }[m] || m)

function nodeAttrs(type) {
  const color = NODE_TYPES[type]?.color || '#78716C'
  return {
    body: { rx: 12, ry: 12, fill: '#fff', stroke: color, strokeWidth: 2, cursor: 'move' },
    title: { refX: 14, refY: 13, fill: '#1C1917', fontSize: 13, fontWeight: '600', textAnchor: 'start' },
    sub: { refX: 14, refY: 33, fill: '#78716C', fontSize: 11, textAnchor: 'start' },
  }
}

function addGraphNode(n) {
  graph.addNode({
    id: n.id,
    x: n.x, y: n.y, width: 168, height: 56,
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'text', selector: 'title' },
      { tagName: 'text', selector: 'sub' },
    ],
    attrs: {
      ...nodeAttrs(n.type),
      title: {
        ...nodeAttrs(n.type).title,
        text: `${NODE_TYPES[n.type]?.icon || ''} ${n.name}`,
        textWrap: { width: -28, height: 20, ellipsis: true },
      },
      sub: {
        ...nodeAttrs(n.type).sub,
        text: NODE_TYPES[n.type]?.label || n.type,
        textWrap: { width: -28, height: 16, ellipsis: true },
      },
    },
    ports: {
      groups: {
        in: { position: 'left', attrs: { circle: { r: 5, magnet: true, stroke: '#A8A29E', fill: '#fff', strokeWidth: 1.5 } } },
        out: { position: 'right', attrs: { circle: { r: 5, magnet: true, stroke: '#F5B301', fill: '#fff', strokeWidth: 1.5 } } },
      },
      items: [{ id: `${n.id}-in`, group: 'in' }, { id: `${n.id}-out`, group: 'out' }],
    },
    data: { nodeId: n.id, type: n.type, name: n.name, config: { ...n.config } },
  })
}

function syncNode() {
  const sn = selectedNode.value
  if (!sn || !graph) return
  const cell = graph.getCellById(sn._origId || sn.id)
  if (!cell) return
  const meta = NODE_TYPES[sn.type] || {}
  cell.attr({
    body: { stroke: meta.color || '#78716C' },
    title: { text: `${meta.icon || ''} ${sn.name}` },
    sub: { text: meta.label || sn.type },
  })
  cell.setData({
    nodeId: sn.id,
    type: sn.type,
    name: sn.name,
    config: { ...sn.config },
  })
}

function onTypeChange() {
  const sn = selectedNode.value
  if (!sn) return
  const keep = COMMAND_TYPES.includes(sn.type) && sn.config?.command
    ? { command: sn.config.command }
    : {}
  sn.config = { ...defaultConfig(sn.type), ...keep }
  syncNode()
}

function onIdChange() {
  const sn = selectedNode.value
  if (!sn || !graph) return
  const newId = (sn.id || '').trim()
  const oldId = sn._origId
  if (newId === oldId) return
  if (!/^[a-zA-Z][\w-]*$/.test(newId)) {
    alert('节点 ID 需以字母开头，只能包含字母、数字、下划线和连字符')
    sn.id = oldId
    return
  }
  if (graph.getCellById(newId)) {
    alert(`节点 ID "${newId}" 已被其他节点占用`)
    sn.id = oldId
    return
  }
  const cell = graph.getCellById(oldId)
  if (!cell) return
  const pos = cell.getPosition()
  const d = cell.getData() || {}
  const conns = graph.getEdges()
    .filter((e) => {
      const s = e.getSourceCellId?.() ?? e.getSource().cell
      const t = e.getTargetCellId?.() ?? e.getTarget().cell
      return s === oldId || t === oldId
    })
    .map((e) => ({
      source: e.getSourceCellId?.() ?? e.getSource().cell,
      target: e.getTargetCellId?.() ?? e.getTarget().cell,
    }))
  graph.removeNode(oldId)
  addGraphNode({ id: newId, name: d.name || newId, type: d.type || 'custom', x: pos.x, y: pos.y, config: d.config || {} })
  conns.forEach((c) => {
    const s = c.source === oldId ? newId : c.source
    const t = c.target === oldId ? newId : c.target
    graph.addEdge({ source: { cell: s, port: `${s}-out` }, target: { cell: t, port: `${t}-in` } })
  })
  sn._origId = newId
}

async function genCommand() {
  const sn = selectedNode.value
  if (!sn || cmdGenerating.value) return
  if (!cmdRequirement.value.trim()) {
    cmdError.value = '请先描述你的需求，例如：跑订单模块接口测试并生成 allure 报告'
    return
  }
  cmdGenerating.value = true
  cmdError.value = ''
  cmdResult.value = null
  cmdRaw.value = ''
  await ssePost('/api/ai/generate-command', {
    node_type: sn.type,
    node_name: sn.name,
    requirement: cmdRequirement.value.trim(),
  }, {
    onChunk: (c) => { cmdRaw.value += c },
    onDone: (full) => {
      try {
        let text = (full || cmdRaw.value).trim()
        if (text.startsWith('```')) {
          text = text.split('```')[1] || text
          if (text.startsWith('json')) text = text.slice(4)
        }
        let parsed
        try { parsed = JSON.parse(text) }
        catch {
          const s = text.indexOf('{'), e = text.lastIndexOf('}')
          parsed = JSON.parse(text.slice(s, e + 1))
        }
        if (!parsed.command) throw new Error('missing command')
        cmdResult.value = parsed
      } catch {
        cmdError.value = 'AI 返回的内容无法解析为命令建议，请重试'
      }
      cmdGenerating.value = false
    },
    onError: (msg) => {
      cmdError.value = `生成失败：${msg}`
      cmdGenerating.value = false
    },
  })
}

function applyAiCommand() {
  const sn = selectedNode.value
  if (!sn || !cmdResult.value?.command) return
  sn.config = { ...sn.config, command: cmdResult.value.command }
  syncNode()
}

function useCommand(cmd) {
  const sn = selectedNode.value
  if (!sn) return
  sn.config = { ...sn.config, command: cmd }
  syncNode()
}

async function copyText(text, key) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = key
  setTimeout(() => { if (copied.value === key) copied.value = '' }, 1500)
}

const NODE_W = 168
const NODE_H = 56
const GAP_X = 26
const GAP_Y = 22

function findFreeSpot() {
  const rects = graph.getNodes().map((n) => {
    const p = n.getPosition()
    return { x: p.x, y: p.y, w: NODE_W, h: NODE_H }
  })
  const overlaps = (x, y) => rects.some((r) =>
    x < r.x + r.w + GAP_X && x + NODE_W + GAP_X > r.x &&
    y < r.y + r.h + GAP_Y && y + NODE_H + GAP_Y > r.y)
  for (let row = 0; row < 20; row++) {
    for (let col = 0; col < 10; col++) {
      const x = 80 + col * (NODE_W + GAP_X)
      const y = 100 + row * (NODE_H + GAP_Y)
      if (!overlaps(x, y)) return { x, y }
    }
  }
  return { x: 80, y: 100 + (rects.length % 20) * (NODE_H + GAP_Y) }
}

function addNode(type, x, y) {
  const ids = graph.getNodes().map((n) => n.id)
  let i = 1
  while (ids.includes(`n${i}`)) i++
  const spot = (x == null) ? findFreeSpot() : { x, y }
  const node = {
    id: `n${i}`,
    name: NODE_TYPES[type]?.label || type,
    type, x: spot.x, y: spot.y,
    config: type === 'gate' ? { pass_rate_min: 100, coverage_min: 80 } : {},
  }
  addGraphNode(node)
  selectNode(node.id)
}

function dropNode(e) {
  if (!dragType.value || !graph) return
  const p = graph.clientToLocal(e.clientX, e.clientY)
  let x = p.x - NODE_W / 2
  let y = p.y - NODE_H / 2
  const rects = graph.getNodes().map((n) => {
    const pos = n.getPosition()
    return { x: pos.x, y: pos.y, w: NODE_W, h: NODE_H }
  })
  const hit = rects.find((r) =>
    x < r.x + r.w + GAP_X && x + NODE_W + GAP_X > r.x &&
    y < r.y + r.h + GAP_Y && y + NODE_H + GAP_Y > r.y)
  if (hit) {
    const spot = findFreeSpot()
    x = spot.x
    y = spot.y
  }
  addNode(dragType.value, x, y)
  dragType.value = null
}

function selectNode(id) {
  const cell = graph.getCellById(id)
  if (!cell) return
  const d = cell.getData()
  const pos = cell.getPosition()
  selectedNode.value = {
    id: cell.id,
    _origId: cell.id,
    ...d,
    config: { ...(d.config || {}) },
    x: pos.x, y: pos.y,
  }
  selectedEdge.value = null
}

function removeSelectedNode() {
  if (!selectedNode.value) return
  graph.removeNode(selectedNode.value.id)
  selectedNode.value = null
}

function removeSelectedEdge() {
  if (!selectedEdge.value) return
  graph.removeEdge(selectedEdge.value.id)
  selectedEdge.value = null
}

function extractDag() {
  const nodes = graph.getNodes().map((cell) => {
    const d = cell.getData() || {}
    const pos = cell.getPosition()
    return {
      id: cell.id, name: d.name || cell.id, type: d.type || 'custom',
      x: pos.x, y: pos.y, config: d.config || {},
    }
  })
  const edges = graph.getEdges().map((e) => ({
    source: typeof e.getSourceCellId === 'function' ? e.getSourceCellId() : e.getSource().cell,
    target: typeof e.getTargetCellId === 'function' ? e.getTargetCellId() : e.getTarget().cell,
  }))
  return { nodes, edges }
}

function detectCycle(nodes, edges) {
  const children = {}
  edges.forEach((e) => { (children[e.source] ||= []).push(e.target) })
  const state = {}
  let cyclic = false
  const dfs = (id) => {
    state[id] = 1
    for (const c of children[id] || []) {
      if (state[c] === 1) { cyclic = true; return }
      if (!state[c]) dfs(c)
    }
    state[id] = 2
  }
  nodes.forEach((n) => { if (!state[n.id]) dfs(n.id) })
  return cyclic
}

function autoLayout() {
  const nodes = graph.getNodes()
  if (!nodes.length) return
  const edges = graph.getEdges().map((e) => ({
    s: typeof e.getSourceCellId === 'function' ? e.getSourceCellId() : e.getSource().cell,
    t: typeof e.getTargetCellId === 'function' ? e.getTargetCellId() : e.getTarget().cell,
  }))
  const depth = {}
  nodes.forEach((n) => { depth[n.id] = 0 })
  for (let i = 0; i < nodes.length; i++) {
    let changed = false
    edges.forEach((e) => {
      if (depth[e.t] < (depth[e.s] ?? 0) + 1) {
        depth[e.t] = (depth[e.s] ?? 0) + 1
        changed = true
      }
    })
    if (!changed) break
  }
  const groups = {}
  nodes.forEach((n) => { (groups[depth[n.id] ?? 0] ||= []).push(n) })
  const colGap = NODE_W + 88
  const rowGap = NODE_H + 54
  Object.entries(groups).forEach(([d, list]) => {
    const x = 80 + Number(d) * colGap
    const startY = 200 - ((list.length - 1) * rowGap) / 2
    list.forEach((n, i) => n.position(x, startY + i * rowGap))
  })
  graph.centerContent()
}

function fitView() {
  if (!graph || !graph.getNodes().length) return
  graph.zoomToFit({ padding: { left: 40, right: 40, top: 40, bottom: 40 }, maxScale: 1 })
  graph.centerContent()
}

async function save(silent = false) {
  const dag = extractDag()
  if (!dag.nodes.length) {
    alert('画布为空，至少需要一个节点才能保存')
    return false
  }
  if (detectCycle(dag.nodes, dag.edges)) {
    alert('检测到循环依赖，DAG 不允许成环，请调整连线')
    return false
  }
  saving.value = true
  try {
    await api.updatePipeline(route.params.id, { dag })
    if (!silent) alert('已保存')
    return true
  } catch (e) {
    alert(`保存失败: ${e.message}`)
    return false
  } finally {
    saving.value = false
  }
}

async function run() {
  const ok = await save(true)
  if (!ok) return
  const run = await api.triggerRun(route.params.id, {
    commit_msg: 'feat: 手动触发流水线', commit_author: 'qa-engineer',
  })
  router.push(`/runs/${run.id}`)
}

async function getAdvice() {
  advising.value = true
  try {
    advice.value = await api.gateAdvice(Number(route.params.id))
  } catch (e) {
    alert(`AI 建议获取失败: ${e.message}`)
  } finally {
    advising.value = false
  }
}

function applyAdvice() {
  const rules = advice.value?.rules || []
  if (!rules.length) return
  const gateNode = graph.getNodes().find((n) => n.getData()?.type === 'gate')
  if (!gateNode) {
    alert('画布中暂无质量门禁节点，请先添加')
    return
  }
  const d = gateNode.getData()
  const config = { ...(d.config || {}) }
  rules.forEach((r) => {
    if (r.metric === 'pass_rate') config.pass_rate_min = r.threshold
    if (r.metric === 'coverage') config.coverage_min = r.threshold
  })
  gateNode.setData({ ...d, config })
  if (selectedNode.value?.id === gateNode.id) {
    selectedNode.value = { ...d, config, ...gateNode.getPosition() }
  }
  advice.value = null
  save(true)
}

function onKey(e) {
  if (e.key !== 'Delete' && e.key !== 'Backspace') return
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
  if (selectedNode.value) removeSelectedNode()
  else if (selectedEdge.value) removeSelectedEdge()
}

onMounted(async () => {
  pipeline.value = await api.pipeline(route.params.id)

  if (graph) { graph.dispose(); graph = null }
  graph = new Graph({
    container: canvasEl.value,
    autoResize: true,
    grid: { size: 14, visible: true, type: 'doubleMesh', args: [
      { color: '#F5F5F4', thickness: 1 },
      { color: '#E7E5E4', thickness: 1, factor: 5 },
    ] },
    panning: { enabled: true, eventTypes: ['leftMouseDown'] },
    mousewheel: { enabled: true, minScale: 0.3, maxScale: 2 },
    connecting: {
      snap: { radius: 32 },
      allowBlank: false,
      allowLoop: false,
      allowMulti: false,
      highlight: true,
      connector: { name: 'rounded' },
      connectionPoint: 'anchor',
      createEdge() {
        return graph.createEdge({
          attrs: { line: { stroke: '#D6D3D1', strokeWidth: 2, targetMarker: { name: 'block', args: { size: 8 } } } },
        })
      },
      validateConnection({ sourceCell, targetCell }) {
        return sourceCell !== targetCell
      },
    },
    highlighting: {
      magnetAvailable: { name: 'stroke', args: { attrs: { stroke: '#F5B301', strokeWidth: 3 } } },
    },
  })

  for (const n of pipeline.value.dag?.nodes || []) addGraphNode(n)
  for (const e of pipeline.value.dag?.edges || []) {
    graph.addEdge({ source: { cell: e.source, port: `${e.source}-out` }, target: { cell: e.target, port: `${e.target}-in` } })
  }

  graph.on('node:click', ({ node }) => selectNode(node.id))
  graph.on('node:change:position', ({ node }) => {
    if (selectedNode.value?.id === node.id) {
      const pos = node.getPosition()
      selectedNode.value.x = pos.x
      selectedNode.value.y = pos.y
    }
  })
  graph.on('edge:click', ({ edge }) => {
    selectedEdge.value = edge
    selectedNode.value = null
    edge.attr('line/stroke', '#F5B301')
  })
  graph.on('blank:click', () => {
    if (selectedEdge.value) {
      const cell = graph.getCellById(selectedEdge.value.id)
      cell?.attr('line/stroke', '#D6D3D1')
    }
    selectedNode.value = null
    selectedEdge.value = null
  })
  if (graph.getNodes().length) fitView()

  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  graph?.dispose()
})
</script>

<style scoped>
.editor { display: flex; flex-direction: column; height: 100%; gap: 14px; }
.editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 18px; flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; gap: 12px; }
.toolbar-right { display: flex; gap: 8px; }
.pipe-name-edit { font-weight: 700; font-size: 14.5px; }
.editor-body { flex: 1; display: flex; gap: 14px; min-height: 0; }
.node-panel { width: 218px; padding: 14px; overflow-y: auto; flex-shrink: 0; }
.panel-title { font-size: 12px; font-weight: 700; color: var(--ink-500); margin-bottom: 12px; letter-spacing: 0.5px; }
.node-item {
  display: flex; gap: 10px; align-items: center; padding: 9px 10px;
  border: 1px solid var(--ink-100); border-radius: 11px; margin-bottom: 8px;
  cursor: grab; transition: all 0.15s; background: #fff;
}
.node-item:hover { border-color: var(--sun-500); box-shadow: 0 2px 8px rgba(245, 179, 1, 0.2); transform: translateY(-1px); }
.node-item-icon {
  width: 34px; height: 34px; border-radius: 9px; display: flex; align-items: center;
  justify-content: center; font-size: 16px; flex-shrink: 0; font-weight: 700;
}
.node-item-name { font-size: 12.5px; font-weight: 600; }
.node-item-desc { font-size: 11px; color: var(--ink-500); margin-top: 1px; }
.panel-tip { font-size: 11px; color: var(--ink-300); text-align: center; margin-top: 10px; }
.canvas-wrap { flex: 1; position: relative; overflow: hidden; min-width: 320px; }
@media (max-width: 1100px) {
  .node-panel { width: 178px; }
  .prop-panel { width: 218px; }
}
.canvas { position: absolute; inset: 0; }
.canvas-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--ink-300); font-size: 14px; pointer-events: none;
}
.canvas-tip {
  position: absolute; right: 14px; bottom: 10px; pointer-events: none;
  font-size: 11px; color: var(--ink-300); background: rgba(255, 255, 255, 0.85);
  padding: 4px 10px; border-radius: 999px; border: 1px solid var(--ink-100);
}
.prop-panel { width: 250px; padding: 16px; overflow-y: auto; flex-shrink: 0; }
.prop-field { margin-bottom: 14px; }
.prop-hint { font-size: 11.5px; color: var(--ink-500); line-height: 1.7; }
.prop-empty { text-align: center; color: var(--ink-500); font-size: 12.5px; padding-top: 30px; }
.prop-empty-icon { font-size: 30px; margin-bottom: 10px; }

/* ---------- AI 生成命令 ---------- */
.ai-cmd-box {
  border: 1px solid #FDE68A;
  background: linear-gradient(180deg, #FFFBEB, #FFFDF5);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 14px;
}
.ai-cmd-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 9px; }
.ai-cmd-head-title { font-size: 12.5px; font-weight: 800; color: #92600A; letter-spacing: 0.2px; }
.ai-cmd-head-sub { font-size: 11px; color: var(--ink-500); }
.ai-cmd-input-row { display: flex; gap: 8px; }
.ai-cmd-input-row .input { flex: 1; min-width: 0; }
.btn-ai {
  background: linear-gradient(135deg, var(--sun-500), var(--sun-400));
  border-color: var(--sun-600);
  color: #422006;
  box-shadow: 0 2px 8px rgba(245, 179, 1, 0.35);
  white-space: nowrap;
}

/* 流式输出：终端风格 */
.ai-cmd-stream {
  border: 1px solid #292524;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 14px;
  background: #171412;
}
.stream-head {
  display: flex; align-items: center; gap: 5px;
  padding: 8px 12px; background: #211D1A; border-bottom: 1px solid #292524;
}
.stream-dot { width: 9px; height: 9px; border-radius: 50%; }
.stream-dot:nth-child(1) { background: #EF4444; }
.stream-dot:nth-child(2) { background: #F59E0B; }
.stream-dot:nth-child(3) { background: #22C55E; }
.stream-title { margin-left: 6px; font-size: 11px; color: #A8A29E; }
.stream-body {
  margin: 0; padding: 10px 12px; max-height: 150px; overflow-y: auto;
  font-family: var(--mono); font-size: 11.5px; line-height: 1.7;
  color: #E7E5E4; white-space: pre-wrap; word-break: break-all;
}

/* 结果卡片 */
.ai-cmd-result {
  border: 1px solid var(--ink-100);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 14px;
  background: #fff;
  box-shadow: 0 2px 10px rgba(28, 25, 23, 0.05);
}
.ai-result-head {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  background: linear-gradient(135deg, rgba(245, 179, 1, 0.16), rgba(245, 179, 1, 0.05));
  border-bottom: 1px solid #FDE68A;
}
.ai-result-badge { font-size: 11.5px; font-weight: 800; color: #92600A; }
.ai-result-node {
  font-size: 11px; padding: 2px 8px; border-radius: 999px;
  background: #fff; border: 1px solid #FDE68A; color: #A16207;
}
.ai-result-close {
  margin-left: auto; border: none; background: none; cursor: pointer;
  color: var(--ink-500); font-size: 12px; padding: 2px 5px; border-radius: 6px;
}
.ai-result-close:hover { background: var(--ink-100); color: var(--ink-900); }

/* 命令块：深色终端 + 琥珀文字，一眼可辨 */
.cmd-block { padding: 10px 12px 12px; }
.cmd-block.alt { padding-top: 8px; }
.cmd-block.alt + .cmd-block.alt { border-top: 1px dashed var(--ink-100); }
.cmd-block-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; }
.cmd-tag-main {
  font-size: 10.5px; font-weight: 800; letter-spacing: 0.5px;
  color: #15803D; background: var(--green-100);
  padding: 2px 9px; border-radius: 999px;
}
.cmd-tag-alt {
  font-size: 10.5px; font-weight: 700;
  color: var(--ink-700); background: var(--ink-100);
  padding: 2px 9px; border-radius: 999px;
}
.cmd-code {
  margin: 0; padding: 10px 12px; border-radius: 9px;
  background: #171412; color: #FDE68A;
  font-family: var(--mono); font-size: 12px; line-height: 1.75;
  white-space: pre-wrap; word-break: break-all;
}
.alt-actions { display: flex; gap: 6px; }
.mini-btn {
  border: 1px solid var(--ink-300); background: #fff; color: var(--ink-700);
  font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 7px;
  cursor: pointer; transition: all 0.15s;
}
.mini-btn:hover { border-color: var(--sun-500); color: #92600A; background: var(--sun-50); }
.mini-btn.use:hover { border-color: var(--green-600); color: #15803D; background: var(--green-100); }

/* 说明 / 警告 */
.ai-explain, .ai-tips {
  display: flex; gap: 8px; align-items: flex-start;
  margin: 0 12px 10px; padding: 8px 10px; border-radius: 9px;
  font-size: 11.5px; line-height: 1.65;
}
.ai-explain { background: #EFF6FF; color: #1D4ED8; }
.ai-tips { background: #FFFBEB; color: #B45309; border-left: 3px solid var(--sun-500); }
.alt-title {
  padding: 6px 12px; font-size: 11px; font-weight: 700;
  color: var(--ink-500); letter-spacing: 0.5px;
}
.ai-cmd-actions { padding: 2px 12px 12px; display: flex; gap: 8px; }
.ai-cmd-actions .btn { flex: 1; justify-content: center; }
.ai-cmd-error {
  margin: -6px 0 14px; font-size: 11.5px; color: var(--red-600);
  background: var(--red-100); padding: 8px 10px; border-radius: 9px; line-height: 1.6;
}
.modal-mask {
  position: fixed; inset: 0; background: rgba(28, 25, 23, 0.4); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal { width: 480px; padding: 24px; }
.modal h3 { font-size: 16px; }
.advice-text { font-size: 13px; color: var(--ink-700); line-height: 1.8; margin-top: 12px; }
.advice-rule {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px;
  background: var(--sun-50); border-radius: 10px; margin-top: 8px; font-size: 12.5px;
}
.advice-threshold { font-weight: 700; font-family: var(--mono); }
.advice-reason { color: var(--ink-500); flex: 1; }
.advice-risk {
  margin-top: 12px; font-size: 12.5px; color: #B45309; background: var(--sun-100);
  padding: 8px 12px; border-radius: 8px; line-height: 1.6;
}
</style>
