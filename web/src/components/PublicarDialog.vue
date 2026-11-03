<script setup lang="ts">
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Message from 'primevue/message';
import { computed, onMounted, ref, watch } from 'vue';
import { api, mensajeError, type Fuente, type Version } from '../api';

const props = defineProps<{ visible: boolean; version: Version }>();
const emit = defineEmits<{ 'update:visible': [boolean]; publicado: [] }>();

const url = ref('');
const tono = ref('');
const fuente = ref('');
const formato = ref('');
const error = ref('');
const enviando = ref(false);
const fuentes = ref<Fuente[]>([]);
onMounted(async () => { fuentes.value = await api.fuentes().catch(() => []); });

// Se muestran los selectores cuando no hay yaml o falta algún campo; vienen rellenos con lo que ya se sabe.
const pedirCampos = computed(() => {
  const v = props.version;
  return !v.editable || !v.fuente || !v.formato || !v.tono;
});
watch(() => [props.visible, props.version.slug], () => {
  url.value = ''; error.value = '';
  tono.value = props.version.tono ?? ''; fuente.value = props.version.fuente ?? ''; formato.value = props.version.formato ?? '';
});

async function enviar() {
  error.value = ''; enviando.value = true;
  try {
    await api.publicar(props.version, url.value, { tono: tono.value, fuente: fuente.value, formato: formato.value });
    emit('publicado'); emit('update:visible', false);
  } catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}
</script>

<template>
  <Dialog :visible="visible" modal header="Marcar como publicado" :style="{ width: '32rem' }"
          @update:visible="emit('update:visible', $event)">
    <div class="form">
      <label>URL del Short en YouTube
        <input v-model="url" type="url" placeholder="https://youtube.com/shorts/…" autofocus @keyup.enter="enviar" />
      </label>
      <template v-if="pedirCampos">
        <Message v-if="!version.editable" severity="warn" :closable="false">
          Sin <code>short.yaml</code>: <code>vod_id</code>, <code>start</code> y <code>end</code> quedan vacíos y
          <code>score</code> no podrá descartar este tramo.
        </Message>
        <label>Fuente
          <select v-model="fuente"><option value="">—</option>
            <option v-for="f in fuentes" :key="f.id" :value="f.id">{{ f.nombre }}</option></select>
        </label>
        <label>Formato
          <select v-model="formato"><option value="">—</option>
            <option value="arco">arco</option><option value="momento">momento</option>
            <option value="recopilacion">recopilación</option></select>
        </label>
        <label>Tono
          <select v-model="tono"><option value="">—</option>
            <option value="critica">crítica</option><option value="positivo">positivo</option>
            <option value="neutro">neutro</option></select>
        </label>
      </template>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    </div>
    <template #footer>
      <Button label="Cancelar" text @click="emit('update:visible', false)" />
      <Button label="Publicado" icon="pi pi-check" :loading="enviando" :disabled="!url.trim()" @click="enviar" />
    </template>
  </Dialog>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; }
label { display: flex; flex-direction: column; gap: .25rem; font-size: .8rem; }
input, select { padding: .5rem; border-radius: 6px; border: 1px solid var(--p-surface-300);
  background: var(--p-surface-0); color: inherit; font: inherit; }
.app-dark input, .app-dark select { background: var(--p-surface-900); border-color: var(--p-surface-700); }
</style>
