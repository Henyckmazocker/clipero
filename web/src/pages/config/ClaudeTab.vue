<script setup lang="ts">
import Button from 'primevue/button';
import Message from 'primevue/message';
import Password from 'primevue/password';
import RadioButton from 'primevue/radiobutton';
import { computed, onMounted, ref } from 'vue';
import { api, mensajeError, type ConfigClaude, type ModoClaude } from '../../api';

// Coste orientativo de una tanda con API key. Se mide en el primer uso (coste_usd de run.json): cámbialo aquí.
const COSTE_TANDA = 'del orden de unos dólares; se mide en el primer uso';

const cfg = ref<ConfigClaude | null>(null);
const modo = ref<ModoClaude>('ninguno');
const clave = ref('');
const error = ref('');
const ok = ref('');
const enviando = ref(false);

function aplicar(c: ConfigClaude) { cfg.value = c; modo.value = c.modo; }
onMounted(async () => {
  try { aplicar(await api.claudeConfig()); } catch (e) { error.value = mensajeError(e); }
});

const opciones = computed(() => {
  const c = cfg.value;
  return [
    { v: 'ninguno' as const, etiqueta: 'Sin Claude', ayuda: 'La app no lanza tandas ni retoques. Puedes seguir usando Claude desde la terminal.',
      libre: true, porque: '' },
    { v: 'api_key' as const, etiqueta: 'API key de Anthropic', ayuda: 'Se paga por tokens a la cuenta de la clave.',
      libre: !!c?.disponibles.api_key, porque: 'Falta la clave: pon una abajo o define ANTHROPIC_API_KEY.' },
    { v: 'suscripcion' as const, etiqueta: 'Claude (tu suscripción, con tu Claude Code instalado)',
      ayuda: c?.claude_cli ? `Usa el \`claude\` de ${c.claude_cli}, con la sesión que iniciaste tú.` : 'Usa el `claude` que tengas instalado, con la sesión que iniciaste tú.',
      libre: !!c?.disponibles.suscripcion, porque: 'No hay `claude` en el PATH: instálalo e inicia sesión en una terminal.' },
  ];
});
const origen = computed(() => cfg.value?.clave.origen === 'entorno' ? 'de la variable ANTHROPIC_API_KEY' : 'del fichero de credenciales');

async function guardarModo() {
  error.value = ''; ok.value = ''; enviando.value = true;
  try { aplicar(await api.guardarClaude(modo.value)); ok.value = 'Modo guardado.'; }
  catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}
async function guardarClave(borrar: boolean) {
  error.value = ''; ok.value = ''; enviando.value = true;
  try {
    // la clave no se devuelve nunca: solo se sabe si está puesta; el modo elegido se mantiene tal cual
    aplicar(await api.guardarClaude(cfg.value?.modo ?? 'ninguno', borrar ? '' : clave.value.trim()));
    clave.value = ''; ok.value = borrar ? 'Clave borrada.' : 'Clave guardada.';
  } catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}
</script>

<template>
  <div class="form">
    <p class="intro">Con qué Claude lanza la app las tandas y los retoques. Desde la terminal siempre puedes abrir
      <code>claude</code> en la carpeta de trabajo y decir «tanda de hoy», sea cual sea el modo.</p>

    <div v-for="o in opciones" :key="o.v" class="opcion" :class="{ off: !o.libre }">
      <RadioButton v-model="modo" :input-id="`m-${o.v}`" name="modo" :value="o.v" :disabled="!o.libre || enviando" />
      <label :for="`m-${o.v}`">{{ o.etiqueta }}
        <small>{{ o.ayuda }}</small>
        <small v-if="!o.libre" class="porque">No disponible. {{ o.porque }}</small>
      </label>
    </div>
    <div><Button label="Guardar modo" icon="pi pi-check" :loading="enviando" :disabled="!cfg || modo === cfg.modo" @click="guardarModo" /></div>

    <h3>API key</h3>
    <Message severity="warn" :closable="false">
      La API key se paga por tokens, aparte de cualquier suscripción: una tanda cuesta {{ COSTE_TANDA }}.
    </Message>
    <p v-if="cfg?.clave.puesta" class="estado"><i class="pi pi-check-circle" /> Hay una clave puesta ({{ origen }}).</p>
    <p v-else class="estado">No hay clave.</p>
    <label>Nueva clave <small>Se guarda en <code>.clipero/credenciales</code> (solo tú puedes leerla) y no se vuelve a mostrar.</small>
      <Password v-model="clave" :feedback="false" toggle-mask autocomplete="off" placeholder="sk-ant-…" fluid />
    </label>
    <div class="botones">
      <Button label="Guardar" icon="pi pi-save" :loading="enviando" :disabled="!clave.trim()" @click="guardarClave(false)" />
      <Button label="Borrar" icon="pi pi-trash" severity="secondary" :disabled="enviando || cfg?.clave.origen !== 'fichero'" @click="guardarClave(true)" />
    </div>
    <small v-if="cfg?.clave.origen === 'entorno'" class="porque">La variable de entorno manda sobre el fichero: para quitarla, cambia el entorno donde corre la app.</small>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <Message v-if="ok" severity="success" :closable="false">{{ ok }}</Message>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; max-width: 40rem; }
.intro { margin: 0; font-size: .9rem; opacity: .85; }
.opcion { display: flex; gap: .6rem; align-items: flex-start; }
.opcion.off { opacity: .6; }
.opcion label { display: flex; flex-direction: column; gap: .15rem; font-size: .9rem; font-weight: 600; }
label small { font-weight: 400; opacity: .7; font-size: .8rem; }
.porque { color: #b45309; opacity: 1; }
h3 { margin: .5rem 0 0; font-size: 1rem; }
.estado { margin: 0; font-size: .85rem; }
.botones { display: flex; gap: .5rem; }
</style>
