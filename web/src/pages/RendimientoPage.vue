<script setup lang="ts">
import Button from 'primevue/button';
import Chart from 'primevue/chart';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { api, mensajeError, type EstadoMedidor, type Rendimiento } from '../api';

const datos = ref<Rendimiento | null>(null);
const cargando = ref(true);
const error = ref('');
const estado = ref<EstadoMedidor>({ midiendo: false, ultima: null, error: null });
const msgMedir = ref('');
let timer: ReturnType<typeof setInterval> | undefined;

// Filtros en cliente (mismos campos que Clips). Las fechas son las de publicación.
const f = ref({ fuente: '', tono: '', formato: '', desde: '', hasta: '' });
const opciones = (k: 'fuente' | 'tono' | 'formato') =>
  [...new Set((datos.value?.publicados ?? []).map((p) => p[k]).filter(Boolean))].sort();
const filtrados = computed(() => (datos.value?.publicados ?? []).filter((p) =>
  (!f.value.fuente || p.fuente === f.value.fuente) && (!f.value.tono || p.tono === f.value.tono) &&
  (!f.value.formato || p.formato === f.value.formato) && (!f.value.desde || p.fecha >= f.value.desde) &&
  (!f.value.hasta || p.fecha <= f.value.hasta)));
const hayFiltros = computed(() => Object.values(f.value).some(Boolean));
const limpiar = () => { f.value = { fuente: '', tono: '', formato: '', desde: '', hasta: '' }; };

const num = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('es-ES'));
const ultimoSubs = computed(() => datos.value?.canal.suscriptores.at(-1) ?? null);

const marca = () => getComputedStyle(document.documentElement).getPropertyValue('--marca').trim() || '#E0201B';
const PALETA = ['#3b82f6', '#22c55e', '#f59e0b', '#a855f7', '#14b8a6', '#ec4899', '#84cc16', '#f97316'];

const dataSemanas = computed(() => {
  const s = datos.value?.canal.por_semana ?? [];
  return {
    labels: s.map((x) => x.semana),
    datasets: [
      { type: 'bar' as const, label: 'Publicados', data: s.map((x) => x.n), backgroundColor: marca() },
      { type: 'line' as const, label: 'Objetivo (21)', data: s.map((x) => x.objetivo), borderColor: '#9ca3af',
        borderDash: [6, 4], pointRadius: 0 },
    ],
  };
});
const dataCurvas = computed(() => ({
  datasets: filtrados.value.filter((p) => datos.value?.series[p.slug]).map((p, i) => ({
    label: p.slug, borderColor: PALETA[i % PALETA.length], backgroundColor: PALETA[i % PALETA.length],
    data: datos.value!.series[p.slug].map((x) => ({ x: x.dia, y: x.vistas })), tension: 0.2,
  })),
}));
const opcionesCurvas = {
  maintainAspectRatio: false, parsing: false as const,
  scales: { x: { type: 'linear' as const, title: { display: true, text: 'Días desde la publicación' }, ticks: { precision: 0 } },
            y: { beginAtZero: true, title: { display: true, text: 'Vistas' } } },
  plugins: { legend: { labels: { boxWidth: 12 } } },
};
const opcionesSemanas = {
  maintainAspectRatio: false,
  scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
};

const TARJETAS = [
  { clave: 'tono', titulo: 'Por tono' }, { clave: 'fuente', titulo: 'Por fuente' },
  { clave: 'formato', titulo: 'Por formato' }, { clave: 'dow', titulo: 'Por día de la semana' },
] as const;
const DOW = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
const filas = (clave: (typeof TARJETAS)[number]['clave']) => {
  const ag = datos.value?.agregados[clave] ?? {};
  return Object.entries(ag).map(([k, v]) => ({ k, ...v }))
    .sort((a, b) => clave === 'dow' ? DOW.indexOf(a.k) - DOW.indexOf(b.k) : b.media - a.media);
};

