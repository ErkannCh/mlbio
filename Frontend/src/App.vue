<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

const theme = ref<'dark' | 'light'>('dark')

const themeLabel = computed(() => (theme.value === 'dark' ? 'Dark' : 'Light'))

function applyTheme(next: 'dark' | 'light') {
  theme.value = next
  document.documentElement.setAttribute('data-theme', next === 'light' ? 'light' : 'dark')
  localStorage.setItem('theme', next)
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') {
    applyTheme(saved)
    return
  }
  const prefersLight = window.matchMedia?.('(prefers-color-scheme: light)')?.matches
  applyTheme(prefersLight ? 'light' : 'dark')
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <div class="logo" aria-hidden="true" />
          <div>
            <h1>Federated Learning — PySyft</h1>
            <p>HAM10000 · FedAvg · clients with private data</p>
          </div>
        </div>

        <div class="pill">
          <span>API</span>
          <code>/fl</code>
          <span class="kbd">{{ themeLabel }}</span>
          <button
            class="btn btn-ghost"
            type="button"
            @click="applyTheme(theme === 'dark' ? 'light' : 'dark')"
          >
            Toggle theme
          </button>
        </div>
      </div>
    </header>

    <main class="container">
      <router-view />
    </main>
  </div>
</template>

