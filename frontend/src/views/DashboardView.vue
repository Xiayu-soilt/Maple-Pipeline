<template>
  <div>
    <div class="grid-4">
      <div v-for="card in cards" :key="card.label" class="card card-pad stat-card">
        <div class="stat-icon" :style="{ background: card.bg, color: card.color }">{{ card.icon }}</div>
        <div>
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </div>
    </div>

    <div class="grid-2 mt-16">
      <div class="card card-pad">
        <div class="card-title">
          <span>近 7 天执行趋势</span>
          <span class="legend">
            <i style="background:#16A34A" />成功
            <i style="background:#DC2626;margin-left:10px" />失败
          </span>
        </div>
        <div ref="trendEl" style="height: 260px" />
      </div>
      <div class="card card-pad">
        <div class="card-title"><span>失败热点节点</span></div>
        <div v-if="!hotNodes.length" class="empty">暂无失败记录，枫叶正红，一切安好</div>
        <div v-else class="hot-list">
          <div v-for="(n, i) in hotNodes" :key="n.name" class="hot-item">
            <span class="hot-rank" :class="`rank-${i + 1}`">{{ i + 1 }}</span>
            <span class="hot-name">{{ n.name }}</span>
            <div class="hot-bar-wrap">
              <div class="hot-bar" :style="{ width: barWidth(n.fail_count) }" />
            </div>
            <span class="hot-count">{{ n.fail_count }} 次</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card mt-16">
      <div class="card-title card-pad" style="padding-bottom: 0">
        <span>最近执行</span>
        <RouterLink to="/pipelines"><button class="btn btn-sm">查看全部流水线</button></RouterLink>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>#</th><th>流水线</th><th>提交</th><th>触发</th><th>状态</th>
            <th>通过率</th><th>覆盖率</th><th>耗时</th><th>完成时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in recent" :key="r.id" class="clickable" @click="$router.push(`/runs/${r.id}`)">
            <td style="color: var(--ink-500)">{{ r.id }}</td>
            <td style="font-weight: 600">{{ r.pipeline_name }}</td>
            <td>
              <div class="commit-msg">{{ r.commit_msg }}</div>
              <div class="commit-author">{{ r.commit_author }}</div>
            </td>
            <td><span class="tag">{{ r.trigger }}</span></td>
            <td><span class="badge" :style="statusStyle(r.status)"><i class="dot" />{{ statusLabel(r.status) }}</span></td>
            <td>{{ r.stats?.pass_rate ?? '-' }}<template v-if="r.stats?.pass_rate != null">%</template></td>
            <td>{{ r.stats?.coverage ?? '-' }}<template v-if="r.stats?.coverage != null">%</template></td>
            <td>{{ fmtDuration(r.stats?.duration_ms) }}</td>
            <td style="color: var(--ink-500)">{{ fmtTime(r.finished_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import { api, STATUS_META, formatDuration, formatTime } from '../api.js'

const data = ref(null)
const trendEl = ref(null)
let chart = null
let timer = null

const cards = computed(() => {
  const c = data.value?.cards || {}
  return [
    { label: '流水线', value: c.pipelines ?? '-', icon: '⑂', color: '#B45309', bg: '#FEF3C7' },
    { label: '累计执行', value: c.runs ?? '-', icon: '▶', color: '#475569', bg: '#F1F5F9' },
    { label: '成功率', value: (c.success_rate ?? '-') + '%', icon: '✓', color: '#15803D', bg: '#DCFCE7' },
    { label: '平均耗时', value: (c.avg_duration_s ?? '-') + 's', icon: '⏱', color: '#7C3AED', bg: '#EDE9FE' },
  ]
})

const recent = computed(() => data.value?.recent || [])
const hotNodes = computed(() => data.value?.hot_nodes || [])

const maxFail = computed(() => Math.max(1, ...hotNodes.value.map((n) => n.fail_count)))
const barWidth = (count) => `${Math.max(8, (count / maxFail.value) * 100)}%`

const statusStyle = (s) => {
  const m = STATUS_META[s] || STATUS_META.pending
  return { color: m.color, background: m.bg }
}
const statusLabel = (s) => STATUS_META[s]?.label || s
const fmtDuration = formatDuration
const fmtTime = formatTime

async function load() {
  try { data.value = await api.dashboard() } catch { /* 后端未启动 */ }
}

function renderChart() {
  if (!trendEl.value || !data.value) return
  if (!chart) chart = echarts.init(trendEl.value)
  const trend = data.value.trend
  chart.setOption({
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trend.map((t) => t.date), axisLine: { lineStyle: { color: '#D6D3D1' } }, axisLabel: { color: '#78716C' } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#F5F5F4' } }, axisLabel: { color: '#78716C' } },
    series: [
      {
        name: '成功', type: 'bar', stack: 'runs', barWidth: 22,
        data: trend.map((t) => t.success), itemStyle: { color: '#16A34A', borderRadius: [0, 0, 0, 0] },
      },
      {
        name: '失败', type: 'bar', stack: 'runs',
        data: trend.map((t) => t.failed), itemStyle: { color: '#DC2626', borderRadius: [4, 4, 0, 0] },
      },
    ],
  })
}

onMounted(async () => {
  await load()
  renderChart()
  timer = setInterval(async () => {
    await load()
    renderChart()
  }, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
  chart?.dispose()
})
</script>

<style scoped>
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-icon {
  width: 44px; height: 44px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.stat-value { font-size: 24px; font-weight: 800; line-height: 1.2; }
.stat-label { font-size: 12px; color: var(--ink-500); margin-top: 2px; }
.legend { font-size: 12px; color: var(--ink-500); font-weight: 400; }
.legend i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
.commit-msg { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.commit-author { font-size: 11.5px; color: var(--ink-500); }
.hot-list { display: flex; flex-direction: column; gap: 14px; padding-top: 6px; }
.hot-item { display: flex; align-items: center; gap: 12px; }
.hot-rank {
  width: 22px; height: 22px; border-radius: 7px; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; background: var(--ink-100); color: var(--ink-500);
}
.rank-1 { background: #FEE2E2; color: #B91C1C; }
.rank-2 { background: #FEF3C7; color: #B45309; }
.rank-3 { background: #F5F5F4; color: #57534E; }
.hot-name { width: 130px; font-size: 13px; font-weight: 600; }
.hot-bar-wrap { flex: 1; height: 8px; background: var(--ink-100); border-radius: 4px; overflow: hidden; }
.hot-bar { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #F87171, #DC2626); }
.hot-count { width: 44px; text-align: right; font-size: 12px; color: var(--ink-500); font-family: var(--mono); }
</style>
