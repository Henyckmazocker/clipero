<script setup lang="ts">
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Message from 'primevue/message';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import { ref, watch } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { useClaude } from '../composables/useClaude';
import { api, ApiError, mensajeError, type TandaDefaults, type Version } from '../api';

const props = defineProps<{ visible: boolean; version: Version; destino: string }>();
const emit = defineEmits<{ 'update:visible': [boolean] }>();
const router = useRouter();

const peticion = ref('');
const modelo = ref('');
const defaults = ref<TandaDefaults | null>(null);
const error = ref('');
const runOcupado = ref<string | null>(null);
const enviando = ref(false);
const { cargar: cargarClaude, motivo: motivoClaude, bloqueado: sinClaude } = useClaude();

watch(() => [props.visible, props.version.slug], async () => {
  if (!props.visible) return;
  peticion.value = ''; error.value = ''; runOcupado.value = null;
  cargarClaude();
  try {
    defaults.value = await api.tandaDefaults();
    modelo.value = defaults.value.modelo;
  } catch (e) { error.value = mensajeError(e); }
});

async function enviar() {
  error.value = ''; runOcupado.value = null; enviando.value = true;
  try {
    const r = await api.retocar(props.version, peticion.value.trim(), modelo.value || undefined);
    emit('update:visible', false);
    router.push(`/tanda?run=${encodeURIComponent(r.id)}`);
  } catch (e) {
    error.value = mensajeError(e);
    if (e instanceof ApiError && e.codigo === 'ocupado') runOcupado.value = e.run ?? null;
  } finally { enviando.value = false; }
}
function verSesion() {
  emit('update:visible', false);
  router.push(`/tanda?run=${encodeURIComponent(runOcupado.value!)}`);
}
</script>

<template>
  <Dialog :visible="visible" modal header="Pedir cambio" :style="{ width: '34rem' }"
          :closable="!enviando" @update:visible="emit('update:visible', $event)">
    <div class="form">
      <label>¿Qué cambio quieres?
        <Textarea v-model="peticion" rows="4" auto-resize :disabled="enviando" fluid
                  placeholder="Ej.: gancho más agresivo, quita el segundo tramo…" />
      </label>
      <label>Modelo
        <Select v-model="modelo" :options="defaults?.modelos ?? []" :disabled="enviando" fluid />
      </label>
      <p class="destino">Se creará (previsto) <code>{{ destino }}</code> a partir de <code>{{ version.slug }}</code>.</p>
      <Message v-if="sinClaude" severity="warn" :closable="false">
        {{ motivoClaude }} <RouterLink to="/config/claude" @click="emit('update:visible', false)">Configuración › Claude</RouterLink>.
      </Message>
      <Message v-if="enviando" severity="info" :closable="false">
        Enviando la petición (destino previsto: <code>{{ destino }}</code>; el definitivo lo fija el servidor)…
      </Message>
      <Message v-if="error" severity="error" :closable="false">
        {{ error }}
        <a v-if="runOcupado" href="#" @click.prevent="verSesion">Ver la sesión en curso</a>
      </Message>
    </div>
    <template #footer>
      <Button label="Cancelar" text :disabled="enviando" @click="emit('update:visible', false)" />
      <Button label="Enviar" icon="pi pi-send" :loading="enviando" :disabled="!peticion.trim() || !modelo || sinClaude" @click="enviar" />
    </template>
  </Dialog>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; }
label { display: flex; flex-direction: column; gap: .3rem; font-size: .85rem; font-weight: 600; }
.destino { margin: 0; font-size: .8rem; opacity: .75; }
</style>
