<script setup lang="ts">
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Message from 'primevue/message';
import ProgressSpinner from 'primevue/progressspinner';
import Select from 'primevue/select';
import { ref, watch } from 'vue';
import { api, mensajeError, type Canal, type Prueba, type PruebaCanal } from '../api';

const props = defineProps<{ visible: boolean; canal: Canal | null }>();   // canal=null → alta
const emit = defineEmits<{ 'update:visible': [boolean]; guardado: [] }>();

const vacio = (): Canal => ({ id: '', nombre: '', tamaño: 'mediano', twitch: '', youtube: '', credito: '' });
const f = ref<Canal>(vacio());
const error = ref('');
const enviando = ref(false);
const probando = ref(false);
const prueba = ref<PruebaCanal | null>(null);
const tamanos = [{ v: 'grande', e: 'Grande' }, { v: 'mediano', e: 'Mediano' }];

watch(() => props.visible, (v) => {
  if (!v) return;
  f.value = props.canal ? { ...vacio(), ...props.canal } : vacio();
  error.value = ''; prueba.value = null;
});

async function guardar() {
  error.value = ''; enviando.value = true;
  try {
    if (props.canal) await api.editarCanal(f.value); else await api.altaCanal(f.value);
    emit('guardado'); emit('update:visible', false);
  } catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}

async function probar() {
  error.value = ''; prueba.value = null; probando.value = true;
  try { prueba.value = await api.probarCanal(f.value); } catch (e) { error.value = mensajeError(e); } finally { probando.value = false; }
}

const texto = (p: Prueba) => (p.ok ? `OK · ${p.vods} VODs` : `Falla: ${p.error ?? 'sin respuesta'}`);
</script>

<template>
  <Dialog :visible="visible" modal :header="canal ? `Editar ${canal.nombre}` : 'Nuevo canal'" :style="{ width: '34rem' }"
          @update:visible="emit('update:visible', $event)">
    <div class="form">
      <label>Id <small>(slug; fijo una vez creado, nombra layouts/&lt;id&gt;.yaml)</small>
        <InputText v-model="f.id" :disabled="!!canal" placeholder="knekro" />
      </label>
      <label>Nombre <InputText v-model="f.nombre" /></label>
      <label>Tamaño
        <Select v-model="f.tamaño" :options="tamanos" option-label="e" option-value="v" />
      </label>
      <label>Twitch <small>(usuario en minúsculas; al menos Twitch o YouTube)</small>
        <InputText v-model="f.twitch" placeholder="knekro" />
      </label>
      <label>YouTube <small>(https://www.youtube.com/@canal, opcional /streams)</small>
        <InputText v-model="f.youtube" placeholder="https://www.youtube.com/@Knekro/streams" />
      </label>
      <label>Crédito <small>(vacío: se rellena con «Nombre (twitch.tv/usuario)»)</small>
        <InputText v-model="f.credito" />
      </label>
      <div class="probar">
        <Button label="Probar" icon="pi pi-search" severity="secondary" outlined :disabled="probando" @click="probar" />
        <ProgressSpinner v-if="probando" style="width: 1.5rem; height: 1.5rem" stroke-width="6" />
        <span v-if="prueba" class="res">
          <span v-if="prueba.twitch" :class="prueba.twitch.ok ? 'ok' : 'ko'">Twitch: {{ texto(prueba.twitch) }}</span>
          <span v-if="prueba.youtube" :class="prueba.youtube.ok ? 'ok' : 'ko'">YouTube: {{ texto(prueba.youtube) }}</span>
          <span v-if="!prueba.twitch && !prueba.youtube" class="ko">Pon un usuario de Twitch o una URL de YouTube.</span>
        </span>
      </div>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    </div>
    <template #footer>
      <Button label="Cancelar" text @click="emit('update:visible', false)" />
      <Button :label="canal ? 'Guardar' : 'Dar de alta'" icon="pi pi-check" :loading="enviando" @click="guardar" />
    </template>
  </Dialog>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .8rem; }
label { display: flex; flex-direction: column; gap: .25rem; font-size: .8rem; }
label small { opacity: .65; }
.probar { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.res { display: flex; flex-direction: column; font-size: .8rem; }
.ok { color: var(--p-green-600); }
.ko { color: var(--p-red-500); }
</style>
