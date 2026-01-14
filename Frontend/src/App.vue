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
          <h1>Federated Learning On Skin Classification</h1>
        </div>
      </div>
    </header>

    <main class="container">
      <router-view />
    </main>
  </div>
</template>
