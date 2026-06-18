<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getJson, postJson } from "../api/client";
import type {
  PluginActionResponse,
  PluginListResponse,
  PluginRecord
} from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const mode = ref<"runtime" | "standalone">("standalone");
const plugins = ref<PluginRecord[]>([]);
const loading = ref(false);
const actingPlugin = ref("");
const error = ref("");
const message = ref("");
const confirmOpen = ref(false);
const pluginToDisable = ref<PluginRecord | null>(null);

const totalCount = computed(() => plugins.value.length);
const enabledCount = computed(() => plugins.value.filter((plugin) => plugin.enabled).length);
const failedCount = computed(() => plugins.value.filter((plugin) => plugin.last_error).length);
const modeLabel = computed(() => (mode.value === "runtime" ? "运行时" : "独立控制台"));

onMounted(loadPlugins);

async function loadPlugins() {
  loading.value = true;
  error.value = "";
  try {
    const payload = await getJson<PluginListResponse>("/api/plugins");
    mode.value = payload.mode;
    plugins.value = payload.plugins;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

function sourceLabel(plugin: PluginRecord): string {
  return plugin.source === "builtin" ? "内置" : "工作区";
}

function statusLabel(plugin: PluginRecord): string {
  if (plugin.last_error) {
    return "加载失败";
  }
  if (plugin.loaded) {
    return "已加载";
  }
  return plugin.enabled ? "已启用" : "已禁用";
}

function statusTone(plugin: PluginRecord): string {
  if (plugin.last_error) {
    return "bad";
  }
  if (plugin.loaded) {
    return "ok";
  }
  return plugin.enabled ? "warn" : "neutral";
}

function shortError(errorText: string): string {
  if (errorText.length <= 120) {
    return errorText;
  }
  return `${errorText.slice(0, 120)}...`;
}

async function enablePlugin(plugin: PluginRecord) {
  await runAction(plugin, "enable");
}

function askDisable(plugin: PluginRecord) {
  pluginToDisable.value = plugin;
  confirmOpen.value = true;
}

async function confirmDisable() {
  confirmOpen.value = false;
  if (pluginToDisable.value) {
    await runAction(pluginToDisable.value, "disable");
  }
  pluginToDisable.value = null;
}

function cancelDisable() {
  confirmOpen.value = false;
  pluginToDisable.value = null;
}

async function reloadPlugin(plugin: PluginRecord) {
  await runAction(plugin, "reload");
}

async function runAction(plugin: PluginRecord, action: "enable" | "disable" | "reload") {
  actingPlugin.value = `${plugin.id}:${action}`;
  error.value = "";
  message.value = "";
  try {
    const result = await postJson<PluginActionResponse>(
      `/api/plugins/${plugin.source}/${plugin.name}/${action}`
    );
    upsertPlugin(result.plugin);
    message.value = result.message;
    if (result.requires_restart && !message.value.includes("下次启动")) {
      message.value = "已保存，Agent 下次启动后生效";
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "请求失败";
  } finally {
    actingPlugin.value = "";
  }
}

function upsertPlugin(plugin: PluginRecord) {
  const index = plugins.value.findIndex((item) => item.id === plugin.id);
  if (index >= 0) {
    plugins.value[index] = plugin;
    return;
  }
  plugins.value.push(plugin);
}

function isActing(plugin: PluginRecord, action: string): boolean {
  return actingPlugin.value === `${plugin.id}:${action}`;
}
</script>

<template>
  <section class="page-head">
    <div>
      <h2>插件</h2>
      <p>{{ modeLabel }}</p>
    </div>
    <button type="button" class="secondary-button" :disabled="loading" @click="loadPlugins">
      {{ loading ? "刷新中" : "刷新" }}
    </button>
  </section>

  <section class="metric-grid plugin-metrics">
    <div class="metric-panel">
      <span>插件总数</span>
      <strong>{{ totalCount }}</strong>
    </div>
    <div class="metric-panel">
      <span>已启用</span>
      <strong>{{ enabledCount }}</strong>
    </div>
    <div class="metric-panel">
      <span>加载失败</span>
      <strong>{{ failedCount }}</strong>
    </div>
  </section>

  <p v-if="message" class="success-line">{{ message }}</p>
  <p v-if="error" class="error-line">{{ error }}</p>

  <section class="plugin-list">
    <article v-for="plugin in plugins" :key="plugin.id" class="plugin-row">
      <div class="plugin-main">
        <div>
          <strong>{{ plugin.name }}</strong>
          <span>{{ plugin.id }}</span>
        </div>
        <span class="source-chip">{{ sourceLabel(plugin) }}</span>
        <span class="plugin-status" :class="statusTone(plugin)">
          {{ statusLabel(plugin) }}
        </span>
      </div>

      <div class="plugin-meta">
        <span>工具 {{ plugin.tool_count }}</span>
        <span>事件 {{ plugin.event_count }}</span>
        <span>{{ plugin.updated_at || "未更新" }}</span>
      </div>

      <p v-if="plugin.last_error" class="plugin-error">
        {{ shortError(plugin.last_error) }}
      </p>

      <div class="plugin-actions">
        <button
          v-if="!plugin.enabled"
          type="button"
          class="primary-button"
          :disabled="isActing(plugin, 'enable')"
          @click="enablePlugin(plugin)"
        >
          {{ isActing(plugin, "enable") ? "启用中" : "启用" }}
        </button>
        <button
          v-else
          type="button"
          class="secondary-button"
          :disabled="plugin.locked || isActing(plugin, 'disable')"
          :title="plugin.locked ? '系统插件不可关闭' : ''"
          @click="askDisable(plugin)"
        >
          {{ isActing(plugin, "disable") ? "禁用中" : "禁用" }}
        </button>
        <button
          type="button"
          class="secondary-button"
          :disabled="isActing(plugin, 'reload')"
          @click="reloadPlugin(plugin)"
        >
          {{ isActing(plugin, "reload") ? "重载中" : "重载" }}
        </button>
      </div>
    </article>
    <p v-if="!plugins.length && !error" class="empty-text">暂无插件</p>
  </section>

  <ConfirmDialog
    :open="confirmOpen"
    title="禁用插件"
    :message="`确认禁用 ${pluginToDisable?.name || ''}？`"
    confirm-text="禁用"
    cancel-text="取消"
    @confirm="confirmDisable"
    @cancel="cancelDisable"
  />
</template>
