<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { flApi, type JobStatusResponse, type RunRequest, type RunResult } from '@/api/fl'
import ProgressBar from '@/components/ProgressBar.vue'
import ResultTable from '@/components/ResultTable.vue'
import ToastMessage from '@/components/ToastMessage.vue'

const info = ref<{ dataset: string; expected_total_size: number; default_test_size: number; recommended_fractions: number[] } | null>(null)

const nClients = ref(5)
const rounds = ref(1)
const epochs = ref(2)
const lr = ref(0.0005)
const testSize = ref(500)

const fractionChoices = ref([
  { v: 1.0, label: '1 / n_clients', enabled: true },
  { v: 0.5, label: '0.5 × (1 / n_clients)', enabled: false },
  { v: 0.1, label: '0.1 × (1 / n_clients)', enabled: false },
])
const customFractionsText = ref('')

const job = ref<JobStatusResponse | null>(null)
const results = computed<RunResult[] | null>(() => job.value?.results ?? null)
const busy = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')

const toast = ref<{ title: string; message: string } | null>(null)
function showToast(title: string, message: string) {
  toast.value = { title, message }
  window.setTimeout(() => {
    toast.value = null
  }, 7000)
}

const trainSize = computed(() => {
  const total = info.value?.expected_total_size ?? 10015
  return Math.max(1, total - testSize.value)
})

const selectedFractions = computed<number[]>(() => {
  const picked = fractionChoices.value.filter((x) => x.enabled).map((x) => x.v)
  const custom = customFractionsText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n) && n > 0)
  const all = [...picked, ...custom]
  const unique = Array.from(new Set(all))
  unique.sort((a, b) => b - a)
  return unique
})

const previewRows = computed(() => {
  const rows = selectedFractions.value.map((frac) => {
    const nData = Math.max(1, Math.floor((trainSize.value * frac) / nClients.value))
    return { frac, nData }
  })
  return rows
})

function resetJob() {
  job.value = null
}

let pollTimer: number | null = null
async function poll(jobId: string) {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    try {
      const st = await flApi.runStatus(jobId)
      job.value = st
      if (st.status === 'succeeded') {
        if (pollTimer) window.clearInterval(pollTimer)
        pollTimer = null
      }
      if (st.status === 'failed') {
        if (pollTimer) window.clearInterval(pollTimer)
        pollTimer = null
        showToast('Run failed', st.message ?? 'Unknown error')
      }
    } catch (e) {
      if (pollTimer) window.clearInterval(pollTimer)
      pollTimer = null
      showToast('Polling error', (e as Error).message)
    }
  }, 1500)
}

async function start() {
  const payload: RunRequest = {
    n_clients: nClients.value,
    rounds: rounds.value,
    epochs: epochs.value,
    lr: lr.value,
    test_size: testSize.value,
    fractions: selectedFractions.value.length ? selectedFractions.value : [1.0, 0.5, 0.1],
  }
  resetJob()
  try {
    const resp = await flApi.startRun(payload)
    job.value = {
      job_id: resp.job_id,
      status: 'queued',
      created_at: new Date().toISOString(),
      progress: 0,
    }
    await poll(resp.job_id)
  } catch (e) {
    showToast('Cannot start run', (e as Error).message)
  }
}

function exportCsv() {
  if (!results.value) return
  const lines = [
    ['fraction_of_1_over_n_clients', 'n_data_per_client', 'accuracy_percent'].join(','),
    ...results.value.map((r) => [r.fraction_of_1_over_n_clients, r.n_data_per_client, r.accuracy_percent].join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `fl_results_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  try {
    info.value = await flApi.info()
    testSize.value = info.value.default_test_size
  } catch (e) {
    showToast('Backend not reachable', (e as Error).message)
  }
})
</script>

<template>
  <div class="row">
    <section class="card">
      <div class="card-header">
        <h2>Run federated training</h2>
      </div>
      <div class="card-body">
        <div class="grid-2">
          <div class="field">
            <label>
              <span>Clients</span>
              <span class="small">nombre de clients</span>
            </label>
            <input v-model.number="nClients" type="number" min="1" max="50" :disabled="busy" />
          </div>

          <div class="field">
            <label>
              <span>Rounds</span>
              <span class="small">global aggregation étapes</span>
            </label>
            <input v-model.number="rounds" type="number" min="1" max="50" :disabled="busy" />
          </div>

          <div class="field">
            <label>
              <span>Local epochs</span>
              <span class="small">par client</span>
            </label>
            <input v-model.number="epochs" type="number" min="1" max="50" :disabled="busy" />
          </div>

          <div class="field">
            <label>
              <span>Learning rate</span>
              <span class="small">adam</span>
            </label>
            <input v-model.number="lr" type="number" step="0.0001" min="0.000001" :disabled="busy" />
          </div>

          <div class="field">
            <label>
              <span>Test size</span>
              <span class="small">taille du jeu d'évaluation</span>
            </label>
            <input v-model.number="testSize" type="number" min="1" :disabled="busy" />
            <div class="hint">
              Train size ≈ <code style="font-family: var(--mono)">{{ trainSize }}</code> images.
            </div>
          </div>

          <div class="field">
            <label>
              <span>Scenarios</span>
            </label>
            <div style="display: grid; gap: 8px; margin-top: 10px">
              <label v-for="c in fractionChoices" :key="c.v" style="display: flex; gap: 10px; align-items: center">
                <input v-model="c.enabled" type="checkbox" :disabled="busy" style="width: auto" />
                <span class="tag">{{ c.label }}</span>
              </label>
            </div>
            <div class="hint" style="margin-top: 10px">Custom fractions (comma-separated):</div>
            <input v-model="customFractionsText" :disabled="busy" placeholder="e.g. 0.25, 0.05" />
          </div>
        </div>

        <div class="btn-row">
          <button class="btn btn-primary" type="button" @click="start" :disabled="busy">Run sweep</button>
          <button class="btn" type="button" @click="resetJob" :disabled="busy || !job">Clear</button>
          <span v-if="job" class="pill">
            Job <code>{{ job.job_id.slice(0, 8) }}</code> · <span class="tag">{{ job.status }}</span>
          </span>
        </div>

        <div v-if="job" style="margin-top: 14px">
          <ProgressBar :value="job.progress" />
          <div class="hint" style="margin-top: 8px">
            <span v-if="job.message">{{ job.message }}</span>
            <span v-else>Running… this can take a few minutes.</span>
          </div>
        </div>
      </div>
    </section>

    <aside class="card">
      <div class="card-header">
        <h2>Resultats</h2>
      </div>
      <div class="card-body">
        <!-- <table class="table" style="margin-bottom: 14px">
          <thead>
            <tr>
              <th>Fraction</th>
              <th>n_data / client</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in previewRows" :key="r.frac">
              <td><span class="tag">{{ r.frac }} × (1 / n_clients)</span></td>
              <td><code style="font-family: var(--mono)">{{ r.nData }}</code></td>
            </tr>
          </tbody>
        </table> -->

        <div v-if="results && results.length">
          <ResultTable :results="results" />
          <div class="btn-row">
            <button class="btn" type="button" @click="exportCsv">Export CSV</button>
          </div>
        </div>

        <div v-else class="hint">
          No results yet. Click <span class="kbd">Run sweep</span> to start training.
        </div>
      </div>
    </aside>
  </div>

  <ToastMessage
    v-if="toast"
    :title="toast.title"
    :message="toast.message"
    @close="toast = null"
  />
</template>
