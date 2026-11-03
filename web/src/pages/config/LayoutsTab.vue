<script setup lang="ts">
import Button from 'primevue/button';
import ConfirmDialog from 'primevue/confirmdialog';
import InputText from 'primevue/inputtext';
import Message from 'primevue/message';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import Slider from 'primevue/slider';
import Tab from 'primevue/tab';
import TabList from 'primevue/tablist';
import Tabs from 'primevue/tabs';
import ToggleSwitch from 'primevue/toggleswitch';
import { useConfirm } from 'primevue/useconfirm';
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  api, ApiError, mensajeError, urlFotograma,
  type Escena, type Layout, type LayoutFila, type Rect, type ResultadoProbar, type Tramo, type VodLayout,
} from '../../api';
import RectEditor from '../../components/RectEditor.vue';
import Vista916 from '../../components/Vista916.vue';
import type { Modo } from '../../layoutPreview';

const route = useRoute();
const router = useRouter();
const confirmar = useConfirm();

const filas = ref<LayoutFila[]>([]);
const vods = ref<VodLayout[]>([]);
const vodSel = ref('');
const segSel = ref('');
const tSlider = ref(0);
const t = ref(0);

const destino = ref('');                 // '' = todo el canal; si no, id del VOD de la excepción
const layout = ref<Layout | null>(null);
const nuevo = ref(false);                // aún no está en disco
const escenaSel = ref('');
const error = ref('');
const ok = ref('');
const resultado = ref<ResultadoProbar | null>(null);
const ocupado = ref(false);

const fuente = computed(() => String(route.params.fuente ?? ''));
const fila = computed(() => filas.value.find((f) => f.fuente === fuente.value));
const vod = computed<VodLayout | undefined>(() => vods.value.find((v) => v.vod === vodSel.value));
const tramo = computed<Tramo | undefined>(() => vod.value?.tramos.find((x) => x.seg === segSel.value));
const src = computed(() => (vod.value && tramo.value ? urlFotograma(vod.value.vod, tramo.value.seg, t.value) : null));

// --- carga ----------------------------------------------------------------------

const medio = (x: Tramo) => Math.round(((x.start + x.end) / 2) * 2) / 2;
function elegirTramo(seg: string) {
  segSel.value = seg;
  const x = vod.value?.tramos.find((y) => y.seg === seg);
  if (x) { tSlider.value = Math.min(Math.max(medio(x), x.start), x.end); t.value = tSlider.value; }
  resultado.value = null;
}
function elegirVod(id: string) {
  vodSel.value = id;
  const v = vods.value.find((y) => y.vod === id);
  elegirTramo(v?.tramos[0]?.seg ?? '');
}
let temporizador: ReturnType<typeof setTimeout> | undefined;
watch(tSlider, (v) => { clearTimeout(temporizador); temporizador = setTimeout(() => { t.value = v; resultado.value = null; }, 250); });
onBeforeUnmount(() => clearTimeout(temporizador));

async function refrescarFilas() {
  try { filas.value = await api.layouts(); } catch (e) { error.value = mensajeError(e); }
}

async function leer(vodId?: string): Promise<Layout | null> {
  try { return await api.layout(fuente.value, vodId || undefined); }
  catch (e) { if (e instanceof ApiError && e.codigo === 'sin_layout') return null; throw e; }
}

function adoptar(l: Layout | null, esNuevo = false) {
  layout.value = l;
  nuevo.value = esNuevo;
  resultado.value = null;
  escenaSel.value = l?.escenas ? Object.keys(l.escenas)[0] ?? '' : '';
}

async function cargarFuente() {
  error.value = ''; ok.value = ''; vods.value = []; vodSel.value = ''; segSel.value = ''; destino.value = '';
  adoptar(null);
  if (!fuente.value) return;
  const f = fuente.value;
  try {
    await refrescarFilas();
    const [vs, l] = await Promise.all([api.layoutVods(f), leer()]);
    if (f !== fuente.value) return;
    vods.value = vs;
    adoptar(l);
    elegirVod(vs[0]?.vod ?? '');
  } catch (e) { error.value = mensajeError(e); }
}

