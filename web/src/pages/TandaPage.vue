<script setup lang="ts">
import Column from 'primevue/column';
import ConfirmDialog from 'primevue/confirmdialog';
import DataTable from 'primevue/datatable';
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api, mensajeError, type RunJson } from '../api';
import RunProgreso from '../components/RunProgreso.vue';
import TandaForm from '../components/TandaForm.vue';

const route = useRoute();
const router = useRouter();
const historial = ref<RunJson[]>([]);
const actual = ref<RunJson | null>(null);
const error = ref('');
const cargado = ref(false);

const idQuery = computed(() => (typeof route.query.run === 'string' ? route.query.run : ''));
// Con ?run manda la URL; sin él, la sesión en curso o la más reciente.
const seleccionado = computed(() => idQuery.value || actual.value?.id || historial.value[0]?.id || '');
const ocupado = computed(() => actual.value !== null);

async function refrescar() {
  try {
    const [h, a] = await Promise.all([api.runs(), api.runActual()]);
    historial.value = h; actual.value = a; error.value = '';
  } catch (e) { error.value = mensajeError(e); }
}
onMounted(async () => { await refrescar(); cargado.value = true; });

function elegir(id: string) { router.replace({ path: '/tanda', query: { run: id } }); }
async function lanzada(id: string) { await refrescar(); elegir(id); }
async function ocupada(id: string | null) { await refrescar(); if (id) elegir(id); }
watch(() => route.query.run, refrescar);

const FECHA = new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'short' });
const fecha = (r: RunJson) => FECHA.format(new Date(r.creado));
const ESTADO: Record<string, string> = { en_curso: 'En curso', ok: 'Terminada', error: 'Con error', detenida: 'Detenida', interrumpida: 'Interrumpida' };
const duracion = (r: RunJson) => {
  const fin = r.terminado ? new Date(r.terminado).getTime() : Date.now();
  const s = Math.max(0, Math.round((fin - new Date(r.creado).getTime()) / 1000));
  return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
};
function parametros(r: RunJson) {
  const p = r.params;
  if (r.tipo === 'retoque') return `${p.slug ?? ''} → ${p.destino ?? ''}`;
  const que = p.vod_url ? 'VOD' : p.fuentes?.length ? p.fuentes.join(', ') : 'todos los canales';
  return `${que} · ${p.clips} clips · ${p.editorial}${p.vod_url ? '' : ` · ${p.dias} d`}`;
}
</script>

<template>
  <ConfirmDialog />
  <h1>Tanda</h1>
  <p v-if="error" class="error">{{ error }}</p>
  <div class="cols">
    <section>
      <TandaForm :ocupado="ocupado" @lanzada="lanzada" @ocupada="ocupada" />
    </section>
    <section>
      <RunProgreso v-if="seleccionado" :id="seleccionado" @cambio="refrescar" />
      <p v-else-if="cargado" class="vacio">Todavía no se ha lanzado ninguna sesión.</p>
    </section>
  </div>

  <h2>Historial</h2>
  <DataTable :value="historial" data-key="id" size="small" selection-mode="single" :selection="historial.find((r) => r.id === seleccionado)"
    @row-click="(e) => elegir(e.data.id)">
    <template #empty>Sin sesiones todavía.</template>
    <Column header="Fecha"><template #body="{ data }">{{ fecha(data) }}</template></Column>
    <Column field="tipo" header="Tipo" />
    <Column header="Estado"><template #body="{ data }">{{ ESTADO[data.estado] ?? data.estado }}</template></Column>
    <Column header="Parámetros"><template #body="{ data }">{{ parametros(data) }}</template></Column>
    <Column header="Shorts"><template #body="{ data }">{{ data.resultado.shorts.length }}</template></Column>
    <Column header="Duración"><template #body="{ data }">{{ duracion(data) }}</template></Column>
  </DataTable>
</template>

<style scoped>
.cols { display: grid; grid-template-columns: minmax(0, 360px) minmax(0, 1fr); gap: 1.5rem; align-items: start; }
.error { color: #dc2626; }
.vacio { opacity: .6; }
h2 { margin-top: 2rem; font-size: 1.1rem; }
</style>
