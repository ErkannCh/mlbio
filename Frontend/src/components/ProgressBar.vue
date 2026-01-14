<script setup lang="ts">
defineProps<{
  value: number
}>()
</script>

<template>
  <div class="progress" role="progressbar" :aria-valuenow="value" aria-valuemin="0" aria-valuemax="1">
    <div :style="{ width: `${Math.round(value * 100)}%` }" />
  </div>
</template>

