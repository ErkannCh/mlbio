<script setup lang="ts">
import { computed } from 'vue'

type Series = {
  name: string
  values: number[]
  color?: string
}

const props = withDefaults(
  defineProps<{
    title: string
    series: Series[]
    height?: number
  }>(),
  { height: 120 },
)

function isFiniteNumber(n: number) {
  return Number.isFinite(n)
}

const flatValues = computed(() =>
  props.series.flatMap((s) => s.values).filter((n) => isFiniteNumber(n)) as number[],
)

const minY = computed(() => {
  if (!flatValues.value.length) return 0
  return Math.min(...flatValues.value)
})
const maxY = computed(() => {
  if (!flatValues.value.length) return 1
  const m = Math.max(...flatValues.value)
  return m === minY.value ? m + 1 : m
})

function points(values: number[]) {
  const w = 100
  const h = 40
  const n = values.length
  if (!n) return ''
  const denom = Math.max(1, n - 1)
  return values
    .map((v, idx) => {
      const x = (idx / denom) * w
      const vv = isFiniteNumber(v) ? v : minY.value
      const y = h - ((vv - minY.value) / (maxY.value - minY.value)) * h
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function lastValue(values: number[]) {
  for (let i = values.length - 1; i >= 0; i--) {
    const v = values[i]
    if (v !== undefined && isFiniteNumber(v)) return v
  }
  return null
}
</script>

<template>
  <div class="chart-card">
    <div class="chart-title">{{ title }}</div>
    <svg viewBox="0 0 100 40" :height="height" width="100%" preserveAspectRatio="none">
      <line x1="0" y1="40" x2="100" y2="40" stroke="rgba(255,255,255,0.15)" stroke-width="0.4" />
      <line x1="0" y1="0" x2="0" y2="40" stroke="rgba(255,255,255,0.15)" stroke-width="0.4" />
      <polyline
        v-for="(s, i) in series"
        :key="`${s.name}-${i}`"
        :points="points(s.values)"
        :stroke="s.color ?? '#60a5fa'"
        stroke-width="1.2"
        fill="none"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <div class="chart-legend" v-if="series.length">
      <div v-for="(s, i) in series" :key="`${s.name}-legend-${i}`" class="chart-legend-item">
        <span class="dot" :style="{ background: s.color ?? '#60a5fa' }" />
        <span>{{ s.name }}</span>
        <span v-if="lastValue(s.values) !== null" class="val">{{ lastValue(s.values)!.toFixed(4) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.03);
}
.chart-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.92);
}
.chart-legend {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}
.chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}
.val {
  font-family: var(--mono);
  color: rgba(255, 255, 255, 0.9);
}
</style>
