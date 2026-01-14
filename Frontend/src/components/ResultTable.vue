<script setup lang="ts">
import type { RunResult } from '@/api/fl'

defineProps<{
  results: RunResult[]
}>()

function label(frac: number) {
  if (frac === 1) return '1.0 × (1 / n_clients)'
  if (frac === 0.5) return '0.5 × (1 / n_clients)'
  if (frac === 0.1) return '0.1 × (1 / n_clients)'
  return `${frac} × (1 / n_clients)`
}

function tagClass(acc: number) {
  if (acc >= 70) return 'good'
  if (acc >= 40) return 'warn'
  return 'bad'
}
</script>

<template>
  <table class="table">
    <thead>
      <tr>
        <th>Scenario</th>
        <th>n_data / client</th>
        <th>Accuracy</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in results" :key="r.fraction_of_1_over_n_clients">
        <td>
          <span class="tag">{{ label(r.fraction_of_1_over_n_clients) }}</span>
        </td>
        <td><code style="font-family: var(--mono)">{{ r.n_data_per_client }}</code></td>
        <td>
          <span class="tag" :class="tagClass(r.accuracy_percent)">{{ r.accuracy_percent.toFixed(1) }}%</span>
        </td>
      </tr>
    </tbody>
  </table>
</template>

