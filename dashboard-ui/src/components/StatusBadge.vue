<script setup lang="ts">
defineProps<{
  label: string;
  tone?: "ok" | "warn" | "bad" | "neutral";
}>();
</script>

<template>
  <span class="status-badge" :class="tone || 'neutral'">
    <span class="status-dot"></span>
    {{ label }}
  </span>
</template>
