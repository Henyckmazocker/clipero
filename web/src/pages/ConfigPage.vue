<script setup lang="ts">
import Tab from 'primevue/tab';
import TabList from 'primevue/tablist';
import Tabs from 'primevue/tabs';
import { computed } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();
const pestanas = [
  { v: 'canales', etiqueta: 'Canales', to: '/config/canales' },
  { v: 'marca', etiqueta: 'Marca', to: '/config/marca' },
  { v: 'layouts', etiqueta: 'Layouts', to: '/config/layouts' },
  { v: 'tanda', etiqueta: 'Tanda', to: '/config/tanda' },
  { v: 'claude', etiqueta: 'Claude', to: '/config/claude' },
];
const activa = computed(() => pestanas.find((p) => route.path.startsWith(`/config/${p.v}`))?.v ?? 'canales');
const ir = (v: string | number) => {
  const p = pestanas.find((x) => x.v === String(v));
  if (p && p.v !== activa.value) router.push(p.to);
};
</script>

<template>
  <h1>Configuración</h1>
  <Tabs :value="activa" @update:value="ir">
    <TabList>
      <Tab v-for="p in pestanas" :key="p.v" :value="p.v">{{ p.etiqueta }}</Tab>
    </TabList>
  </Tabs>
  <div class="cuerpo"><RouterView /></div>
</template>

<style scoped>
h1 { margin: 0 0 1rem; font-size: 1.4rem; }
.cuerpo { padding-top: 1.25rem; }
</style>
