<script setup lang="ts">
import StatusBadge from "./StatusBadge.vue";

defineProps<{
  navItems: string[];
  activeView: string;
  workspace: string;
  statusLabel: string;
  statusTone: "ok" | "warn" | "bad" | "neutral";
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:activeView": [value: string];
  refresh: [];
}>();
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <h1>小助手控制台</h1>
        <p>{{ workspace }}</p>
      </div>
      <div class="topbar-actions">
        <StatusBadge :label="statusLabel" :tone="statusTone" />
        <button type="button" class="primary-button" @click="emit('refresh')">
          {{ loading ? "刷新中" : "刷新" }}
        </button>
      </div>
    </header>

    <div class="layout">
      <aside class="sidebar" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item"
          type="button"
          class="nav-button"
          :class="{ active: activeView === item }"
          @click="emit('update:activeView', item)"
        >
          {{ item }}
        </button>
      </aside>

      <main class="content">
        <slot></slot>
      </main>
    </div>
  </div>
</template>
