<script setup lang="ts">
defineProps<{
  open: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
}>();

const emit = defineEmits<{
  confirm: [];
  cancel: [];
}>();
</script>

<template>
  <div v-if="open" class="dialog-backdrop" role="presentation">
    <section class="confirm-dialog" role="dialog" aria-modal="true" :aria-label="title">
      <h3>{{ title }}</h3>
      <p>{{ message }}</p>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="emit('cancel')">
          {{ cancelText || "取消" }}
        </button>
        <button type="button" class="primary-button" @click="emit('confirm')">
          {{ confirmText || "确认" }}
        </button>
      </div>
    </section>
  </div>
</template>
