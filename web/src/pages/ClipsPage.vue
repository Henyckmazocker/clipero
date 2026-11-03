<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, mensajeError, type ClipGroup } from '../api';
import ClipCard from '../components/ClipCard.vue';
import ClipDialog from '../components/ClipDialog.vue';
import Filtros from '../components/Filtros.vue';

const route = useRoute();
const grupos = ref<ClipGroup[]>([]);
const cargando = ref(true);
const error = ref('');
const abierto = ref<{ fecha: string; base: string } | null>(null);
const visible = ref(false);

const grupo = computed(() => grupos.value.find((g) => g.fecha === abierto.value?.fecha && g.base === abierto.value?.base) ?? null);
const hayFiltros = computed(() => Object.keys(route.query).length > 0);

async function cargar() {
  error.value = '';
  try {
    const q: Record<string, string> = {};
    for (const [k, v] of Object.entries(route.query)) if (typeof v === 'string') q[k] = v;
    grupos.value = await api.clips(q);
  } catch (e) { error.value = mensajeError(e); } finally { cargando.value = false; }
}
watch(() => route.query, cargar, { immediate: true });

function abrir(g: ClipGroup) { abierto.value = { fecha: g.fecha, base: g.base }; visible.value = true; }
async function refrescar() {
  await cargar();
  if (!grupo.value) visible.value = false;
}
</script>

<template>
  <h1>Clips</h1>
  <Filtros />
  <p v-if="error" class="error">{{ error }}</p>
  <p v-else-if="cargando">Cargando…</p>
  <p v-else-if="!grupos.length && !hayFiltros">Aún no hay shorts en <code>out/</code>: lanza una tanda.</p>
  <p v-else-if="!grupos.length">Ningún clip cumple los filtros.</p>
  <template v-else>
    <section v-for="fecha in [...new Set(grupos.map((g) => g.fecha))]" :key="fecha">
      <h2>{{ fecha }}</h2>
      <div class="rejilla">
        <ClipCard v-for="g in grupos.filter((x) => x.fecha === fecha)" :key="g.fecha + g.base" :grupo="g" @abrir="abrir(g)" />
      </div>
    </section>
  </template>
  <ClipDialog v-model:visible="visible" :grupo="grupo" @cambio="refrescar" />
</template>

<style scoped>
h1 { margin-top: 0; }
h2 { font-size: .95rem; opacity: .7; margin: 1.5rem 0 .75rem; }
.rejilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); gap: 1rem; }
.error { color: #dc2626; }
</style>
