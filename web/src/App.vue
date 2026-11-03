<script setup lang="ts">
import { onMounted } from 'vue';
import AppShell from './layouts/AppShell.vue';
import { api } from './api';
import { marca } from './marca';

onMounted(async () => {
  try {
    const m = await api.marca();
    marca.value = m;
    if (m.color) document.documentElement.style.setProperty('--marca', m.color);
    document.title = m.nombre ? `${m.nombre} · Clipero` : 'Clipero';
  } catch {
    /* sin marca: se queda el nombre y color por defecto */
  }
});
</script>

<template>
  <AppShell />
</template>