watch(fuente, async () => {
  if (!fuente.value) {
    await refrescarFilas();
    if (filas.value[0]) router.replace(`/config/layouts/${filas.value[0].fuente}`);
    return;
  }
  cargarFuente();
}, { immediate: true });

async function cambiarDestino(d: string) {
  destino.value = d; error.value = ''; ok.value = '';
  try {
    adoptar(await leer(d));
    if (d && vods.value.some((v) => v.vod === d) && vodSel.value !== d) elegirVod(d);
  } catch (e) { error.value = mensajeError(e); }
}

// --- plantilla y excepciones ----------------------------------------------------

const clon = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const dims = (): [number, number] => [tramo.value?.w ?? 1920, tramo.value?.h ?? 1080];
function plantilla(): Layout {
  const [w, h] = dims();
  const r = Math.round;
  return {
    entrada: `${w}x${h}`,
    facecam: { x: r(0.75 * w), y: r(0.5 * h), w: r(0.24 * w), h: r(0.25 * h) },
    juego: { x: 0, y: 0, w, h },
  };
}
const crearLayout = () => { adoptar(plantilla(), true); ok.value = ''; error.value = ''; };

async function nuevaExcepcion() {
  if (!vodSel.value) return;
  error.value = ''; ok.value = '';
  try {
    const base = (await leer()) ?? plantilla();
    destino.value = vodSel.value;
    adoptar(clon(base), true);
  } catch (e) { error.value = mensajeError(e); }
}

const opcionesDestino = computed(() => {
  const ids = [...(fila.value?.excepciones ?? [])];
  if (destino.value && !ids.includes(destino.value)) ids.push(destino.value);
  return [{ label: 'Todo el canal', value: '' }, ...ids.map((v) => ({ label: `Solo el VOD ${v}`, value: v }))];
});
const puedeExcepcion = computed(() => !!vodSel.value && destino.value !== vodSel.value && !fila.value?.excepciones.includes(vodSel.value));

// --- edición ----------------------------------------------------------------------

const entrada = computed<[number, number]>(() => {
  const m = /^(\d+)x(\d+)$/i.exec(String(layout.value?.entrada ?? ''));
  return m ? [Number(m[1]), Number(m[2])] : [1920, 1080];
});
const escenas = computed(() => layout.value?.escenas);
const nombres = computed(() => Object.keys(escenas.value ?? {}));
const tipoDe = (e?: Escena): 'recuadro' | 'ancho' | 'cara' => (e && 'ancho' in e ? 'ancho' : e && 'cara' in e ? 'cara' : 'recuadro');
const escenaAct = computed(() => (escenaSel.value ? escenas.value?.[escenaSel.value] : undefined));
const tipoAct = computed(() => tipoDe(escenaAct.value));
const modo = computed<Modo>(() => (escenas.value ? tipoAct.value : 'plano'));

const rectsAct = computed({
  get: () => {
    const l = layout.value;
    if (!l) return {};
    const o = escenas.value ? escenaAct.value : l;
    return o && 'facecam' in o ? { facecam: o.facecam, juego: o.juego } : {};
  },
  set: (r) => {
    const l = layout.value;
    if (!l) return;
    const o = escenas.value ? escenaAct.value : l;
    if (!o) return;
    if (r.facecam) o.facecam = r.facecam;
    if (r.juego) o.juego = r.juego;
    resultado.value = null;
  },
});

const plantillaRects = (): { facecam: Rect; juego: Rect } => {
  const [w, h] = entrada.value;
  const r = Math.round;
  return { facecam: { x: r(0.75 * w), y: r(0.5 * h), w: r(0.24 * w), h: r(0.25 * h) }, juego: { x: 0, y: 0, w, h } };
};

