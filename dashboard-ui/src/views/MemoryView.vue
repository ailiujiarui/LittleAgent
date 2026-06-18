<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getJson, postJson } from "../api/client";
import type {
  MemoryFileResponse,
  MemoryFilesResponse,
  SaveMemoryResponse
} from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const files = ref<string[]>([]);
const selectedFile = ref("");
const pendingFile = ref("");
const content = ref("");
const originalContent = ref("");
const loading = ref(false);
const saving = ref(false);
const message = ref("");
const messageTone = ref<"success" | "error" | "">("");
const discardDialogOpen = ref(false);

const dirty = computed(() => selectedFile.value !== "" && content.value !== originalContent.value);

onMounted(async () => {
  await loadFiles();
});

async function loadFiles() {
  loading.value = true;
  message.value = "";
  try {
    const payload = await getJson<MemoryFilesResponse>("/api/memory/files");
    files.value = payload.files;
    if (!selectedFile.value && files.value.length > 0) {
      await selectFile(files.value[0], true);
    }
  } catch (err) {
    showError(err);
  } finally {
    loading.value = false;
  }
}

async function selectFile(name: string, force = false) {
  if (dirty.value && !force) {
    pendingFile.value = name;
    discardDialogOpen.value = true;
    return;
  }

  selectedFile.value = name;
  loading.value = true;
  message.value = "";
  try {
    const payload = await getJson<MemoryFileResponse>(
      `/api/memory/files/${encodeURIComponent(name)}`
    );
    content.value = payload.content;
    originalContent.value = payload.content;
    message.value = `已读取 ${name}`;
    messageTone.value = "success";
  } catch (err) {
    showError(err);
  } finally {
    loading.value = false;
  }
}

async function confirmDiscard() {
  discardDialogOpen.value = false;
  await selectFile(pendingFile.value, true);
  pendingFile.value = "";
}

function cancelDiscard() {
  discardDialogOpen.value = false;
  pendingFile.value = "";
}

async function reloadCurrent() {
  if (selectedFile.value) {
    await selectFile(selectedFile.value, true);
  }
}

async function saveCurrent() {
  if (!selectedFile.value || !dirty.value) {
    return;
  }

  saving.value = true;
  message.value = "";
  try {
    const payload = await postJson<SaveMemoryResponse>(
      `/api/memory/files/${encodeURIComponent(selectedFile.value)}`,
      { content: content.value }
    );
    originalContent.value = content.value;
    message.value = `已保存，备份：${payload.backup}`;
    messageTone.value = "success";
  } catch (err) {
    showError(err);
  } finally {
    saving.value = false;
  }
}

function showError(err: unknown) {
  message.value = err instanceof Error ? err.message : "请求失败";
  messageTone.value = "error";
}
</script>

<template>
  <section class="page-head">
    <div>
      <h2>记忆</h2>
      <p>{{ selectedFile || "未选择文件" }}</p>
    </div>
    <div class="page-actions">
      <button type="button" class="secondary-button" :disabled="!selectedFile || loading" @click="reloadCurrent">
        重新读取
      </button>
      <button type="button" class="primary-button" :disabled="!dirty || saving" @click="saveCurrent">
        {{ saving ? "保存中" : "保存" }}
      </button>
    </div>
  </section>

  <section class="memory-layout">
    <aside class="memory-files">
      <div class="list-head">
        <strong>记忆文件</strong>
        <button type="button" class="ghost-button" :disabled="loading" @click="loadFiles">刷新</button>
      </div>
      <button
        v-for="file in files"
        :key="file"
        type="button"
        class="file-row"
        :class="{ active: selectedFile === file }"
        @click="selectFile(file)"
      >
        {{ file }}
      </button>
    </aside>

    <div class="editor-panel">
      <textarea
        v-model="content"
        class="memory-editor"
        spellcheck="false"
        :disabled="!selectedFile || loading"
      ></textarea>
      <div class="message-row" :class="messageTone">
        <span>{{ message || (dirty ? "有未保存修改" : "已同步") }}</span>
        <strong>{{ dirty ? "未保存" : "已保存" }}</strong>
      </div>
    </div>
  </section>

  <ConfirmDialog
    :open="discardDialogOpen"
    title="放弃未保存修改"
    message="当前记忆文件有未保存修改。"
    confirm-text="放弃"
    cancel-text="返回编辑"
    @confirm="confirmDiscard"
    @cancel="cancelDiscard"
  />
</template>
