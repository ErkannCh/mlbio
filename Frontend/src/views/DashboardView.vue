<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { flApi, type JobStatusResponse, type RunRequest, type RunResult } from '@/api/fl'
import LineChart from '@/components/LineChart.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import ResultTable from '@/components/ResultTable.vue'
import ToastMessage from '@/components/ToastMessage.vue'

const info = ref<{
  dataset: string
  expected_total_size: number
  default_test_size: number
  recommended_fractions: number[]
} | null>(null)

const nClients = ref(3)
const rounds = ref(1)
const epochs = ref(2)
const lr = ref(0.0005)
const testSize = ref(500)

const fractionChoices = ref([
  { v: 1.0, label: '1 / n_clients', enabled: false },
  { v: 0.5, label: '0.5 × (1 / n_clients)', enabled: false },
  { v: 0.1, label: '0.1 × (1 / n_clients)', enabled: true },
])
const customFractionsText = ref('')

const job = ref<JobStatusResponse | null>(null)
const results = computed<RunResult[] | null>(() => job.value?.results ?? null)
const busy = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')

type ScenarioStartedEvent = {
  type: 'scenario_started'
  scenario: number
  scenarios_total: number
  fraction_of_1_over_n_clients: number
  n_clients: number
}
type GlobalMetricsEvent = {
  type: 'global_metrics'
  scenario?: number
  fraction_of_1_over_n_clients?: number
  round: number
  test_accuracy_percent: number
  test_loss: number
}
type ClientMetricsEvent = {
  type: 'client_metrics'
  scenario?: number
  fraction_of_1_over_n_clients?: number
  round: number
  client_id: number
  metrics: {
    client_id: number
    n_samples: number
    epoch_loss: number[]
    epoch_acc?: number[]
    epoch_test_acc?: number[] | null
    epoch_test_loss?: number[] | null
    test_accuracy_percent?: number
    test_loss?: number
    n_test_samples?: number
    duration_s: number
    device: string
  }
}
type JobStatusEvent = { type: 'job_status'; job: JobStatusResponse }
type StreamEvent =
  | ScenarioStartedEvent
  | GlobalMetricsEvent
  | ClientMetricsEvent
  | JobStatusEvent
  | { type: string; [k: string]: unknown }

const scenario = ref<{ idx: number; total: number; fraction: number; nClients: number } | null>(
  null,
)
const backendDevice = ref<string | null>(null)
type GlobalPoint = { round: number; acc: number; loss: number }
type ClientLatest = {
  round: number
  nSamples: number
  epochTestAcc: number[]
  epochTestLoss: number[]
  epochLoss: number[]
  durationS: number
  device: string
}
type ScenarioLiveState = {
  meta: { idx: number; fraction: number; nClients: number } | null
  globalHistory: GlobalPoint[]
  clientsLatest: Record<number, ClientLatest>
}

const scenariosLive = ref<Record<number, ScenarioLiveState>>({})

function getScenarioIdFromEvent(ev: StreamEvent): number | null {
  const id = Number((ev as any).scenario)
  if (Number.isFinite(id)) return id
  return scenario.value?.idx ?? null
}

function getScenarioState(id: number): ScenarioLiveState {
  const existing = scenariosLive.value[id]
  if (existing) return existing
  const created: ScenarioLiveState = { meta: null, globalHistory: [], clientsLatest: {} }
  scenariosLive.value = { ...scenariosLive.value, [id]: created }
  return created
}

const scenarioEntries = computed(() =>
  Object.entries(scenariosLive.value)
    .map(([id, s]) => ({ id: Number(id), ...s }))
    .sort((a, b) => a.id - b.id),
)

function globalAccSeriesFor(s: ScenarioLiveState) {
  return [{ name: 'test acc (%)', values: s.globalHistory.map((x) => x.acc), color: '#34d399' }]
}
function globalLossSeriesFor(s: ScenarioLiveState) {
  return [{ name: 'test loss', values: s.globalHistory.map((x) => x.loss), color: '#60a5fa' }]
}
function showRoundChartsFor(s: ScenarioLiveState) {
  return s.globalHistory.length > 1
}
function clientCardsFor(s: ScenarioLiveState) {
  return Object.entries(s.clientsLatest)
    .map(([id, m]) => ({ id: Number(id), ...m }))
    .sort((a, b) => a.id - b.id)
}
function showEpochChartsFor(s: ScenarioLiveState) {
  return clientCardsFor(s).some((c) => c.epochLoss.length > 1 || c.epochTestAcc.length > 1)
}

