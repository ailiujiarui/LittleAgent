<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getJson } from "../api/client";
import type { DriftResponse, DriftRun } from "../api/types";

const runs = ref<DriftRun[]>([]);
const loading = ref(false);
const error = ref("");

onMounted(loadRuns);

async function loadRuns() {
  loading.value = true;
  error.value = "";
  try {
    runs.value = (await getJson<DriftResponse>("/api/drift")).runs;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "请求失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="page-head">
    <div>
      <h2>漂移任务</h2>
      <p>{{ runs.length }} 条记录</p>
    </div>
    <button type="button" class="secondary-button" :disabled="loading" @click="loadRuns">
      {{ loading ? "刷新中" : "刷新" }}
    </button>
  </section>

  <section class="table-panel">
    <div class="table-row table-head">
      <span>状态</span>
      <span>开始时间</span>
      <span>完成时间</span>
      <span>摘要</span>
    </div>
    <div v-for="run in runs" :key="run.id" class="table-row">
      <strong>{{ run.status }}</strong>
      <span>{{ run.started_at }}</span>
      <span>{{ run.finished_at || "未完成" }}</span>
      <span>{{ run.summary }}</span>
    </div>
    <p v-if="!runs.length && !error" class="empty-text">暂无漂移任务</p>
  </section>

  <p v-if="error" class="error-line">{{ error }}</p>
</template>
