<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { dibujar, H, W, type Modo, type Rects } from '../layoutPreview';

const props = defineProps<{ src: string | null; entrada: [number, number]; modo: Modo; rects: Rects }>();
const K = 0.25;   // 270×480
const lienzo = ref<HTMLCanvasElement | null>(null);
let img: HTMLImageElement | null = null;

function pintar() {
  const ctx = lienzo.value?.getContext('2d');
  if (ctx) dibujar(ctx, img, props.entrada, props.modo, props.rects, K);
}

watch(() => props.src, (s) => {
  img = null;
  pintar();
  if (!s) return;
  const nueva = new Image();
  nueva.onload = () => { if (props.src === s) { img = nueva; pintar(); } };
  nueva.src = s;
}, { immediate: true });
watch(() => [props.entrada, props.modo, props.rects], pintar, { deep: true });
onMounted(pintar);
</script>

<template>
  <div class="v916">
    <canvas ref="lienzo" :width="W * K" :height="H * K" />
    <small v-if="modo === 'cara'">Aproximado: en el render sigue la cara.</small>
    <small v-else>Aproximado: el render real usa ffmpeg.</small>
  </div>
</template>

<style scoped>
.v916 { display: flex; flex-direction: column; gap: .4rem; align-items: center; }
canvas { width: 270px; height: 480px; border: 1px solid var(--p-content-border-color, #444); border-radius: 6px; background: #000; }
small { opacity: .7; }
</style>