function bestInSeries(values: number[]) {
  let best: { value: number; index: number } | null = null
  for (let i = 0; i < values.length; i++) {
    const value = values[i]
    if (value === undefined) continue
    if (!Number.isFinite(value)) continue
    if (!best || value > best.value) best = { value, index: i }
  }
  return best
}

function lastInSeries(values: number[]) {
  for (let i = values.length - 1; i >= 0; i--) {
    const value = values[i]
    if (value === undefined) continue
    if (!Number.isFinite(value)) continue
    return { value, index: i }
  }
  return null
}

function pickAccPoint(values: number[]) {
  return lastInSeries(values) ?? bestInSeries(values)
}

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
  resetLive()
  closeStream()
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

let es: EventSource | null = null
function closeStream() {
  if (es) es.close()
  es = null
}

function resetLive() {
  scenario.value = null
  backendDevice.value = null
  scenariosLive.value = {}
}

function handleStreamEvent(ev: StreamEvent) {
  if (ev.type === 'job_status') {
    job.value = (ev as JobStatusEvent).job
    if (job.value.status === 'succeeded' || job.value.status === 'failed') closeStream()
    return
  }
  if (ev.type === 'scenario_started') {
    const e = ev as ScenarioStartedEvent
    scenario.value = {
      idx: e.scenario,
      total: e.scenarios_total,
      fraction: e.fraction_of_1_over_n_clients,
      nClients: e.n_clients,
    }
    const nextState: ScenarioLiveState = {
      meta: { idx: e.scenario, fraction: e.fraction_of_1_over_n_clients, nClients: e.n_clients },
      globalHistory: [],
      clientsLatest: {},
    }
    scenariosLive.value = { ...scenariosLive.value, [e.scenario]: nextState }
    return
  }
  if (ev.type === 'backend_device') {
    backendDevice.value = String((ev as any).device ?? '')
    return
  }
  if (ev.type === 'global_metrics') {
    const e = ev as GlobalMetricsEvent
    const sid = getScenarioIdFromEvent(ev)
    if (sid === null) return
    const state = getScenarioState(sid)
    const round = Number(e.round)
    const next = state.globalHistory.filter((x) => x.round !== round)
    next.push({ round, acc: Number(e.test_accuracy_percent), loss: Number(e.test_loss) })
    next.sort((a, b) => a.round - b.round)
    const nextState: ScenarioLiveState = { ...state, globalHistory: next }
    scenariosLive.value = { ...scenariosLive.value, [sid]: nextState }
    return
  }
  if (ev.type === 'client_metrics') {
    const e = ev as ClientMetricsEvent
    const sid = getScenarioIdFromEvent(ev)
    if (sid === null) return
    const state = getScenarioState(sid)
    const prev = state.clientsLatest[e.client_id]
    const epochTestAcc = Array.isArray((e.metrics as any).epoch_test_acc)
      ? (e.metrics as any).epoch_test_acc.map(Number)
      : Array.isArray(prev?.epochTestAcc)
        ? prev.epochTestAcc
        : []
    const epochTestLoss = Array.isArray((e.metrics as any).epoch_test_loss)
      ? (e.metrics as any).epoch_test_loss.map(Number)
      : Array.isArray(prev?.epochTestLoss)
        ? prev.epochTestLoss
        : []
    const nextState: ScenarioLiveState = {
      ...state,
      clientsLatest: {
        ...state.clientsLatest,
        [e.client_id]: {
          round: Number(e.round),
          nSamples: Number((e.metrics as any).n_samples ?? 0),
          epochTestAcc,
          epochTestLoss,
          epochLoss: e.metrics.epoch_loss.map(Number),
          durationS: Number(e.metrics.duration_s),
          device: String(e.metrics.device),
        },
      },
    }
    scenariosLive.value = { ...scenariosLive.value, [sid]: nextState }
  }
}

