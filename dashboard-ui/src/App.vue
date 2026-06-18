<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getJson } from "./api/client";
import type { DashboardStatus } from "./api/types";
import AppShell from "./components/AppShell.vue";
import DriftView from "./views/DriftView.vue";
import EventsView from "./views/EventsView.vue";
import MemoryView from "./views/MemoryView.vue";
import OverviewView from "./views/OverviewView.vue";
import PluginsView from "./views/PluginsView.vue";
import ProactiveView from "./views/ProactiveView.vue";
import SessionsView from "./views/SessionsView.vue";

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

const workspace = computed(() => status.value?.workspace || "工作区读取中");
const statusLabel = computed(() => {
  if (!status.value) {
    return "检查中";
  }
  return status.value.running ? "运行中" : "控制台在线";
});
const statusTone = computed(() => {
  if (error.value) {
    return "bad";
  }
  return status.value?.running ? "ok" : "warn";
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
  <AppShell
    v-model:active-view="activeView"
    :nav-items="navItems"
    :workspace="workspace"
    :status-label="statusLabel"
    :status-tone="statusTone"
    :loading="loading"
    @refresh="refreshStatus"
  >
    <OverviewView v-if="activeView === '总览'" :status="status" :error="error" />
    <MemoryView v-else-if="activeView === '记忆'" />
    <PluginsView v-else-if="activeView === '插件'" />
    <SessionsView v-else-if="activeView === '会话'" />
    <EventsView v-else-if="activeView === '运行事件'" />
    <ProactiveView v-else-if="activeView === '主动推送'" />
    <DriftView v-else />
  </AppShell>
</template>
