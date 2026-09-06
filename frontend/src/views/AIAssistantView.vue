<template>
  <div class="ai-page">
    <div class="ai-hero card card-pad">
      <MapleLogo :size="44" />
      <div class="hero-text">
        <h2>AI 流水线工程师</h2>
        <p>用一句话描述你的交付流程，DeepSeek 将生成完整的 DAG 流水线配置，含质量门禁卡点。</p>
      </div>
    </div>

    <div class="card card-pad">
      <label class="field-label">描述你的流水线</label>
      <div class="prompt-row">
        <textarea v-model="prompt" class="textarea" rows="3"
                  placeholder="例如：Python 后端服务的发布流水线，需要拉代码、构建、跑 pytest 单测和安全扫描并行，然后做质量门禁（通过率 100%，覆盖率不低于 75%），最后部署到 staging 环境" />
        <button class="btn btn-primary" style="height: fit-content" :disabled="generating || !prompt.trim()" @click="generate">
          {{ generating ? '生成中…' : '✦ 生成流水线' }}
        </button>
      </div>
      <div class="chips">
        <button v-for="c in samples" :key="c" class="chip" @click="prompt = c">{{ c }}</button>
      </div>
      <p v-if="error" class="error-msg">⚠ {{ error }}</p>
    </div>

    <div v-if="result" class="card card-pad mt-16">
      <div class="card-title">
        <span>生成结果</span>
        <div style="display: flex; gap: 8px">
          <button class="btn btn-sm" @click="result = null">丢弃</button>
          <button class="btn btn-sm btn-primary" :disabled="creating" @click="create">
            {{ creating ? '创建中…' : '✔ 创建并打开编排器' }}
          </button>
        </div>
      </div>
      <div class="gen-name">{{ result.name }}</div>
      <p class="gen-desc">{{ result.description }}</p>
      <div class="gen-flow">
        <template v-for="(n, i) in result.dag.nodes" :key="n.id">
          <div class="gen-col">
            <template v-if="colNodes(i).length > 1">
              <div v-for="cn in colNodes(i)" :key="cn.id" class="flow-node" :style="{ borderColor: NODE_TYPES[cn.type]?.color }">
                {{ NODE_TYPES[cn.type]?.icon }} {{ cn.name }}
              </div>
            </template>
            <div v-else class="flow-node single" :style="{ borderColor: NODE_TYPES[n.type]?.color }">
              {{ NODE_TYPES[n.type]?.icon }} {{ n.name }}
              <div v-if="gateConfig(n)" class="flow-sub">{{ gateConfig(n) }}</div>
            </div>
          </div>
          <span v-if="i < result.dag.nodes.length - 1 && isNewColumn(i)" class="flow-arrow">→</span>
        </template>
      </div>
      <div class="gen-meta">
        <span class="tag">{{ result.dag.nodes.length }} 个节点</span>
        <span class="tag">{{ result.dag.edges.length }} 条依赖</span>
        <span class="tag" v-if="hasGate">含质量门禁</span>
      </div>
    </div>

    <div class="card card-pad mt-16">
      <div class="card-title"><span>AI 能力一览</span></div>
      <div class="ability-grid">
        <div class="ability">
          <div class="ability-icon" style="background:#FEF3C7;color:#B45309">⑂</div>
          <div>
            <div class="ability-name">自然语言生成流水线</div>
            <div class="ability-desc">输入交付流程描述，自动生成可执行的 DAG 配置（本页）</div>
          </div>
        </div>
        <div class="ability">
          <div class="ability-icon" style="background:#FEE2E2;color:#B91C1C">✦</div>
          <div>
            <div class="ability-name">失败日志智能归因</div>
            <div class="ability-desc">执行失败后在详情页一键分析根因，给出修复建议与防回归用例</div>
          </div>
        </div>
        <div class="ability">
          <div class="ability-icon" style="background:#DCFCE7;color:#15803D">⏳</div>
          <div>
            <div class="ability-name">门禁阈值智能建议</div>
            <div class="ability-desc">基于近 10 次执行数据推荐通过率/覆盖率阈值，可一键应用（编排页）</div>
          </div>
        </div>
        <div class="ability">
          <div class="ability-icon" style="background:#E0F2FE;color:#0369A1">📄</div>
          <div>
            <div class="ability-name">执行报告自动生成</div>
            <div class="ability-desc">面向管理层的 Markdown 执行总结，含风险与下一步行动（详情页）</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import MapleLogo from '../components/MapleLogo.vue'
