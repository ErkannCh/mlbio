<script setup lang="ts">
defineProps<{
  title: string
  message: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()
</script>

<template>
  <div class="toast" role="status" aria-live="polite">
    <div>
      <strong>{{ title }}</strong>
      <p>{{ message }}</p>
    </div>
    <button type="button" class="btn btn-ghost" @click="emit('close')">Close</button>
  </div>
</template>

