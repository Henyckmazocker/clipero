<script setup lang="ts">
import InputNumber from 'primevue/inputnumber';
import { computed, ref } from 'vue';
import type { Rect } from '../api';

type Clave = 'facecam' | 'juego';
type Rects = Partial<Record<Clave, Rect>>;
const props = defineProps<{ src: string | null; entrada: [number, number]; rects: Rects }>();
const emit = defineEmits<{ 'update:rects': [Rects] }>();

const MIN = 8;
const ETIQUETA: Record<Clave, string> = { facecam: 'facecam', juego: 'juego' };
const claves = computed(() => (['juego', 'facecam'] as Clave[]).filter((c) => props.rects[c]));
const sel = ref<Clave>('facecam');
const svg = ref<SVGSVGElement | null>(null);
const iw = computed(() => props.entrada[0]);
const ih = computed(() => props.entrada[1]);
const asa = computed(() => Math.max(6, Math.round(iw.value / 70)));

const ASAS: Array<[string, number, number, string]> = [
  ['nw', 0, 0, 'nwse-resize'], ['n', 0.5, 0, 'ns-resize'], ['ne', 1, 0, 'nesw-resize'], ['e', 1, 0.5, 'ew-resize'],
  ['se', 1, 1, 'nwse-resize'], ['s', 0.5, 1, 'ns-resize'], ['sw', 0, 1, 'nesw-resize'], ['w', 0, 0.5, 'ew-resize'],
];
const clamp = (v: number, a: number, b: number) => Math.min(Math.max(v, a), Math.max(a, b));

type Arrastre = { clave: Clave; modo: string; px: number; py: number; r0: Rect };
let drag: Arrastre | null = null;

function punto(e: PointerEvent): [number, number] {
  const b = svg.value!.getBoundingClientRect();
  return [((e.clientX - b.left) / b.width) * iw.value, ((e.clientY - b.top) / b.height) * ih.value];
}
function inicio(e: PointerEvent, clave: Clave, modo: string) {
  const r = props.rects[clave];
  if (!r) return;
  e.preventDefault();
  sel.value = clave;
  (e.currentTarget as Element).setPointerCapture(e.pointerId);
  const [px, py] = punto(e);
  drag = { clave, modo, px, py, r0: { ...r } };
}
function mover(e: PointerEvent) {
  if (!drag) return;
  const [px, py] = punto(e);
  const dx = px - drag.px, dy = py - drag.py, r0 = drag.r0;
  let nuevo: Rect;
  if (drag.modo === 'mover') {
    nuevo = { ...r0, x: clamp(Math.round(r0.x + dx), 0, iw.value - r0.w), y: clamp(Math.round(r0.y + dy), 0, ih.value - r0.h) };
  } else {
    let l = r0.x, t = r0.y, r = r0.x + r0.w, b = r0.y + r0.h;
    if (drag.modo.includes('w')) l = clamp(Math.round(r0.x + dx), 0, r - MIN);
    if (drag.modo.includes('e')) r = clamp(Math.round(r0.x + r0.w + dx), l + MIN, iw.value);
    if (drag.modo.includes('n')) t = clamp(Math.round(r0.y + dy), 0, b - MIN);
    if (drag.modo.includes('s')) b = clamp(Math.round(r0.y + r0.h + dy), t + MIN, ih.value);
    nuevo = { x: l, y: t, w: r - l, h: b - t };
  }
  emit('update:rects', { ...props.rects, [drag.clave]: nuevo });
}
const fin = () => { drag = null; };

function cambiar(clave: Clave, campo: keyof Rect, v: number | null) {
  const base = props.rects[clave];
  if (v == null || !base) return;
  const r = { ...base, [campo]: Math.round(v) };
  r.w = clamp(r.w, 1, iw.value); r.h = clamp(r.h, 1, ih.value);
  r.x = clamp(r.x, 0, iw.value - r.w); r.y = clamp(r.y, 0, ih.value - r.h);
  emit('update:rects', { ...props.rects, [clave]: r });
}
const CAMPOS: Array<keyof Rect> = ['x', 'y', 'w', 'h'];
const maximo = (clave: Clave, c: keyof Rect) => {
  const r = props.rects[clave]!;
  return c === 'x' ? iw.value - r.w : c === 'y' ? ih.value - r.h : c === 'w' ? iw.value : ih.value;
};
</script>

<template>
  <div class="editor">
    <div class="lienzo" :style="{ aspectRatio: `${iw} / ${ih}` }">
      <img v-if="src" :src="src" alt="Fotograma del tramo" draggable="false" />
      <svg ref="svg" :viewBox="`0 0 ${iw} ${ih}`" preserveAspectRatio="none">
        <template v-for="c in claves" :key="c">
          <rect :x="rects[c]!.x" :y="rects[c]!.y" :width="rects[c]!.w" :height="rects[c]!.h"
                :class="['rect', c, { activo: sel === c }]" fill="transparent"
                @pointerdown="inicio($event, c, 'mover')" @pointermove="mover" @pointerup="fin" @pointercancel="fin" />
        </template>
        <template v-if="rects[sel]">
          <rect v-for="[id, fx, fy, cur] in ASAS" :key="id"
                :x="rects[sel]!.x + rects[sel]!.w * fx - asa / 2" :y="rects[sel]!.y + rects[sel]!.h * fy - asa / 2"
                :width="asa" :height="asa" :class="['asa', sel]" :style="{ cursor: cur }"
                @pointerdown="inicio($event, sel, id)" @pointermove="mover" @pointerup="fin" @pointercancel="fin" />
        </template>
      </svg>
    </div>

    <div v-for="c in claves" :key="c" class="numeros">
      <span :class="['etq', c]" @click="sel = c">{{ ETIQUETA[c] }}</span>
      <label v-for="k in CAMPOS" :key="k">{{ k }}
        <InputNumber :model-value="rects[c]![k]" :min="k === 'w' || k === 'h' ? 1 : 0" :max="maximo(c, k)"
                     :use-grouping="false" size="small" input-class="num" @focus="sel = c"
                     @update:model-value="cambiar(c, k, $event)" />
      </label>
    </div>
  </div>
</template>

<style scoped>
.editor { display: flex; flex-direction: column; gap: .75rem; }
.lienzo { position: relative; width: 100%; background: #111; border-radius: 6px; }
.lienzo img, .lienzo svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.lienzo svg { overflow: visible; touch-action: none; }
.rect { cursor: move; stroke-width: 2; vector-effect: non-scaling-stroke; fill-opacity: 0; touch-action: none; }
.rect.activo { stroke-width: 3; }
.rect.facecam, .asa.facecam { stroke: var(--marca, #e0201b); }
.rect.juego, .asa.juego { stroke: #22d3ee; }
.asa { fill: #fff; stroke-width: 2; vector-effect: non-scaling-stroke; touch-action: none; }
.numeros { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.numeros label { display: flex; align-items: center; gap: .3rem; font-size: .85rem; }
.etq { font-weight: 600; width: 5rem; cursor: pointer; border-left: 4px solid; padding-left: .4rem; }
.etq.facecam { border-color: var(--marca, #e0201b); }
.etq.juego { border-color: #22d3ee; }
:deep(.num) { width: 5rem; }
</style>
