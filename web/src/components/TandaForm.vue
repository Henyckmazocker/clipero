<script setup lang="ts">
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import InputText from 'primevue/inputtext';
import MultiSelect from 'primevue/multiselect';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import Textarea from 'primevue/textarea';
import { useToast } from 'primevue/usetoast';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useClaude } from '../composables/useClaude';
import { api, ApiError, mensajeError, type Fuente, type TandaDefaults, type TandaIn } from '../api';

defineProps<{ ocupado: boolean }>();
const emit = defineEmits<{ lanzada: [id: string]; ocupada: [id: string | null] }>();
const toast = useToast();

const modos = [{ v: 'canales', e: 'Canales' }, { v: 'vod', e: 'VOD concreto' }];
const editoriales = [{ v: 'mixta', e: 'Mixta' }, { v: 'positiva', e: 'Positiva' }, { v: 'critica', e: 'Crítica' }];

const fuentes = ref<Fuente[]>([]);
const defaults = ref<TandaDefaults | null>(null);
const modo = ref<'canales' | 'vod'>('canales');
const sel = ref<string[]>([]);
const dias = ref<number | null>(7);
const url = ref('');
const clips = ref<number | null>(5);
const editorial = ref<TandaIn['editorial']>('mixta');
const modelo = ref('');
const nota = ref('');
const enviando = ref(false);
const error = ref('');
const { cargar: cargarClaude, motivo: motivoClaude, bloqueado: sinClaude } = useClaude();

onMounted(async () => {
  cargarClaude();
  try {
    const [f, d] = await Promise.all([api.fuentes(), api.tandaDefaults()]);
    fuentes.value = f; defaults.value = d;
    clips.value = d.clips; dias.value = d.dias; editorial.value = d.editorial; modelo.value = d.modelo;
  } catch (e) { error.value = mensajeError(e); }
});

async function lanzar() {
  error.value = '';
  const vod = modo.value === 'vod';
  const cuerpo: TandaIn = {
    fuentes: vod ? [] : sel.value, vod_url: vod ? url.value.trim() : null,
    clips: clips.value ?? 5, editorial: editorial.value, dias: vod ? (defaults.value?.dias ?? 7) : (dias.value ?? 7), modelo: modelo.value, nota: nota.value,
  };
  enviando.value = true;
  try {
    const r = await api.lanzarTanda(cuerpo);
    if (r.canal_creado) {
      toast.add({ severity: 'info', summary: 'Canal nuevo', life: 8000,
        detail: `Canal ${r.canal_creado.nombre} añadido a Configuración › Canales` });
    }
    emit('lanzada', r.id);
  } catch (e) {
    error.value = mensajeError(e);
    if (e instanceof ApiError && e.codigo === 'ocupado') emit('ocupada', e.run ?? null);
  } finally { enviando.value = false; }
}
</script>

<template>
  <form class="form" @submit.prevent="lanzar">
    <SelectButton v-model="modo" :options="modos" option-label="e" option-value="v" :allow-empty="false" />

    <template v-if="modo === 'canales'">
      <label>Canales <small>(vacío = todos)</small>
        <MultiSelect v-model="sel" :options="fuentes" option-label="nombre" option-value="id" placeholder="Todos los canales"
          display="chip" filter fluid />
      </label>
      <label>Días hacia atrás
        <InputNumber v-model="dias" :min="1" :max="30" show-buttons fluid />
      </label>
    </template>
    <label v-else>URL del VOD
      <InputText v-model="url" placeholder="https://www.twitch.tv/videos/…" fluid />
    </label>

    <label>Clips como máximo
      <InputNumber v-model="clips" :min="1" :max="10" show-buttons fluid />
    </label>
    <label>Editorial
      <SelectButton v-model="editorial" :options="editoriales" option-label="e" option-value="v" :allow-empty="false" />
    </label>
    <label>Modelo
      <Select v-model="modelo" :options="defaults?.modelos ?? []" fluid />
    </label>
    <label>Nota <small>(opcional)</small>
      <Textarea v-model="nota" rows="3" maxlength="1000" auto-resize fluid />
    </label>

    <p v-if="sinClaude" class="error">
      {{ motivoClaude }} <RouterLink to="/config/claude">Configuración › Claude</RouterLink>.
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="ocupado" class="aviso">Hay una sesión en curso: espera a que termine.</p>
    <Button type="submit" label="Lanzar tanda" icon="pi pi-bolt" :loading="enviando"
      :disabled="ocupado || sinClaude || !defaults || (modo === 'vod' && !url.trim())" />
  </form>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; }
label { display: flex; flex-direction: column; gap: .3rem; font-size: .85rem; font-weight: 600; }
label small { font-weight: 400; opacity: .65; }
.error { color: #dc2626; margin: 0; }
.aviso { margin: 0; font-size: .85rem; opacity: .75; }
</style>
