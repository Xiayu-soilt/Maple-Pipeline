<template>
  <div>
    <div class="list-head">
      <div class="list-head-info">
        <h2>报告中心</h2>
        <p>共 {{ filtered.length }} 份 · AI 执行报告与失败归因统一归档，点击卡片展开阅读</p>
      </div>
      <div class="report-filters">
        <button v-for="f in filters" :key="f.key" class="btn btn-sm"
                :class="{ 'filter-active': filterType === f.key }" @click="filterType = f.key">
          {{ f.label }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="empty">加载中…</div>

    <div v-else-if="!filtered.length" class="card empty">
      <div class="empty-icon">🍁</div>
      还没有报告 — 运行一条流水线后，在执行详情页点击「AI 执行报告」或「AI 失败归因」，报告会自动归档到这里
    </div>

    <div v-else class="report-list">
      <div v-for="r in filtered" :key="r.run_id" class="card report-card" :class="{ open: openId === r.run_id }">
        <div class="report-row" @click="toggle(r.run_id)">
          <div class="report-main">
            <div class="report-title">
              <span class="badge" :style="statusStyle(r.status)"><i class="dot" />{{ statusLabel(r.status) }}</span>
              <b>{{ r.pipeline_name }}</b>
              <span class="tag">#{{ r.run_id }}</span>
              <span v-if="r.has_report" class="tag tag-report">📄 执行报告</span>
              <span v-if="r.has_analysis" class="tag tag-analysis">✦ 失败归因</span>
            </div>
            <div class="report-sub">
              <span v-if="r.stats?.pass_rate != null">通过率 {{ r.stats.pass_rate }}%</span>
              <span v-if="r.stats?.coverage != null">覆盖率 {{ r.stats.coverage }}%</span>
              <span v-if="r.stats?.duration_ms != null">耗时 {{ fmtDuration(r.stats.duration_ms) }}</span>
              <span class="report-commit">{{ r.commit_msg }} · {{ r.commit_author }}</span>
            </div>
          </div>
          <div class="report-side">
            <span class="report-time">{{ fmtTime(r.finished_at) }}</span>
            <button class="btn btn-sm" @click.stop="$router.push(`/runs/${r.run_id}`)">执行详情</button>
            <span class="report-chevron" :class="{ flip: openId === r.run_id }">▾</span>
          </div>
        </div>

        <div v-if="openId === r.run_id" class="report-body">
          <template v-if="r.has_report">
            <div class="report-section-title">📄 AI 执行报告</div>
            <div class="ai-output md" v-html="renderMd(r.report_md)" />
          </template>
          <template v-if="r.has_analysis">
            <div class="report-section-title">✦ AI 失败归因</div>
            <div class="ai-output md" v-html="renderMd(analysisText(r.ai_analysis))" />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { marked } from 'marked'
import { api, STATUS_META, formatDuration, formatTime } from '../api.js'

const reports = ref([])
const loading = ref(true)
const filterType = ref('all')
const openId = ref(null)

const filters = [
  { key: 'all', label: '全部' },
  { key: 'report', label: '执行报告' },
  { key: 'analysis', label: '失败归因' },
]

const filtered = computed(() => {
  if (filterType.value === 'report') return reports.value.filter((r) => r.has_report)
  if (filterType.value === 'analysis') return reports.value.filter((r) => r.has_analysis)
  return reports.value
})

const statusStyle = (s) => {
  const m = STATUS_META[s] || STATUS_META.pending
  return { color: m.color, background: m.bg }
}
const statusLabel = (s) => STATUS_META[s]?.label || s
const fmtDuration = formatDuration
const fmtTime = formatTime

function renderMd(text) {
  return marked.parse(text || '')
}

function analysisText(a) {
  if (!a) return ''
  if (typeof a === 'string') return a
  return a.analysis || a.summary || JSON.stringify(a, null, 2)
}

function toggle(id) {
  openId.value = openId.value === id ? null : id
}

onMounted(async () => {
  reports.value = await api.reports()
  if (reports.value.length) openId.value = reports.value[0].run_id
  loading.value = false
})
</script>

<style scoped>
.list-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 12px; }
.list-head h2 { font-size: 18px; }
.list-head p { font-size: 12.5px; color: var(--ink-500); margin-top: 4px; }
.report-filters { display: flex; gap: 8px; }
.filter-active { background: var(--sun-100); border-color: var(--sun-500); color: #92400E; }

.report-list { display: flex; flex-direction: column; gap: 12px; }
.report-card { overflow: hidden; transition: box-shadow 0.15s; }
.report-card.open { box-shadow: 0 4px 20px rgba(28, 25, 23, 0.1); }
.report-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; cursor: pointer; gap: 16px;
}
.report-row:hover { background: var(--ink-50); }
.report-main { min-width: 0; flex: 1; }
.report-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.report-title b { font-size: 14.5px; }
.tag-report { background: #E0F2FE; color: #0369A1; }
.tag-analysis { background: #FEF3C7; color: #B45309; }
.report-sub { display: flex; gap: 14px; font-size: 12.5px; color: var(--ink-500); margin-top: 7px; flex-wrap: wrap; }
.report-commit { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.report-side { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.report-time { font-size: 12px; color: var(--ink-500); white-space: nowrap; }
.report-chevron { color: var(--ink-500); transition: transform 0.2s; font-size: 13px; }
.report-chevron.flip { transform: rotate(180deg); }

.report-body { border-top: 1px solid var(--ink-100); padding: 18px 22px 22px; background: var(--ink-50); max-height: 640px; overflow-y: auto; }
.report-section-title {
  font-size: 12px; font-weight: 800; color: var(--ink-700);
  margin: 4px 0 12px; letter-spacing: 0.5px;
}
.report-body .ai-output { background: #fff; border: 1px solid var(--ink-100); border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; }
</style>
