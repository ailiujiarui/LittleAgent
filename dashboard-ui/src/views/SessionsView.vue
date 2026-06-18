<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getJson } from "../api/client";
import type { SessionSummary, SessionsResponse } from "../api/types";

const sessions = ref<SessionSummary[]>([]);
const loading = ref(false);
const error = ref("");

onMounted(loadSessions);

async function loadSessions() {
  loading.value = true;
  error.value = "";
  try {
    sessions.value = (await getJson<SessionsResponse>("/api/sessions")).sessions;
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
      <h2>会话</h2>
      <p>{{ sessions.length }} 条记录</p>
    </div>
    <button type="button" class="secondary-button" :disabled="loading" @click="loadSessions">
      {{ loading ? "刷新中" : "刷新" }}
    </button>
  </section>

  <section class="table-panel">
    <div class="table-row table-head">
      <span>会话</span>
      <span>渠道</span>
      <span>消息数</span>
      <span>更新时间</span>
    </div>
    <div v-for="session in sessions" :key="session.id" class="table-row">
      <strong>{{ session.id }}</strong>
      <span>{{ session.channel }} / {{ session.chat_id }}</span>
      <span>{{ session.message_count }}</span>
      <span>{{ session.updated_at }}</span>
    </div>
    <p v-if="!sessions.length && !error" class="empty-text">暂无会话</p>
  </section>

  <p v-if="error" class="error-line">{{ error }}</p>
</template>
