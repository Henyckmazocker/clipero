<script setup lang="ts">
import Button from 'primevue/button';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, type Fuente } from '../api';

const route = useRoute();
const router = useRouter();
const fuentes = ref<Fuente[]>([]);
onMounted(async () => { fuentes.value = await api.fuentes().catch(() => []); });

// El estado vive en la query de la URL.
const claves = ['fuente', 'tono', 'formato', 'desde', 'hasta', 'publicado'] as const;
const valor = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '');
const poner = (k: string, v: string) => {
  const q = { ...route.query };
  if (v) q[k] = v; else delete q[k];
  router.replace({ query: q });
};
const activos = computed(() => claves.some((k) => valor(k)));
const limpiar = () => router.replace({ query: {} });
const on = (k: string) => (e: Event) => poner(k, (e.target as HTMLSelectElement | HTMLInputElement).value);
</script>

<template>
  <div class="filtros">
    <label>Fuente
      <select :value="valor('fuente')" @change="on('fuente')($event)">
        <option value="">Todas</option>
        <option v-for="f in fuentes" :key="f.id" :value="f.id">{{ f.nombre }}</option>
      </select>
    </label>
    <label>Tono
      <select :value="valor('tono')" @change="on('tono')($event)">
        <option value="">Todos</option>
        <option value="critica">Crítica</option><option value="positivo">Positivo</option>
        <option value="neutro">Neutro</option>
      </select>
    </label>
    <label>Formato
      <select :value="valor('formato')" @change="on('formato')($event)">
        <option value="">Todos</option>
        <option value="arco">Arco</option><option value="momento">Momento</option>
        <option value="recopilacion">Recopilación</option>
      </select>
    </label>
    <label>Desde <input type="date" :value="valor('desde')" @change="on('desde')($event)" /></label>
    <label>Hasta <input type="date" :value="valor('hasta')" @change="on('hasta')($event)" /></label>
    <label>Publicado
      <select :value="valor('publicado')" @change="on('publicado')($event)">
        <option value="">Todos</option><option value="si">Sí</option><option value="no">No</option>
      </select>
    </label>
    <Button v-if="activos" label="Limpiar" icon="pi pi-filter-slash" text size="small" @click="limpiar" />
  </div>
</template>

<style scoped>
.filtros { display: flex; flex-wrap: wrap; gap: .75rem; align-items: end; margin-bottom: 1.25rem; }
label { display: flex; flex-direction: column; gap: .2rem; font-size: .75rem; opacity: .85; }
select, input { padding: .4rem .5rem; border-radius: 6px; border: 1px solid var(--p-surface-300);
  background: var(--p-surface-0); color: inherit; font: inherit; font-size: .85rem; }
.app-dark select, .app-dark input { background: var(--p-surface-900); border-color: var(--p-surface-700); }
</style>
