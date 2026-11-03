<script setup lang="ts">
import Button from 'primevue/button';
import Panel from 'primevue/panel';
import { useConfirm } from 'primevue/useconfirm';
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api, ApiError, mensajeError, type Evento, type RunJson } from '../api';

const props = defineProps<{ id: string }>();
const emit = defineEmits<{ cambio: [run: RunJson] }>();
const confirmar = useConfirm();

// Las mismas fases que sesiones.py (FASES); un retoque solo enseña las tres últimas que usa.
const FASES_TANDA = ['metricas', 'vods', 'ingesta', 'transcripcion', 'guion', 'render', 'limpieza'];
const FASES_RETOQUE = ['transcripcion', 'guion', 'render'];
const ETIQUETA: Record<string, string> = {
  metricas: 'Métricas', vods: 'VODs', ingesta: 'Ingesta', transcripcion: 'Transcripción',
  guion: 'Guion', render: 'Render', limpieza: 'Limpieza',
};
const ESTADO: Record<string, string> = {
  en_curso: 'En curso', ok: 'Terminada', error: 'Con error', detenida: 'Detenida', interrumpida: 'Interrumpida',
};

const run = ref<RunJson | null>(null);
const eventos = ref<Evento[]>([]);
const error = ref('');
const ahora = ref(Date.now());
const deteniendo = ref(false);
let cursor = 0;
let token = 0;
let sondeo: ReturnType<typeof setTimeout> | undefined;
let reloj: ReturnType<typeof setInterval> | undefined;

const fases = computed(() => (run.value?.tipo === 'retoque' ? FASES_RETOQUE : FASES_TANDA));
const actual = computed(() => (run.value?.fase ? fases.value.indexOf(run.value.fase) : -1));
const paso = (i: number) => (run.value?.estado === 'ok' ? 'hecha' : i < actual.value ? 'hecha' : i === actual.value ? 'actual' : 'pendiente');

