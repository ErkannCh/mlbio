export type RunRequest = {
  n_clients: number
  rounds: number
  epochs: number
  lr: number
  test_size: number
  fractions: number[]
}

export type RunResult = {
  fraction_of_1_over_n_clients: number
  n_data_per_client: number
  accuracy_percent: number
}

export type StartRunResponse = { job_id: string }

export type JobStatusResponse = {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  progress: number
  message?: string | null
  results?: RunResult[] | null
}

export type InfoResponse = {
  dataset: string
  expected_total_size: number
  default_test_size: number
  recommended_fractions: number[]
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      msg = body?.detail ?? msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }
  return (await res.json()) as T
}

export const flApi = {
  info: () => http<InfoResponse>('/fl/info'),
  startRun: (payload: RunRequest) =>
    http<StartRunResponse>('/fl/run', { method: 'POST', body: JSON.stringify(payload) }),
  runStatus: (jobId: string) => http<JobStatusResponse>(`/fl/run/${jobId}`),
}

