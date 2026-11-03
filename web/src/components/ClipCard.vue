<script setup lang="ts">
import type { ClipGroup } from '../api';

const props = defineProps<{ grupo: ClipGroup }>();
defineEmits<{ abrir: [] }>();
const v = props.grupo.versiones[0];
const ultima = () => props.grupo.versiones[props.grupo.versiones.length - 1];
const segundos = (s: number | null) => (s == null ? null : `${s.toFixed(1).replace('.', ',')} s`);
const algunaPublicada = () => props.grupo.versiones.some((x) => x.publicado);
</script>

<template>
  <button class="tarjeta" @click="$emit('abrir')">
    <div class="miniatura">
      <img :src="ultima().thumb" :alt="v.titulo" loading="lazy" />
      <span v-if="grupo.versiones.length > 1" class="insignia">v{{ ultima().n }}</span>
      <i v-if="algunaPublicada()" class="pi pi-check-circle check" title="Publicado" />
    </div>
    <div class="texto">
      <div class="titulo">{{ ultima().titulo.replace(/ #shorts$/, '') }}</div>
      <div class="chips">
        <span v-if="ultima().fuente" class="chip">{{ ultima().fuente }}</span>
        <span v-if="ultima().tono" class="chip" :class="ultima().tono!">{{ ultima().tono }}</span>
        <span v-if="ultima().formato" class="chip">{{ ultima().formato }}</span>
        <span v-if="segundos(ultima().duracion_s)" class="chip">{{ segundos(ultima().duracion_s) }}</span>
      </div>
    </div>
  </button>
</template>

<style scoped>
.tarjeta { text-align: left; padding: 0; border: 1px solid var(--p-surface-200); border-radius: 10px;
  background: var(--p-surface-0); color: inherit; cursor: pointer; overflow: hidden; font: inherit; }
.app-dark .tarjeta { background: var(--p-surface-900); border-color: var(--p-surface-800); }
.tarjeta:hover { border-color: var(--marca); }
.miniatura { position: relative; aspect-ratio: 9 / 16; background: #000; }
.miniatura img { width: 100%; height: 100%; object-fit: cover; display: block; }
.insignia { position: absolute; top: .4rem; left: .4rem; background: var(--marca); color: #fff;
  border-radius: 999px; padding: .05rem .5rem; font-size: .75rem; font-weight: 700; }
.check { position: absolute; top: .4rem; right: .4rem; color: #22c55e; background: #000a; border-radius: 50%; font-size: 1.2rem; }
.texto { padding: .6rem; display: flex; flex-direction: column; gap: .4rem; }
.titulo { font-size: .85rem; font-weight: 600; line-height: 1.25; display: -webkit-box;
  -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.chips { display: flex; flex-wrap: wrap; gap: .25rem; }
.chip { font-size: .65rem; padding: .1rem .4rem; border-radius: 4px; background: var(--p-surface-100); }
.app-dark .chip { background: var(--p-surface-800); }
.chip.critica { background: #fecaca; color: #7f1d1d; }
.chip.positivo { background: #bbf7d0; color: #14532d; }
.chip.neutro { background: #e5e7eb; color: #374151; }
</style>
