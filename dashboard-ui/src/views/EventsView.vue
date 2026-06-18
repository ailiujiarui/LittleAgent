<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getJson } from "../api/client";
import type { EventRecord, EventsResponse } from "../api/types";

const events = ref<EventRecord[]>([]);
const loading = ref(false);
const error = ref("");

onMounted(loadEvents);

async function loadEvents() {
  loading.value = true;
  error.value = "";
  try {
    events.value = (await getJson<EventsResponse>("/api/events")).events;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

function titleFor(event: EventRecord): string {
  return event.kind === "tool" ? `工具：${event.tool_name}` : `运行：${event.event_type}`;
}

function detailFor(event: EventRecord): string {
  return event.kind === "tool"
    ? JSON.stringify(event.result)
    : JSON.stringify(event.payload);
}
</script>

<template>
  <section class="page-head">
    <div>
      <h2>运行事件</h2>
      <p>{{ events.length }} 条记录</p>
    </div>
    <button type="button" class="secondary-button" :disabled="loading" @click="loadEvents">
      {{ loading ? "刷新中" : "刷新" }}
    </button>
  </section>

  <section class="list-panel">
    <article v-for="event in events" :key="`${event.kind}-${event.id}`" class="record-row">
      <strong>{{ titleFor(event) }}</strong>
      <span>{{ event.created_at }}</span>
      <code>{{ detailFor(event) }}</code>
    </article>
    <p v-if="!events.length && !error" class="empty-text">暂无运行事件</p>
  </section>

  <p v-if="error" class="error-line">{{ error }}</p>
</template>