function connectStream(jobId: string) {
  closeStream()
  resetLive()
  try {
    es = new EventSource(`/fl/stream/${jobId}`)
    es.onmessage = (msg) => {
      try {
        handleStreamEvent(JSON.parse(msg.data) as StreamEvent)
      } catch {
        // ignore malformed
      }
    }
    es.onerror = () => {
      closeStream()
      showToast('Live stream error', 'Falling back to polling.')
      poll(jobId)
    }
  } catch (e) {
    closeStream()
    showToast('Live stream error', (e as Error).message)
    poll(jobId)
  }
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
    connectStream(resp.job_id)
  } catch (e) {
    showToast('Cannot start run', (e as Error).message)
  }
}

function exportCsv() {
  if (!results.value) return
  const lines = [
    ['fraction_of_1_over_n_clients', 'n_data_per_client', 'accuracy_percent'].join(','),
    ...results.value.map((r) =>
      [r.fraction_of_1_over_n_clients, r.n_data_per_client, r.accuracy_percent].join(','),
    ),
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

onBeforeUnmount(() => closeStream())
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
            <input
              v-model.number="lr"
              type="number"
              step="0.0001"
              min="0.000001"
              :disabled="busy"
            />
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
              <label
                v-for="c in fractionChoices"
                :key="c.v"
                style="display: flex; gap: 10px; align-items: center"
              >
                <input v-model="c.enabled" type="checkbox" :disabled="busy" style="width: auto" />
                <span class="tag">{{ c.label }}</span>
              </label>
            </div>
            <div class="hint" style="margin-top: 10px">Custom fractions (comma-separated):</div>
            <input v-model="customFractionsText" :disabled="busy" placeholder="e.g. 0.25, 0.05" />
          </div>
        </div>

        <div class="btn-row">
          <button class="btn btn-primary" type="button" @click="start" :disabled="busy">
            Run sweep
          </button>
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
        </div>

        <div v-else class="hint">
          No results yet. Click <span class="kbd">Run sweep</span> to start training.
        </div>
      </div>
    </aside>
  </div>

  <section v-if="job" class="card" style="margin-top: 18px">
    <div class="card-header">
      <h2>Courbes</h2>
    </div>
    <div class="card-body">
      <div v-if="scenarioEntries.length">
        <div
          v-for="s in scenarioEntries"
          :key="s.id"
          style="border: 1px solid var(--stroke); border-radius: 16px; padding: 14px; margin: 12px 0"
        >
          <div class="hint" style="margin-top: 0">
            Scenario <code style="font-family: var(--mono)">{{ s.id + 1 }}</code>
          </div>

          <div v-if="showRoundChartsFor(s)" class="grid-2" style="margin-top: 10px">
            <LineChart title="Accuracy (test) vs rounds" :series="globalAccSeriesFor(s)" />
            <LineChart title="Loss (test) vs rounds" :series="globalLossSeriesFor(s)" />
          </div>

          <div v-if="clientCardsFor(s).length" style="margin-top: 14px">
            <div
              style="
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                gap: 12px;
              "
            >
              <div
                v-for="c in clientCardsFor(s)"
                :key="c.id"
              >
                <div class="hint" style="margin-top: 0">
                  Client <code style="font-family: var(--mono)">{{ c.id }}</code> · round
                  <code style="font-family: var(--mono)">{{ c.round + 1 }}</code> ·
                  n=<code style="font-family: var(--mono)">{{ c.nSamples }}</code> ·
                  <code style="font-family: var(--mono)">{{ c.durationS.toFixed(2) }}s</code> ·
                  {{ c.device }}
                </div>
                <div v-if="showEpochChartsFor(s)" class="grid-1" style="margin-top: 10px">
                  <LineChart
                    title="loss / epochs"
                    :series="[{ name: 'loss', values: c.epochLoss, color: '#f59e0b' }]"
                    :height="90"
                  />
                </div>
                <div class="hint" style="margin-top: 10px">
                  <span v-if="pickAccPoint(c.epochTestAcc)">
                    Accuracy (%) (test):
                    <code style="font-family: var(--mono)"
                      >{{ pickAccPoint(c.epochTestAcc)!.value.toFixed(2) }}%</code
                    >
                    (epoch
                    <code style="font-family: var(--mono)"
                      >{{ pickAccPoint(c.epochTestAcc)!.index + 1 }}</code
                    >)
                  </span>
                  <span v-else>Accuracy (%): n/a</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="hint">Aucune courbe reçue pour le moment.</div>
    </div>
  </section>

  <ToastMessage v-if="toast" :title="toast.title" :message="toast.message" @close="toast = null" />
</template>