function conEscenas(on: boolean) {
  const l = layout.value;
  if (!l) return;
  if (on && !l.escenas) {
    const f = l.facecam ?? plantillaRects().facecam, j = l.juego ?? plantillaRects().juego;
    delete l.facecam; delete l.juego;
    l.escenas = { principal: { facecam: f, juego: j } };
    escenaSel.value = 'principal';
  } else if (!on && l.escenas) {
    const e = Object.values(l.escenas).find((x) => x.facecam && x.juego);
    delete l.escenas;
    l.facecam = e?.facecam ?? plantillaRects().facecam;
    l.juego = e?.juego ?? plantillaRects().juego;
    escenaSel.value = '';
  }
  resultado.value = null;
}

function cambiarTipo(tipo: 'recuadro' | 'ancho' | 'cara' | null) {
  const l = layout.value;
  if (!tipo || !l?.escenas || !escenaSel.value || tipo === tipoAct.value) return;
  l.escenas[escenaSel.value] = tipo === 'recuadro' ? plantillaRects() : tipo === 'ancho' ? { ancho: true } : { cara: true };
  resultado.value = null;
}

function renombrar(nuevoNombre: string | undefined) {
  const l = layout.value;
  const viejo = escenaSel.value;
  const n = nuevoNombre ?? '';
  if (!l?.escenas || n === viejo || (n in l.escenas)) return;
  // reconstruye el mapa para conservar el orden
  const sal: Record<string, Escena> = {};
  for (const [k, v] of Object.entries(l.escenas)) sal[k === viejo ? n : k] = v;
  l.escenas = sal;
  escenaSel.value = n;
}

function añadirEscena() {
  const l = layout.value;
  if (!l?.escenas) return;
  let i = nombres.value.length + 1;
  while (`escena_${i}` in l.escenas) i++;
  const hayCara = Object.values(l.escenas).some((e) => e.facecam);
  l.escenas[`escena_${i}`] = hayCara ? { ancho: true } : plantillaRects();
  escenaSel.value = `escena_${i}`;
}
function quitarEscena() {
  const l = layout.value;
  if (!l?.escenas || nombres.value.length < 2) return;
  const i = nombres.value.indexOf(escenaSel.value);
  delete l.escenas[escenaSel.value];
  escenaSel.value = nombres.value[Math.max(0, i - 1)];
}

// = clipero/frame.py:validate_layout / _check_escenas / _check_rect (la que manda es la del servidor)
function validar(l: Layout | null): string[] {
  if (!l) return [];
  const er: string[] = [];
  const [iw, ih] = entrada.value;
  const rect = (nombre: string, r: Rect | undefined) => {
    if (!r || ![r.x, r.y, r.w, r.h].every(Number.isInteger)) return er.push(`«${nombre}» tiene que ser {x, y, w, h} con enteros`);
    if (r.w <= 0 || r.h <= 0 || r.x < 0 || r.y < 0 || r.x + r.w > iw || r.y + r.h > ih)
      er.push(`«${nombre}» queda fuera de la imagen (${iw}x${ih}) o mide 0`);
  };
  if (l.escenas) {
    const entradas = Object.entries(l.escenas);
    if (!entradas.length) er.push('Tiene que haber al menos una escena');
    for (const [n, c] of entradas) {
      if (!/^[a-z0-9_]+$/.test(n)) er.push(`El nombre de escena «${n}» solo admite a-z, 0-9 y _`);
      const tipos = (['facecam', 'ancho', 'cara'] as const).filter((k) => k in c);
      if (tipos.length !== 1 || ('facecam' in c && !('juego' in c)))
        er.push(`La escena «${n}» tiene que ser recuadro (facecam + juego), ancho o cara`);
      else if ('facecam' in c) { rect(`${n}.facecam`, c.facecam); rect(`${n}.juego`, c.juego); }
    }
    if (entradas.filter(([, c]) => 'facecam' in c).length > 1) er.push('Solo una escena puede ser de tipo Recuadro (la detectable)');
    if (entradas.filter(([, c]) => !('facecam' in c)).length > 1) er.push('Solo una escena puede ser la de por defecto (Ancho o Cara)');
  } else { rect('facecam', l.facecam); rect('juego', l.juego); }
  return er;
}
const problemas = computed(() => validar(layout.value));