async function cargar() {
  error.value = '';
  try { datos.value = await api.rendimiento(); } catch (e) { error.value = mensajeError(e); } finally { cargando.value = false; }
}
async function refrescarEstado() {
  const antes = estado.value.midiendo;
  try { estado.value = await api.estadoMedidor(); } catch { return; }
  if (estado.value.midiendo) arrancarSondeo();
  else {
    pararSondeo();
    if (antes) await cargar();
  }
}
function arrancarSondeo() { if (!timer) timer = setInterval(refrescarEstado, 1500); }
function pararSondeo() { if (timer) { clearInterval(timer); timer = undefined; } }
async function medir() {
  msgMedir.value = '';
  try {
    await api.medir();
    estado.value = { ...estado.value, midiendo: true, error: null };
    arrancarSondeo();
  } catch (e) { msgMedir.value = mensajeError(e); await refrescarEstado(); }
}

onMounted(async () => { await Promise.all([cargar(), refrescarEstado()]); });
onBeforeUnmount(pararSondeo);
</script>

<template>
  <div class="cabecera">
    <h1>Rendimiento</h1>
    <div class="medir">
      <span v-if="estado.midiendo" class="estado"><i class="pi pi-spin pi-spinner" /> Midiendo…</span>
      <span v-else-if="estado.error" class="error">Error al medir: {{ estado.error }}</span>
      <span v-else class="estado">Última medida: {{ estado.ultima ?? 'ninguna' }}</span>
      <Button label="Medir ahora" icon="pi pi-refresh" size="small" :disabled="estado.midiendo" @click="medir" />
    </div>
  </div>
  <p v-if="msgMedir" class="error">{{ msgMedir }}</p>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-else-if="cargando">Cargando…</p>
  <p v-else-if="!datos || !datos.publicados.length" class="vacio">
    Aún no hay shorts publicados: marca uno como «Publicado» en Clips y mide.
  </p>
  <template v-else>
    <div class="totales">
      <div class="total"><span class="n">{{ num(datos.canal.vistas_total) }}</span><span>vistas totales</span></div>
      <div class="total"><span class="n">{{ datos.publicados.length }}</span><span>shorts publicados</span></div>
      <div class="total">
        <span class="n">{{ ultimoSubs ? num(ultimoSubs.n) : '—' }}</span>
        <span>suscriptores{{ ultimoSubs ? ` (${ultimoSubs.fecha})` : ': sin dato' }}</span>
      </div>
    </div>

    <h2>Publicados por semana</h2>
    <div class="grafica corta"><Chart type="bar" :data="dataSemanas" :options="opcionesSemanas" class="chart" /></div>

    <h2>Vistas por día desde la publicación</h2>
    <div class="filtros">
      <label>Fuente <select v-model="f.fuente"><option value="">Todas</option>
        <option v-for="o in opciones('fuente')" :key="o" :value="o">{{ o }}</option></select></label>
      <label>Tono <select v-model="f.tono"><option value="">Todos</option>
        <option v-for="o in opciones('tono')" :key="o" :value="o">{{ o }}</option></select></label>
      <label>Formato <select v-model="f.formato"><option value="">Todos</option>
        <option v-for="o in opciones('formato')" :key="o" :value="o">{{ o }}</option></select></label>
      <label>Desde <input v-model="f.desde" type="date" /></label>
      <label>Hasta <input v-model="f.hasta" type="date" /></label>
      <Button v-if="hayFiltros" label="Limpiar" icon="pi pi-filter-slash" text size="small" @click="limpiar" />
    </div>
    <p v-if="!dataCurvas.datasets.length">Ningún short con medidas cumple los filtros.</p>
    <div v-else class="grafica"><Chart type="line" :data="dataCurvas" :options="opcionesCurvas" class="chart" /></div>

    <h2>Agregados</h2>
    <div class="tarjetas">
      <section v-for="t in TARJETAS" :key="t.clave" class="tarjeta">
        <h3>{{ t.titulo }}</h3>
        <p v-if="!filas(t.clave).length" class="tenue">Sin medidas.</p>
        <table v-else>
          <thead><tr><th></th><th>shorts</th><th>media</th><th>mediana</th></tr></thead>
          <tbody><tr v-for="r in filas(t.clave)" :key="r.k">
            <td>{{ r.k }}</td><td>{{ r.shorts }}</td><td>{{ num(r.media) }}</td><td>{{ num(r.mediana) }}</td>
          </tr></tbody>
        </table>
      </section>
    </div>

    <h2>Publicados</h2>
    <DataTable :value="filtrados" size="small" sort-field="fecha" :sort-order="-1" striped-rows>
      <Column header="">
        <template #body="{ data }"><img v-if="data.thumb" :src="data.thumb" class="mini" :alt="data.slug" loading="lazy" /></template>
      </Column>
      <Column field="slug" header="Short" sortable>
        <template #body="{ data }">
          <a :href="data.url" target="_blank" rel="noopener">{{ data.slug }}</a>
          <i v-if="data.claim" class="pi pi-exclamation-triangle claim" title="Con reclamo (claim)" />
        </template>
      </Column>
      <Column field="fecha" header="Fecha" sortable />
      <Column field="dias" header="Días" sortable />
      <Column field="fuente" header="Fuente" sortable />
      <Column field="tono" header="Tono" sortable />
      <Column field="formato" header="Formato" sortable />
      <Column field="vistas" header="Vistas" sortable><template #body="{ data }">{{ num(data.vistas) }}</template></Column>
      <Column field="likes" header="Likes" sortable><template #body="{ data }">{{ num(data.likes) }}</template></Column>
      <Column field="comentarios" header="Coment." sortable><template #body="{ data }">{{ num(data.comentarios) }}</template></Column>
    </DataTable>
  </template>
