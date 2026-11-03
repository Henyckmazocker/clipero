<script setup lang="ts">
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import InputText from 'primevue/inputtext';
import Message from 'primevue/message';
import Select from 'primevue/select';
import SelectButton from 'primevue/selectbutton';
import { computed, onMounted, ref } from 'vue';
import { api, mensajeError, type TandaDefaults } from '../../api';

const EDITORIALES = [
  { label: 'Mixta', value: 'mixta' },
  { label: 'Positiva', value: 'positiva' },
  { label: 'Crítica', value: 'critica' },
];
const f = ref<TandaDefaults>({ clips: 5, dias: 7, editorial: 'mixta', modelo: 'claude-opus-5-5', modelos: [] });
const nuevo = ref('');
const error = ref('');
const ok = ref(false);
const enviando = ref(false);

onMounted(async () => {
  try { f.value = await api.tandaConfig(); } catch (e) { error.value = mensajeError(e); }
});

const valido = computed(() => f.value.modelos.length > 0 && f.value.modelos.includes(f.value.modelo));

function anadir() {
  const m = nuevo.value.trim();
  if (m && !f.value.modelos.includes(m)) f.value.modelos.push(m);
  nuevo.value = '';
}
function quitar(i: number) {
  const [m] = f.value.modelos.splice(i, 1);
  if (m === f.value.modelo) f.value.modelo = f.value.modelos[0] ?? '';
}

async function guardar() {
  error.value = ''; ok.value = false; enviando.value = true;
  try {
    f.value = await api.guardarTandaConfig(f.value);
    ok.value = true;
  } catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}
</script>

<template>
  <div class="form">
    <label>Clips <small>Máximo por tanda (1-10).</small>
      <InputNumber v-model="f.clips" :min="1" :max="10" show-buttons fluid />
    </label>
    <label>Días <small>Ventana de <code>vods</code> (1-30).</small>
      <InputNumber v-model="f.dias" :min="1" :max="30" show-buttons fluid />
    </label>
    <label>Editorial
      <SelectButton v-model="f.editorial" :options="EDITORIALES" option-label="label" option-value="value" :allow-empty="false" />
    </label>
    <label>Modelo <small>Debe estar en la lista de abajo.</small>
      <Select v-model="f.modelo" :options="f.modelos" placeholder="Elige un modelo" />
    </label>
    <div class="modelos">
      <span class="tit">Modelos del selector</span>
      <div v-for="(m, i) in f.modelos" :key="m" class="fila">
        <span>{{ m }}</span>
        <Button icon="pi pi-times" severity="secondary" text rounded size="small" :aria-label="`Quitar ${m}`" @click="quitar(i)" />
      </div>
      <div class="fila">
        <InputText v-model="nuevo" placeholder="Nuevo modelo" @keyup.enter="anadir" />
        <Button icon="pi pi-plus" label="Añadir" severity="secondary" size="small" :disabled="!nuevo.trim()" @click="anadir" />
      </div>
    </div>
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <Message v-if="ok" severity="success" :closable="false">Valores de Tanda guardados.</Message>
    <div><Button label="Guardar" icon="pi pi-check" :loading="enviando" :disabled="!valido" @click="guardar" /></div>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; max-width: 40rem; }
label { display: flex; flex-direction: column; gap: .25rem; font-size: .85rem; }
label small { opacity: .65; }
.modelos { display: flex; flex-direction: column; gap: .3rem; font-size: .85rem; }
.tit { font-size: .85rem; }
.fila { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
</style>
