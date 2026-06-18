<script setup lang="ts">
import type { DashboardStatus } from "../api/types";

const props = defineProps<{
  status: DashboardStatus | null;
  error: string;
}>();

function countConnectedMcp(): number {
  return Object.keys(props.status?.mcp?.connected || {}).length;
}

function countFailedMcp(): number {
  return Object.keys(props.status?.mcp?.failed || {}).length;
}
</script>

<template>
  <section class="page-head">
    <div>
      <h2>总览</h2>
      <p>{{ status?.workspace || "工作区读取中" }}</p>
    </div>
  </section>

  <section class="metric-grid">
    <div class="metric-panel">
      <span>运行状态</span>
      <strong>{{ status?.running ? "运行中" : "控制台在线" }}</strong>
    </div>
    <div class="metric-panel">
      <span>MCP 已连接</span>
      <strong>{{ countConnectedMcp() }}</strong>
    </div>
    <div class="metric-panel">
      <span>MCP 失败</span>
      <strong>{{ countFailedMcp() }}</strong>
    </div>
  </section>

  <p v-if="error" class="error-line">{{ error }}</p>
</template>