</template>

<style scoped>
h1 { margin: 0; }
h2 { font-size: .95rem; opacity: .7; margin: 1.75rem 0 .75rem; }
h3 { font-size: .85rem; margin: 0 0 .5rem; }
.cabecera { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .75rem; margin-bottom: 1rem; }
.medir { display: flex; align-items: center; gap: .75rem; }
.estado { font-size: .85rem; opacity: .8; }
.error { color: #dc2626; }
.vacio, .tenue { opacity: .7; }
.totales { display: flex; flex-wrap: wrap; gap: 1rem; }
.total { display: flex; flex-direction: column; padding: .75rem 1.25rem; border: 1px solid var(--p-surface-200);
  border-radius: 10px; background: var(--p-surface-0); font-size: .8rem; min-width: 10rem; }
.app-dark .total, .app-dark .tarjeta { background: var(--p-surface-900); border-color: var(--p-surface-800); }
.total .n { font-size: 1.6rem; font-weight: 700; }
.grafica { position: relative; height: 22rem; }
.grafica.corta { height: 14rem; }
.chart { height: 100%; }
.filtros { display: flex; flex-wrap: wrap; gap: .75rem; align-items: end; margin-bottom: 1rem; }
.filtros label { display: flex; flex-direction: column; gap: .2rem; font-size: .75rem; opacity: .85; }
select, input { padding: .4rem .5rem; border-radius: 6px; border: 1px solid var(--p-surface-300);
  background: var(--p-surface-0); color: inherit; font: inherit; font-size: .85rem; }
.app-dark select, .app-dark input { background: var(--p-surface-900); border-color: var(--p-surface-700); }
.tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr)); gap: 1rem; }
.tarjeta { padding: 1rem; border: 1px solid var(--p-surface-200); border-radius: 10px; background: var(--p-surface-0); }
table { width: 100%; border-collapse: collapse; font-size: .85rem; }
th { text-align: right; font-weight: 600; opacity: .7; font-size: .75rem; }
td { text-align: right; padding: .15rem 0; }
th:first-child, td:first-child { text-align: left; }
.mini { width: 2.25rem; aspect-ratio: 9 / 16; object-fit: cover; border-radius: 4px; display: block; }
.claim { color: #f59e0b; margin-left: .4rem; }
a { color: inherit; }
</style>
