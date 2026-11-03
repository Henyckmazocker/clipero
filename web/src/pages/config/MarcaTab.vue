<script setup lang="ts">
import Button from 'primevue/button';
import ColorPicker from 'primevue/colorpicker';
import InputText from 'primevue/inputtext';
import Message from 'primevue/message';
import { computed, onMounted, ref } from 'vue';
import { api, mensajeError, type Branding } from '../../api';
import { marca } from '../../marca';

const vacia = (): Branding => ({ nombre: '', handle: '', lema: '', color: '#2A6FDB', marca_agua: '', linea_descripcion: '', hashtag: '' });
const f = ref<Branding>(vacia());
const error = ref('');
const ok = ref(false);
const enviando = ref(false);

onMounted(async () => {
  try { f.value = { ...vacia(), ...(await api.branding()) }; } catch (e) { error.value = mensajeError(e); }
});

// ColorPicker trabaja con «RRGGBB» sin almohadilla; el servidor y el InputText con «#RRGGBB».
const picker = computed({
  get: () => f.value.color.replace(/^#/, ''),
  set: (v: string) => { f.value.color = `#${String(v).toUpperCase()}`; },
});
const hexValido = computed(() => /^#[0-9A-Fa-f]{6}$/.test(f.value.color));

async function guardar() {
  error.value = ''; ok.value = false; enviando.value = true;
  try {
    const b = await api.guardarBranding(f.value);
    f.value = { ...vacia(), ...b };
    marca.value = { nombre: b.nombre, color: b.color };
    document.documentElement.style.setProperty('--marca', b.color);
    document.title = b.nombre ? `${b.nombre} · Clipero` : 'Clipero';
    ok.value = true;
  } catch (e) { error.value = mensajeError(e); } finally { enviando.value = false; }
}
</script>

<template>
  <div class="form">
    <label>Nombre <small>Nombre del canal; sale en el menú.</small>
      <InputText v-model="f.nombre" />
    </label>
    <label>Handle <em>informativo, no lo usa el render</em> <small>@ del canal en YouTube.</small>
      <InputText v-model="f.handle" />
    </label>
    <label>Lema <em>informativo, no lo usa el render</em> <small>Frase de la marca.</small>
      <InputText v-model="f.lema" />
    </label>
    <label>Color <small>Fondo del gancho y de la marca de agua; se guarda como 0xRRGGBB.</small>
      <span class="color">
        <ColorPicker v-model="picker" format="hex" />
        <InputText v-model="f.color" :invalid="!hexValido" maxlength="7" placeholder="#2A6FDB" style="width: 8rem" />
      </span>
    </label>
    <label>Marca de agua <small>Texto arriba a la izquierda, durante todo el clip.</small>
      <InputText v-model="f.marca_agua" />
      <span class="agua" :style="{ background: hexValido ? f.color : 'var(--marca)' }">{{ f.marca_agua || '—' }}</span>
    </label>
    <label>Línea de descripción <small>Última línea fija de la descripción del meta.md.</small>
      <InputText v-model="f.linea_descripcion" />
    </label>
    <label>Hashtag <small>Con # y sin espacios; se añade a los hashtags del meta.md.</small>
      <InputText v-model="f.hashtag" placeholder="#micanal" />
    </label>
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <Message v-if="ok" severity="success" :closable="false">Marca guardada.</Message>
    <div><Button label="Guardar" icon="pi pi-check" :loading="enviando" :disabled="!hexValido" @click="guardar" /></div>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: .9rem; max-width: 40rem; }
label { display: flex; flex-direction: column; gap: .25rem; font-size: .85rem; }
label small { opacity: .65; }
label em { font-size: .7rem; opacity: .7; }
.color { display: flex; align-items: center; gap: .6rem; }
.agua { align-self: flex-start; color: #fff; font-weight: 700; padding: .3rem .7rem; border-radius: 4px; font-size: .9rem; }
</style>