// --- acciones -----------------------------------------------------------------------

const objetivo = () => destino.value || undefined;

async function guardar() {
  if (!layout.value || problemas.value.length) return;
  error.value = ''; ok.value = ''; ocupado.value = true;
  try {
    adoptarGuardado(await api.guardarLayout(fuente.value, objetivo(), clon(layout.value)));
    await refrescarFilas();
  } catch (e) { error.value = mensajeError(e); } finally { ocupado.value = false; }
}
function adoptarGuardado(l: Layout) {
  const esc = escenaSel.value;
  adoptar(l);
  if (l.escenas && esc in l.escenas) escenaSel.value = esc;
  ok.value = destino.value ? `Excepción del VOD ${destino.value} guardada.` : 'Layout del canal guardado.';
}

async function probar() {
  if (!layout.value || !vod.value || !tramo.value || problemas.value.length) return;
  error.value = ''; resultado.value = null; ocupado.value = true;
  try { resultado.value = await api.probarLayout(clon(layout.value), vod.value.vod, tramo.value.seg, t.value); }
  catch (e) { error.value = mensajeError(e); } finally { ocupado.value = false; }
}

function pedirBorrar() {
  const que = destino.value ? `la excepción del VOD ${destino.value}` : 'el layout del canal';
  confirmar.require({
    header: 'Borrar layout', icon: 'pi pi-exclamation-triangle', acceptLabel: 'Borrar', rejectLabel: 'Cancelar',
    acceptProps: { severity: 'danger' }, rejectProps: { severity: 'secondary', text: true },
    message: `¿Borrar ${que}? Se elimina el fichero y no hay copia.${destino.value ? '' : ' Sin layout el render vuelve a seguir la cara.'}`,
    accept: borrar,
  });
}
async function borrar() {
  error.value = ''; ok.value = '';
  try {
    await api.borrarLayout(fuente.value, objetivo());
    await refrescarFilas();
    if (destino.value) await cambiarDestino(''); else adoptar(null);
    ok.value = 'Layout borrado.';
  } catch (e) { error.value = mensajeError(e); }
}

const tipos = [
  { l: 'Recuadro', v: 'recuadro' }, { l: 'Ancho', v: 'ancho' }, { l: 'Cara', v: 'cara' },
];
const etiquetaVod = (v: VodLayout) => `${v.vod} · ${v.fecha} · ${v.titulo.slice(0, 50)}`;
const etiquetaTramo = (x: Tramo) => `${x.start}–${x.end} s${x.w && x.h ? ` (${x.w}×${x.h})` : ''}`;
</script>

