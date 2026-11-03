<script setup lang="ts">
import Toast from 'primevue/toast';
import { RouterLink, RouterView } from 'vue-router';
import { marca } from '../marca';
import { elegir, eleccion, type Eleccion } from '../composables/useTheme';

type Entrada = { to: string; etiqueta: string; icono: string; activa: boolean };
const entradas: Entrada[] = [
  { to: '/clips', etiqueta: 'Clips', icono: 'pi-video', activa: true },
  { to: '/rendimiento', etiqueta: 'Rendimiento', icono: 'pi-chart-line', activa: true },
  { to: '/tanda', etiqueta: 'Tanda', icono: 'pi-bolt', activa: true },
  { to: '/config', etiqueta: 'Configuración', icono: 'pi-cog', activa: true },
];
const temas: { v: Eleccion; etiqueta: string }[] = [
  { v: 'sistema', etiqueta: 'Sistema' },
  { v: 'claro', etiqueta: 'Claro' },
  { v: 'oscuro', etiqueta: 'Oscuro' },
];
</script>

<template>
  <Toast />
  <div class="shell">
    <nav class="menu">
      <div class="marca">
        <span class="punto" />
        <span class="nombre">{{ marca.nombre }}</span>
      </div>
      <template v-for="e in entradas" :key="e.to">
        <RouterLink v-if="e.activa" :to="e.to" class="item" active-class="on">
          <i class="pi" :class="e.icono" /> {{ e.etiqueta }}
        </RouterLink>
        <span v-else class="item off" title="Próximamente">
          <i class="pi" :class="e.icono" /> {{ e.etiqueta }} <small>próximamente</small>
        </span>
      </template>
      <div class="tema">
        <button v-for="t in temas" :key="t.v" :class="{ on: eleccion === t.v }" @click="elegir(t.v)">
          {{ t.etiqueta }}
        </button>
      </div>
    </nav>
    <main class="contenido"><RouterView /></main>
  </div>
</template>

<style scoped>
.shell { display: flex; height: 100%; }
.menu { width: 15rem; flex: none; display: flex; flex-direction: column; gap: .25rem; padding: 1rem .75rem;
  background: var(--p-surface-0); border-right: 1px solid var(--p-surface-200); }
.app-dark .menu { background: var(--p-surface-900); border-color: var(--p-surface-800); }
.marca { display: flex; align-items: center; gap: .6rem; padding: .25rem .5rem 1rem; font-weight: 700; font-size: 1.1rem; }
.punto { width: .9rem; height: .9rem; border-radius: 50%; background: var(--marca); flex: none; }
.item { display: flex; align-items: center; gap: .6rem; padding: .6rem .75rem; border-radius: 8px;
  color: inherit; text-decoration: none; }
.item:hover:not(.off) { background: var(--p-surface-100); }
.app-dark .item:hover:not(.off) { background: var(--p-surface-800); }
.item.on { background: var(--marca); color: #fff; }
.item.off { opacity: .45; cursor: not-allowed; }
.item small { margin-left: auto; font-size: .65rem; }
.tema { margin-top: auto; display: flex; gap: .25rem; }
.tema button { flex: 1; padding: .35rem; border: 1px solid var(--p-surface-300); border-radius: 6px;
  background: transparent; color: inherit; cursor: pointer; font-size: .75rem; }
.tema button.on { border-color: var(--marca); color: var(--marca); }
.contenido { flex: 1; overflow: auto; padding: 1.5rem; }
</style>
