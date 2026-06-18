<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getJson } from "../api/client";
import type { ProactiveItem, ProactiveResponse } from "../api/types";

const items = ref<ProactiveItem[]>([]);
const loading = ref(false);
const error = ref("");

onMounted(loadItems);

async function loadItems() {
  loading.value = true;
  error.value = "";
  try {
    items.value = (await getJson<ProactiveResponse>("/api/proactive")).items;
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
      <h2>主动推送</h2>
      <p>{{ items.length }} 条记录</p>
    </div>
    <button type="button" class="secondary-button" :disabled="loading" @click="loadItems">
      {{ loading ? "刷新中" : "刷新" }}
    </button>
  </section>

  <section class="list-panel">
    <article v-for="item in items" :key="item.id" class="record-row">
      <strong>{{ item.title || item.item_key }}</strong>
      <span>{{ item.source }} / {{ item.pushed_at ? "已推送" : "已判断" }}</span>
      <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">{{ item.url }}</a>
    </article>
    <p v-if="!items.length && !error" class="empty-text">暂无主动推送</p>
  </section>

  <p v-if="error" class="error-line">{{ error }}</p>
</template>
