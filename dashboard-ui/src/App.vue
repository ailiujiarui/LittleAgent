<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getJson } from "./api/client";
import type { DashboardStatus } from "./api/types";

const navItems = [
  "总览",
  "记忆",
  "插件",
  "会话",
  "运行事件",
  "主动推送",
  "漂移任务"
];

const activeView = ref("总览");
const status = ref<DashboardStatus | null>(null);
const loading = ref(false);
const error = ref("");

const runtimeLabel = computed(() => {
  if (!status.value) {
    return "检查中";
  }
  return status.value.running ? "运行中" : "控制台在线";
});

async function refreshStatus() {
  loading.value = true;
  error.value = "";
  try {
    status.value = await getJson<DashboardStatus>("/api/status");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

onMounted(refreshStatus);
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <h1>小助手控制台</h1>
        <p>{{ status?.workspace || "工作区读取中" }}</p>
      </div>
      <div class="topbar-actions">
        <span class="status-pill" :class="{ online: Boolean(status) }">
          {{ runtimeLabel }}
        </span>
        <button type="button" class="icon-text-button" @click="refreshStatus">
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
          @click="activeView = item"
        >
          {{ item }}
        </button>
      </aside>

      <main class="content">
        <section class="page-head">
          <div>
            <h2>{{ activeView }}</h2>
            <p>{{ status?.workspace || "暂无工作区信息" }}</p>
          </div>
          <span class="view-chip">Vue 控制台</span>
        </section>

        <section class="overview-grid">
          <div class="metric-panel">
            <span>运行状态</span>
            <strong>{{ runtimeLabel }}</strong>
          </div>
          <div class="metric-panel">
            <span>插件</span>
            <strong>待载入</strong>
          </div>
          <div class="metric-panel">
            <span>记忆</span>
            <strong>待载入</strong>
          </div>
        </section>

        <p v-if="error" class="error-line">{{ error }}</p>
      </main>
    </div>
  </div>
</template>
