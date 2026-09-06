<template>
  <div>
    <div class="list-head">
      <div class="list-head-info">
        <h2>流水线</h2>
        <p>共 {{ pipelines.length }} 条 · 点击卡片进入编排，运行后可查看实时日志与门禁结果</p>
      </div>
      <div style="display: flex; gap: 10px">
        <RouterLink to="/ai"><button class="btn">✦ AI 生成流水线</button></RouterLink>
        <button class="btn btn-primary" @click="showCreate = true">＋ 新建流水线</button>
      </div>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <div v-else class="pipe-grid">
      <div v-for="p in pipelines" :key="p.id" class="card card-pad pipe-card">
        <div class="pipe-card-head">
          <div class="pipe-icon" :style="{ background: typeColor(p) }">⑂</div>
          <div class="pipe-card-title">
            <div class="pipe-name">{{ p.name }}</div>
            <div class="pipe-repo">{{ p.repo || '未配置仓库' }} <span class="tag">{{ p.branch }}</span></div>
          </div>
          <span class="badge" :style="lastRunStyle(p)"><i class="dot" />{{ lastRunLabel(p) }}</span>
        </div>

        <p class="pipe-desc">{{ p.description || '暂无描述' }}</p>

        <div class="pipe-flow">
          <template v-for="(n, i) in p.dag?.nodes || []" :key="n.id">
            <span v-if="i > 0" class="flow-arrow">→</span>
            <span class="flow-node" :style="{ borderColor: NODE_TYPES[n.type]?.color }">
              {{ NODE_TYPES[n.type]?.icon }} {{ n.name }}
            </span>
          </template>
        </div>

        <div class="pipe-actions">
          <button class="btn btn-sm btn-primary" :disabled="running === p.id" @click="openRunDialog(p)">
            {{ running === p.id ? '启动中…' : '▶ 立即运行' }}
          </button>
          <button class="btn btn-sm" @click="$router.push(`/pipelines/${p.id}/edit`)">编排</button>
          <button class="btn btn-sm btn-danger" style="margin-left: auto" @click="remove(p)">删除</button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !pipelines.length" class="card empty">
      <div class="empty-icon">🍁</div>
      还没有流水线，点击右上角新建，或让 AI 帮你生成
    </div>

    <!-- 运行对话框 -->
    <div v-if="runDialog" class="modal-mask" @click.self="runDialog = null">
      <div class="card modal">
        <h3>运行「{{ runDialog.name }}」</h3>
        <div class="mt-16" style="display: flex; flex-direction: column; gap: 14px">
          <div>
            <label class="field-label">提交信息</label>
            <input v-model="runForm.commit_msg" class="input" />
          </div>
          <div>
            <label class="field-label">提交人</label>
            <input v-model="runForm.commit_author" class="input" />
          </div>
          <div>
            <label class="field-label">故障演练（可选，用于演示质量门禁拦截）</label>
            <select v-model="runForm.fail_node_id" class="select">
              <option :value="null">不注入故障</option>
              <option v-for="n in testOrScanNodes" :key="n.id" :value="n.id">
                {{ n.name }}（{{ NODE_TYPES[n.type]?.label || n.type }}）
              </option>
            </select>
            <div v-if="runForm.fail_node_id" style="margin-top: 10px">
              <label class="field-label">演练模式</label>
              <div class="mode-radio">
                <label class="mode-option" :class="{ active: runForm.fail_mode === 'fail' }">
                  <input v-model="runForm.fail_mode" type="radio" value="fail" />
                  <b>节点执行失败</b>
                  <span>该节点模拟执行失败，下游直接被阻断</span>
                </label>
                <label v-if="isTestNodeSelected" class="mode-option" :class="{ active: runForm.fail_mode === 'degraded' }">
                  <input v-model="runForm.fail_mode" type="radio" value="degraded" />
                  <b>覆盖率不达标</b>
                  <span>测试全过但覆盖率 76.8%，由质量门禁拦截部署</span>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px">
          <button class="btn" @click="runDialog = null">取消</button>
          <button class="btn btn-primary" @click="doRun">🚀 启动执行</button>
        </div>
      </div>
    </div>

    <!-- 新建对话框 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="card modal">
        <h3>新建流水线</h3>
        <div class="mt-16" style="display: flex; flex-direction: column; gap: 14px">
          <div>
            <label class="field-label">名称</label>
            <input v-model="createForm.name" class="input" placeholder="例如：order-service · 主干流水线" />
          </div>
          <div>
            <label class="field-label">描述</label>
            <input v-model="createForm.description" class="input" placeholder="一句话说明用途" />
          </div>
          <div>
            <label class="field-label">代码来源</label>
            <div class="source-radio">
              <label class="source-option" :class="{ active: createForm.source_type === 'git' }">
                <input v-model="createForm.source_type" type="radio" value="git" />
                <b>⎇ Git 仓库</b>
                <span>运行时真实 git clone 拉取代码</span>
              </label>
              <label class="source-option" :class="{ active: createForm.source_type === 'upload' }">
                <input v-model="createForm.source_type" type="radio" value="upload" />
                <b>📦 上传本地代码</b>
                <span>zip 压缩包，检出时真实解压</span>
              </label>
            </div>
          </div>
          <div v-if="createForm.source_type === 'git'">
            <label class="field-label">代码仓库</label>
            <input v-model="createForm.repo" class="input" placeholder="https://github.com/user/repo.git" />
          </div>
          <div v-else>
            <label class="field-label">本地代码包（zip，≤50MB）</label>
            <div v-if="uploaded" class="upload-done">
              <span>📦 {{ uploaded.filename }} · {{ uploaded.file_count }} 个文件 · {{ uploaded.size_kb }} KB</span>
              <button class="btn btn-sm" @click="resetUpload">重新选择</button>
            </div>
            <label v-else class="upload-zone" :class="{ busy: uploading }">
              <input type="file" accept=".zip,.py,.txt,.md,.json,.yaml,.yml" hidden @change="onUpload" />
              <span v-if="uploading">上传中…</span>
              <span v-else><b>点击选择文件</b><small>或把 zip 拖到这里（暂不支持拖拽，请点击）</small></span>
            </label>
            <p v-if="uploadError" class="upload-error">✕ {{ uploadError }}</p>
          </div>
        </div>
        <p class="hint mt-16">创建后将进入可视化编排器，添加节点并连线。代码来源之后也可以在编排页修改。</p>
        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" :disabled="!canCreate" @click="create">
            {{ uploading ? '上传中…' : '创建并编排' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, NODE_TYPES, STATUS_META } from '../api.js'

const router = useRouter()
const pipelines = ref([])
const loading = ref(true)
const running = ref(null)
const runDialog = ref(null)
const showCreate = ref(false)
const createForm = ref({ name: '', description: '', repo: '', source_type: 'git', upload_id: 0 })
const uploaded = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const runForm = ref({ commit_msg: 'feat: 新功能提交', commit_author: 'qa-engineer', fail_node_id: null, fail_mode: 'fail' })

const canCreate = computed(() => {
  if (!createForm.value.name) return false
  if (createForm.value.source_type === 'upload') return !!uploaded.value
  return true
})

async function onUpload(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  uploading.value = true
  uploadError.value = ''
  try {
    uploaded.value = await api.uploadFile(file)
    createForm.value.upload_id = uploaded.value.id
  } catch (err) {
    uploadError.value = err.message
    uploaded.value = null
  } finally {
    uploading.value = false
  }
}

function resetUpload() {
  uploaded.value = null
  createForm.value.upload_id = 0
}

const DRILLABLE_EXCLUDE = ['gate', 'notify']
const METRIC_TYPES = ['test', 'api_test', 'e2e_test']
const testOrScanNodes = computed(() =>
  (runDialog.value?.dag?.nodes || []).filter((n) => !DRILLABLE_EXCLUDE.includes(n.type)))
const isTestNodeSelected = computed(() => {
  const n = (runDialog.value?.dag?.nodes || []).find((x) => x.id === runForm.value.fail_node_id)
  return METRIC_TYPES.includes(n?.type)
})

async function load() {
  loading.value = true
  const list = await api.pipelines()
  const runs = await api.runs()
  pipelines.value = list.map((p) => ({
    ...p,
    last_run: runs.find((r) => r.pipeline_id === p.id) || null,
  }))
  loading.value = false
}

const lastRunLabel = (p) =>
  p.last_run ? (STATUS_META[p.last_run.status]?.label || p.last_run.status) : '从未运行'
const lastRunStyle = (p) => {
  const m = p.last_run ? STATUS_META[p.last_run.status] : STATUS_META.pending
  return { color: m.color, background: m.bg }
}
const typeColor = () => ({ background: 'var(--sun-100)', color: 'var(--sun-600)' })

function openRunDialog(p) {
  runForm.value = { commit_msg: 'feat: 新功能提交', commit_author: 'qa-engineer', fail_node_id: null, fail_mode: 'fail' }
  runDialog.value = p
}

async function doRun() {
  const p = runDialog.value
  running.value = p.id
  try {
    const run = await api.triggerRun(p.id, runForm.value)
    router.push(`/runs/${run.id}`)
  } catch (e) {
    alert(e.message)
  } finally {
    running.value = null
    runDialog.value = null
  }
}

async function create() {
  const dag = { nodes: [], edges: [] }
  const payload = { ...createForm.value, branch: 'main', dag }
  if (payload.source_type !== 'upload') {
    payload.upload_id = 0
  }
  const p = await api.createPipeline(payload)
  showCreate.value = false
  uploaded.value = null
  router.push(`/pipelines/${p.id}/edit`)
}

async function remove(p) {
  if (!confirm(`确认删除流水线「${p.name}」？其执行历史也会一并删除。`)) return
  await api.deletePipeline(p.id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.list-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.list-head h2 { font-size: 18px; }
.list-head p { font-size: 12.5px; color: var(--ink-500); margin-top: 4px; }
.pipe-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }
.pipe-card-head { display: flex; align-items: flex-start; gap: 12px; }
.pipe-icon {
  width: 40px; height: 40px; border-radius: 11px; display: flex; align-items: center;
  justify-content: center; font-size: 18px; flex-shrink: 0;
}
.pipe-card-title { flex: 1; min-width: 0; }
.pipe-name { font-weight: 700; font-size: 14.5px; }
.pipe-repo { font-size: 11.5px; color: var(--ink-500); margin-top: 3px; display: flex; gap: 6px; align-items: center; }
.pipe-desc { font-size: 12.5px; color: var(--ink-500); margin: 12px 0; min-height: 18px; }
.pipe-flow { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 16px; }
.flow-node {
  font-size: 11.5px; padding: 3px 9px; border: 1.5px solid; border-radius: 7px;
  background: #fff; font-weight: 600; white-space: nowrap;
}
.flow-arrow { color: var(--ink-300); font-size: 12px; }
.pipe-actions { display: flex; gap: 8px; align-items: center; }
.modal-mask {
  position: fixed; inset: 0; background: rgba(28, 25, 23, 0.4); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal { width: 460px; padding: 24px; }
.modal h3 { font-size: 16px; }
.hint { font-size: 11.5px; color: var(--ink-500); margin-top: 6px; line-height: 1.6; }
.mode-radio { display: flex; flex-direction: column; gap: 8px; }
.mode-option {
  display: flex; flex-direction: column; gap: 2px; padding: 10px 12px;
  border: 1.5px solid var(--ink-100); border-radius: 10px; cursor: pointer; transition: all 0.15s;
}
.mode-option:hover { border-color: var(--sun-500); }
.mode-option.active { border-color: var(--sun-500); background: var(--sun-50); }
.mode-option input { display: none; }
.mode-option b { font-size: 12.5px; }
.mode-option span { font-size: 11.5px; color: var(--ink-500); }

.source-radio { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.source-option {
  display: flex; flex-direction: column; gap: 2px; padding: 10px 12px;
  border: 1.5px solid var(--ink-100); border-radius: 10px; cursor: pointer; transition: all 0.15s;
}
.source-option:hover { border-color: var(--sun-500); }
.source-option.active { border-color: var(--sun-500); background: var(--sun-50); }
.source-option input { display: none; }
.source-option b { font-size: 12.5px; }
.source-option span { font-size: 11.5px; color: var(--ink-500); }

.upload-zone {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
  padding: 22px 12px; border: 1.5px dashed var(--ink-300); border-radius: 10px;
  cursor: pointer; transition: all 0.15s; color: var(--ink-500);
}
.upload-zone:hover { border-color: var(--sun-500); background: var(--sun-50); }
.upload-zone.busy { pointer-events: none; opacity: 0.6; }
.upload-zone b { color: var(--ink-800); font-size: 13px; }
.upload-zone small { font-size: 11px; }
.upload-done {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 12px 14px; background: #F0FDF4; border: 1px solid #BBF7D0; color: #15803D;
  border-radius: 10px; font-size: 12.5px; font-weight: 600;
}
.upload-error { font-size: 12px; color: var(--red-600); margin-top: 8px; }
</style>