<template>
  <ConfirmDialog />
  <div class="fila">
    <label>Canal
      <Select :model-value="fuente" :options="filas" option-label="nombre" option-value="fuente" placeholder="Elige un canal"
              @update:model-value="router.push(`/config/layouts/${$event}`)" />
    </label>
    <label v-if="fuente">Destino
      <Select :model-value="destino" :options="opcionesDestino" option-label="label" option-value="value"
              @update:model-value="cambiarDestino" />
    </label>
    <Button v-if="fuente && puedeExcepcion" label="Nueva excepción para este VOD" icon="pi pi-plus" size="small" outlined
            @click="nuevaExcepcion" />
  </div>

  <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
  <Message v-if="ok" severity="success" :closable="false">{{ ok }}</Message>

  <template v-if="fuente">
    <Message v-if="!vods.length" severity="warn" :closable="false">
      No hay segmentos de este canal: renderiza o transcribe algo primero (<code>clean</code> los borra a los 14 días).
    </Message>
    <div v-else class="fila">
      <label>VOD
        <Select :model-value="vodSel" :options="vods" option-value="vod" :option-label="etiquetaVod" @update:model-value="elegirVod" />
      </label>
      <label>Tramo
        <Select :model-value="segSel" :options="vod?.tramos ?? []" option-value="seg" :option-label="etiquetaTramo"
                @update:model-value="elegirTramo" />
      </label>
      <label v-if="tramo" class="slider">Segundo: {{ tSlider.toFixed(1) }} s
        <Slider v-model="tSlider" :min="tramo.start" :max="tramo.end" :step="0.5" />
      </label>
    </div>

    <div v-if="!layout" class="vacio">
      <p>Este canal no tiene layout{{ destino ? ' para ese VOD' : '' }}.</p>
      <Message severity="info" :closable="false">
        Con layout, el render deja de seguir la cara del canal y usa los recuadros fijos.
      </Message>
      <Button label="Crear layout" icon="pi pi-plus" @click="crearLayout" />
    </div>

    <div v-else class="cols">
      <section class="izq">
        <div class="fila">
          <label class="check"><ToggleSwitch :model-value="!!escenas" @update:model-value="conEscenas" /> Con escenas</label>
          <small>entrada {{ layout.entrada }}</small>
          <Message v-if="nuevo" severity="info" :closable="false">
            Aún no guardado.{{ destino ? '' : ' Al guardarlo, el canal deja de seguir la cara.' }}
          </Message>
        </div>

        <template v-if="escenas">
          <Tabs :value="escenaSel" scrollable @update:value="escenaSel = String($event)">
            <TabList>
              <Tab v-for="n in nombres" :key="n" :value="n">{{ n }}</Tab>
            </TabList>
          </Tabs>
          <div class="fila">
            <label>Nombre
              <InputText :model-value="escenaSel" @change="renombrar(($event.target as HTMLInputElement).value)" />
            </label>
            <SelectButton :model-value="tipoAct" :options="tipos" option-label="l" option-value="v" :allow-empty="false"
                          @update:model-value="cambiarTipo" />
            <Button icon="pi pi-plus" label="Añadir escena" size="small" text @click="añadirEscena" />
            <Button icon="pi pi-trash" label="Quitar" size="small" text severity="secondary"
                    :disabled="nombres.length < 2" @click="quitarEscena" />
          </div>
        </template>

        <RectEditor v-model:rects="rectsAct" :src="src" :entrada="entrada" />
        <p v-if="modo === 'ancho' || modo === 'cara'" class="nota">
          Esta escena ({{ modo }}) no tiene recuadros que editar.
        </p>

        <Message v-for="p in problemas" :key="p" severity="warn" :closable="false">{{ p }}</Message>

        <div class="fila">
          <Button label="Guardar" icon="pi pi-save" :disabled="!!problemas.length || ocupado" @click="guardar" />
          <Button label="Probar detección" icon="pi pi-search" severity="secondary"
                  :disabled="!!problemas.length || ocupado || !src" @click="probar" />
          <Button label="Borrar layout" icon="pi pi-trash" severity="danger" text :disabled="nuevo || ocupado" @click="pedirBorrar" />
        </div>
        <Message v-if="resultado" :severity="resultado.detecta ? 'success' : 'warn'" :closable="false">
          Detección: {{ resultado.score.toFixed(2) }} (umbral {{ resultado.umbral.toFixed(2) }}) —
          {{ resultado.detecta ? 'se detecta el recuadro' : 'no se detecta' }}.
          <span v-if="resultado.aviso"> {{ resultado.aviso }}</span>
        </Message>
      </section>

      <aside>
        <Vista916 :src="src" :entrada="entrada" :modo="modo" :rects="rectsAct" />
      </aside>
    </div>
  </template>
  <p v-else class="nota">Elige un canal.</p>
</template>

<style scoped>
.fila { display: flex; align-items: flex-end; gap: 1rem; flex-wrap: wrap; margin-bottom: .75rem; }
label { display: flex; flex-direction: column; gap: .25rem; font-size: .85rem; }
label.check { flex-direction: row; align-items: center; gap: .5rem; }
.slider { min-width: 18rem; flex: 1; }
.cols { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 1.5rem; align-items: start; }
.izq { min-width: 0; display: flex; flex-direction: column; gap: .5rem; }
.vacio { display: flex; flex-direction: column; gap: .75rem; align-items: flex-start; }
.nota { opacity: .7; font-size: .9rem; }
aside { position: sticky; top: 1rem; }
</style>