import { api, NODE_TYPES } from '../api.js'

const router = useRouter()
const prompt = ref('')
const generating = ref(false)
const creating = ref(false)
const result = ref(null)
const error = ref('')

const samples = [
  'Python 服务发布流水线：构建、pytest 单测与安全扫描并行、门禁（通过率100% 覆盖率75%）后部署 staging',
  '前端项目流水线：拉取代码、构建、Playwright E2E 测试、门禁后发布生产环境',
  '数据服务流水线：代码检查、单元测试、覆盖率门禁 85%、部署到测试环境',
]

const hasGate = computed(() => result.value?.dag?.nodes?.some((n) => n.type === 'gate'))

function colNodes(i) {
  const nodes = result.value.dag.nodes
  const n = nodes[i]
  return nodes.filter((x) => Math.abs(x.x - n.x) < 100)
}

function isNewColumn(i) {
  const nodes = result.value.dag.nodes
  return i === 0 || Math.abs(nodes[i + 1]?.x - nodes[i]?.x) >= 100
}

function gateConfig(n) {
  if (n.type !== 'gate') return ''
  const parts = []
  if (n.config?.pass_rate_min != null) parts.push(`通过率 ≥ ${n.config.pass_rate_min}%`)
  if (n.config?.coverage_min != null) parts.push(`覆盖率 ≥ ${n.config.coverage_min}%`)
  return parts.join(' · ')
}

async function generate() {
  generating.value = true
  error.value = ''
  result.value = null
  try {
    const resp = await fetch('/api/ai/generate-pipeline', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value }),
    })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${resp.status}`)
    }
    result.value = await resp.json()
  } catch (e) {
    error.value = e.message
  } finally {
    generating.value = false
  }
}

async function create() {
  creating.value = true
  try {
    const p = await api.createPipeline({
      name: result.value.name,
      description: result.value.description || 'AI 生成',
      repo: '',
      branch: 'main',
      dag: result.value.dag,
    })
    router.push(`/pipelines/${p.id}/edit`)
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.ai-page { max-width: 900px; margin: 0 auto; }
.ai-hero { display: flex; gap: 16px; align-items: center; margin-bottom: 16px;
  background: linear-gradient(135deg, #FFFBEB, #fff 60%); }
.hero-text h2 { font-size: 18px; }
.hero-text p { font-size: 13px; color: var(--ink-500); margin-top: 5px; line-height: 1.7; }
.prompt-row { display: flex; gap: 12px; align-items: flex-start; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.chip {
  border: 1px dashed var(--ink-300); background: var(--ink-50); border-radius: 999px;
  padding: 6px 14px; font-size: 12px; color: var(--ink-700); cursor: pointer; transition: all 0.15s;
}
.chip:hover { border-color: var(--sun-500); color: #92400E; background: var(--sun-50); }
.error-msg { color: var(--red-600); font-size: 12.5px; margin-top: 10px; }
.gen-name { font-size: 16px; font-weight: 700; }
.gen-desc { font-size: 12.5px; color: var(--ink-500); margin: 6px 0 16px; }
.gen-flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 16px;
  background: var(--ink-50); border-radius: 12px; }
.gen-col { display: flex; flex-direction: column; gap: 6px; }
.flow-node {
  font-size: 12px; padding: 6px 12px; border: 1.5px solid; border-radius: 9px;
  background: #fff; font-weight: 600; white-space: nowrap;
}
.flow-node.single { padding: 8px 14px; }
.flow-sub { font-size: 10.5px; color: var(--ink-500); font-weight: 500; margin-top: 2px; }
.flow-arrow { color: var(--ink-300); font-size: 14px; }
.gen-meta { display: flex; gap: 8px; margin-top: 14px; }
.ability-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ability { display: flex; gap: 12px; align-items: flex-start; padding: 12px;
  border: 1px solid var(--ink-100); border-radius: 12px; }
.ability-icon { width: 38px; height: 38px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center; font-size: 17px; font-weight: 700; flex-shrink: 0; }
.ability-name { font-size: 13.5px; font-weight: 700; }
.ability-desc { font-size: 12px; color: var(--ink-500); margin-top: 3px; line-height: 1.7; }
</style>
