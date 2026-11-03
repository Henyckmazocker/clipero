<script setup lang="ts">
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Message from 'primevue/message';
import { computed, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { api, mensajeError, type ClipGroup } from '../api';
import { useClaude } from '../composables/useClaude';
import PublicarDialog from './PublicarDialog.vue';
import RetoqueDialog from './RetoqueDialog.vue';

const props = defineProps<{ visible: boolean; grupo: ClipGroup | null }>();
const emit = defineEmits<{ 'update:visible': [boolean]; cambio: [] }>();

const idx = ref(0);
const aviso = ref('');
const confirmarBorrar = ref(false);
const publicar = ref(false);
const retocar = ref(false);
const sesionEnCurso = ref(false);
const copiado = ref('');
const { cargar: cargarClaude, motivo: motivoClaude, bloqueado: sinClaude } = useClaude();
watch(() => [props.grupo?.base, props.grupo?.fecha, props.visible], () => {
  idx.value = Math.max(0, (props.grupo?.versiones.length ?? 1) - 1);
  aviso.value = ''; confirmarBorrar.value = false;
  if (props.visible) cargarClaude();
  if (props.visible) api.runActual().then(r => { sesionEnCurso.value = r !== null; }).catch(() => { sesionEnCurso.value = false; });
});
const v = computed(() => props.grupo?.versiones[Math.min(idx.value, (props.grupo?.versiones.length ?? 1) - 1)] ?? null);
const destino = computed(() => `${props.grupo?.base}-v${Math.max(1, ...(props.grupo?.versiones.map(x => x.n) ?? [1])) + 1}`);
const motivoRetoque = computed(() => v.value?.publicado ? 'Publicada: no se retoca'
  : !v.value?.editable ? 'Sin short.yaml'
  : sinClaude.value ? `${motivoClaude.value} Configuración › Claude`
  : sesionEnCurso.value ? 'Hay una sesión en curso: espera a que termine' : '');
const multiVod = computed(() => v.value?.formato === 'recopilacion');

async function copiar(que: 'titulo' | 'descripcion' | 'hashtags') {
  if (!v.value) return;
  await navigator.clipboard.writeText(v.value[que]);   // título tal cual: ya lleva #shorts
  copiado.value = que;
  setTimeout(() => { if (copiado.value === que) copiado.value = ''; }, 1500);
}
async function accion(f: () => Promise<unknown>, refrescar = true) {
  aviso.value = '';
  try { await f(); if (refrescar) emit('cambio'); } catch (e) { aviso.value = mensajeError(e); }
}
async function borrar() {
  confirmarBorrar.value = false;
  await accion(async () => {
    await api.borrar(v.value!);
    if ((props.grupo?.versiones.length ?? 0) <= 1) emit('update:visible', false);
  });
}
</script>

<template>
  <Dialog :visible="visible && !!v" modal :header="grupo?.base" :style="{ width: '60rem' }"
          @update:visible="emit('update:visible', $event)">
    <div v-if="v" class="cuerpo">
      <video :key="v.mp4" controls :src="v.mp4" class="video" />
      <div class="lado">
        <div v-if="grupo!.versiones.length > 1" class="pestanas">
          <button v-for="(x, i) in grupo!.versiones" :key="x.slug" :class="{ on: i === idx }" @click="idx = i">
            v{{ x.n }} <i v-if="x.publicado" class="pi pi-check-circle" />
          </button>
        </div>
        <h3>{{ v.titulo }}</h3>
        <div class="chips">
          <span v-if="v.fuente">{{ v.fuente }}</span><span v-if="v.tono">{{ v.tono }}</span>
          <span v-if="v.formato">{{ v.formato }}</span>
          <span v-if="v.duracion_s != null">{{ v.duracion_s.toFixed(1).replace('.', ',') }} s</span>
          <span v-if="v.encuadre">encuadre {{ v.encuadre }}</span>
        </div>
        <pre class="desc">{{ v.descripcion }}</pre>
        <div class="tags">{{ v.hashtags }}</div>
        <div class="fila">
          <Button :label="copiado === 'titulo' ? 'Copiado' : 'Copiar título'" icon="pi pi-copy" size="small" severity="secondary" @click="copiar('titulo')" />
          <Button :label="copiado === 'descripcion' ? 'Copiado' : 'Copiar descripción'" icon="pi pi-copy" size="small" severity="secondary" @click="copiar('descripcion')" />
          <Button :label="copiado === 'hashtags' ? 'Copiado' : 'Copiar hashtags'" icon="pi pi-copy" size="small" severity="secondary" @click="copiar('hashtags')" />
        </div>
        <div v-if="v.avisos.length" class="avisos">
          <div v-for="a in v.avisos" :key="a"><i class="pi pi-exclamation-triangle" /> {{ a }}</div>
        </div>
        <Message v-if="!v.editable" severity="warn" :closable="false">
          Sin <code>short.yaml</code>: <code>score</code> no podrá descartar este tramo al publicarlo.
        </Message>
        <Message v-if="multiVod" severity="info" :closable="false">
          Las recopilaciones con varios VODs solo guardan el primero en <code>publicados.csv</code>.
        </Message>
        <Message v-if="aviso" severity="error" :closable="false">{{ aviso }}</Message>
        <div v-if="v.publicado" class="publicado">
          <i class="pi pi-check-circle" /> Publicado el {{ v.publicado.fecha }} ·
          <a :href="v.publicado.url" target="_blank" rel="noopener">{{ v.publicado.url }}</a>
          <span v-if="v.publicado.claim"> · con claim</span>
        </div>
        <div class="fila">
          <Button label="Abrir carpeta" icon="pi pi-folder-open" size="small" severity="secondary" @click="accion(() => api.abrirCarpeta(v!), false)" />
          <Button v-if="!v.publicado" label="Publicado" icon="pi pi-check" size="small" @click="publicar = true" />
          <Button v-else :disabled="v.publicado.claim" :label="v.publicado.claim ? 'Claim marcado' : 'Marcar claim'" icon="pi pi-flag" size="small" severity="secondary" @click="accion(() => api.claim(v!))" />
          <Button label="Pedir cambio" icon="pi pi-pencil" size="small" severity="secondary"
                  :disabled="!!motivoRetoque" :title="motivoRetoque" @click="retocar = true" />
          <Button v-if="!confirmarBorrar" label="Borrar versión" icon="pi pi-trash" size="small" severity="danger" outlined
                  :disabled="!!v.publicado" :title="v.publicado ? 'Está publicada: no se puede borrar' : ''" @click="confirmarBorrar = true" />
          <template v-else>
            <Button label="Sí, borrar" icon="pi pi-trash" size="small" severity="danger" @click="borrar" />
            <Button label="No" size="small" text @click="confirmarBorrar = false" />
          </template>
        </div>
        <p v-if="sinClaude" class="sin-claude">
          {{ motivoClaude }} <RouterLink to="/config/claude" @click="emit('update:visible', false)">Configuración › Claude</RouterLink>.
        </p>
      </div>
    </div>
    <PublicarDialog v-if="v" v-model:visible="publicar" :version="v" @publicado="emit('cambio')" />
    <RetoqueDialog v-if="v" v-model:visible="retocar" :version="v" :destino="destino" />
  </Dialog>
</template>

<style scoped>
.sin-claude { margin: .5rem 0 0; font-size: .8rem; opacity: .8; }
.cuerpo { display: flex; gap: 1.25rem; }
.video { width: 22rem; max-height: 70vh; aspect-ratio: 9 / 16; background: #000; border-radius: 8px; flex: none; }
.lado { flex: 1; display: flex; flex-direction: column; gap: .75rem; min-width: 0; }
.lado h3 { margin: 0; font-size: 1.05rem; }
.pestanas { display: flex; gap: .25rem; }
.pestanas button { padding: .3rem .7rem; border: 1px solid var(--p-surface-300); border-radius: 6px; background: transparent;
  color: inherit; cursor: pointer; }
.pestanas button.on { background: var(--marca); border-color: var(--marca); color: #fff; }
.chips { display: flex; flex-wrap: wrap; gap: .3rem; font-size: .75rem; }
.chips span { padding: .1rem .5rem; border-radius: 4px; background: var(--p-surface-100); }
.app-dark .chips span { background: var(--p-surface-800); }
.desc { white-space: pre-wrap; font: inherit; font-size: .85rem; margin: 0; max-height: 12rem; overflow: auto; }
.tags { font-size: .8rem; opacity: .8; }
.fila { display: flex; flex-wrap: wrap; gap: .4rem; }
.avisos { border-left: 3px solid #f59e0b; background: #f59e0b22; padding: .5rem .75rem; font-size: .8rem; color: #b45309; }
.app-dark .avisos { color: #fbbf24; }
.publicado { font-size: .8rem; word-break: break-all; }
.publicado i { color: #22c55e; }
</style>