const duracion = computed(() => {
  const r = run.value;
  if (!r) return '';
  const fin = r.terminado ? new Date(r.terminado).getTime() : ahora.value;
  const s = Math.max(0, Math.round((fin - new Date(r.creado).getTime()) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h} h ${m} min` : m ? `${m} min ${x} s` : `${x} s`;
});

function parar() {
  token++;
  clearTimeout(sondeo); sondeo = undefined;
  clearInterval(reloj); reloj = undefined;
}

async function leer(mio: number) {
  try {
    const l = await api.run(props.id, cursor);
    if (mio !== token) return;
    error.value = '';
    eventos.value.push(...l.eventos);
    cursor = l.siguiente;
    const cambio = run.value?.estado !== l.run.estado;
    run.value = l.run;
    if (cambio) emit('cambio', l.run);
    if (l.run.estado !== 'en_curso') { clearInterval(reloj); reloj = undefined; deteniendo.value = false; return; }
  } catch (e) {
    if (mio !== token) return;
    error.value = mensajeError(e);
    if (e instanceof ApiError && e.status === 404) { clearInterval(reloj); reloj = undefined; return; }
  }
  sondeo = setTimeout(() => leer(mio), 1500);
}

watch(() => props.id, () => {
  parar();
  run.value = null; eventos.value = []; cursor = 0; error.value = ''; deteniendo.value = false;
  if (!props.id) return;
  reloj = setInterval(() => { ahora.value = Date.now(); }, 1000);
  leer(token);
}, { immediate: true });
onBeforeUnmount(parar);

function pedirDetener() {
  confirmar.require({
    header: 'Detener la sesión', icon: 'pi pi-exclamation-triangle', acceptLabel: 'Detener', rejectLabel: 'Seguir',
    acceptProps: { severity: 'danger' }, rejectProps: { severity: 'secondary', text: true },
    message: 'Se corta lo que esté haciendo la sesión. Lo que ya se haya renderizado se queda en Clips.',
    accept: async () => {
      deteniendo.value = true;
      try { await api.detener(props.id); } catch (e) { error.value = mensajeError(e); deteniendo.value = false; }
    },
  });
}
</script>

<template>
  <section v-if="run" class="run">
    <header class="cab">
      <h2>{{ run.tipo === 'tanda' ? 'Tanda' : 'Retoque' }} <small>{{ run.id }}</small></h2>
      <span class="estado" :class="run.estado">{{ ESTADO[run.estado] ?? run.estado }}</span>
      <span class="dur"><i class="pi pi-clock" /> {{ duracion }}</span>
      <Button v-if="run.estado === 'en_curso'" label="Detener" icon="pi pi-stop" severity="danger" size="small"
        :loading="deteniendo" @click="pedirDetener" />
    </header>

    <ol class="pasos">
      <li v-for="(f, i) in fases" :key="f" :class="paso(i)">
        <i class="pi" :class="paso(i) === 'hecha' ? 'pi-check-circle' : paso(i) === 'actual' && run.estado === 'en_curso' ? 'pi-spin pi-spinner' : 'pi-circle'" />
        {{ ETIQUETA[f] ?? f }}
      </li>
    </ol>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="run.estado !== 'en_curso'" class="fin">
      <p v-if="run.canal_creado">Canal añadido: {{ run.canal_creado.nombre }}.</p>
      <p v-if="run.resultado.coste_usd != null">Coste: {{ run.resultado.coste_usd.toFixed(2) }} USD</p>
      <p v-if="run.resultado.error" class="error">{{ run.resultado.error }}</p>
      <p v-if="!run.resultado.shorts.length">Sin shorts nuevos.</p>
      <ul v-else class="shorts">
        <li v-for="s in run.resultado.shorts" :key="s.fecha + s.slug">
          <RouterLink to="/clips">{{ s.slug }}</RouterLink> <small>{{ s.fecha }}</small>
        </li>
      </ul>
    </div>

    <Panel :header="`Transcript (${eventos.length})`" toggleable collapsed class="transcript">
      <p v-if="!eventos.length" class="vacio">Todavía no hay eventos.</p>
      <template v-for="e in eventos" :key="e.i">
        <p v-if="e.tipo === 'texto'" class="ev texto">{{ e.texto }}</p>
        <p v-else-if="e.tipo === 'herramienta'" class="ev herr"><i class="pi pi-wrench" /> <b>{{ e.nombre }}</b> {{ e.resumen }}</p>
        <pre v-else-if="e.tipo === 'salida'" class="ev salida" :class="{ mala: e.error }">{{ e.texto }}</pre>
        <p v-else-if="e.tipo === 'denegado'" class="ev denegado"><i class="pi pi-ban" /> Denegado: {{ e.nombre }} — {{ e.motivo }}</p>
        <p v-else-if="e.tipo === 'fase'" class="ev fase">→ fase {{ e.fase }}</p>
        <p v-else-if="e.tipo === 'fin'" class="ev fase">Fin: {{ e.estado }}</p>
      </template>
    </Panel>
  </section>
  <p v-else-if="error" class="error">{{ error }}</p>
</template>

<style scoped>
.run { display: flex; flex-direction: column; gap: .9rem; }
.cab { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.cab h2 { margin: 0; font-size: 1.1rem; }
.cab h2 small { font-weight: 400; opacity: .6; font-size: .75rem; }
.dur { margin-left: auto; font-size: .85rem; opacity: .75; }
.estado { padding: .1rem .55rem; border-radius: 999px; font-size: .75rem; background: var(--p-surface-200); }
.app-dark .estado { background: var(--p-surface-700); }
.estado.en_curso { background: var(--marca); color: #fff; }
.estado.ok { background: #16a34a; color: #fff; }
.estado.error { background: #dc2626; color: #fff; }
.pasos { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }
.pasos li { display: flex; align-items: center; gap: .4rem; padding: .35rem .7rem; border-radius: 8px;
  border: 1px solid var(--p-surface-300); font-size: .85rem; opacity: .55; }
.app-dark .pasos li { border-color: var(--p-surface-700); }
.pasos li.hecha { opacity: 1; color: #16a34a; }
.pasos li.actual { opacity: 1; border-color: var(--marca); color: var(--marca); font-weight: 600; }
.fin p { margin: .15rem 0; }
.shorts { margin: .25rem 0; padding-left: 1.2rem; }
.error { color: #dc2626; }
.vacio { opacity: .6; margin: 0; }
.ev { margin: .25rem 0; font-size: .85rem; }
.ev.herr { opacity: .8; font-family: monospace; word-break: break-all; }
.ev.fase { opacity: .6; font-style: italic; }
.ev.denegado { background: #fef3c7; color: #92400e; padding: .3rem .5rem; border-radius: 6px; }
.app-dark .ev.denegado { background: #78350f; color: #fde68a; }
.ev.salida { max-height: 12rem; overflow: auto; padding: .5rem; border-radius: 6px; margin: .25rem 0;
  background: var(--p-surface-100); font-size: .75rem; white-space: pre-wrap; }
.app-dark .ev.salida { background: var(--p-surface-800); }
.ev.salida.mala { border-left: 3px solid #dc2626; }
.transcript :deep(.p-panel-content) { max-height: 28rem; overflow: auto; }
</style>
