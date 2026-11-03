<script setup lang="ts">
import Button from 'primevue/button';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Message from 'primevue/message';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api, mensajeError, type Canal, type Canales } from '../../api';
import CanalDialog from '../../components/CanalDialog.vue';

const router = useRouter();
const datos = ref<Canales>({ activos: [], reserva: [] });
const error = ref('');
const dialogo = ref(false);
const editando = ref<Canal | null>(null);

async function cargar() {
  try { datos.value = await api.canales(); error.value = ''; } catch (e) { error.value = mensajeError(e); }
}
onMounted(cargar);

const nuevo = () => { editando.value = null; dialogo.value = true; };
const editar = (c: Canal) => { editando.value = c; dialogo.value = true; };

async function mover(accion: 'canalAReserva' | 'reactivarCanal', c: Canal) {
  try { datos.value = await api[accion](c.id); error.value = ''; } catch (e) { error.value = mensajeError(e); }
}
const reservaA = (c: Canal) => {
  if (confirm(`¿Mandar «${c.nombre}» a la reserva? Pasa a un bloque comentado de sources.yaml.`)) mover('canalAReserva', c);
};
</script>

<template>
  <div class="cab">
    <h2>Canales activos</h2>
    <Button label="Nuevo canal" icon="pi pi-plus" @click="nuevo" />
  </div>
  <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
  <DataTable :value="datos.activos" data-key="id" size="small">
    <Column field="id" header="Id" />
    <Column field="nombre" header="Nombre" />
    <Column field="tamaño" header="Tamaño" />
    <Column field="twitch" header="Twitch" />
    <Column header="YouTube"><template #body="{ data }">{{ data.youtube ? '✓' : '' }}</template></Column>
    <Column header="" style="width: 17rem">
      <template #body="{ data }">
        <div class="acciones">
          <Button label="Editar" icon="pi pi-pencil" size="small" text @click="editar(data)" />
          <Button label="Layout" icon="pi pi-th-large" size="small" text @click="router.push(`/config/layouts/${data.id}`)" />
          <Button label="A reserva" icon="pi pi-inbox" size="small" text severity="secondary" @click="reservaA(data)" />
        </div>
      </template>
    </Column>
  </DataTable>

  <h2>Reserva</h2>
  <DataTable :value="datos.reserva" data-key="id" size="small">
    <template #empty>La reserva está vacía.</template>
    <Column field="id" header="Id" />
    <Column field="nombre" header="Nombre" />
    <Column field="twitch" header="Twitch" />
    <Column header="" style="width: 9rem">
      <template #body="{ data }">
        <Button label="Reactivar" icon="pi pi-replay" size="small" text @click="mover('reactivarCanal', data)" />
      </template>
    </Column>
  </DataTable>

  <CanalDialog v-model:visible="dialogo" :canal="editando" @guardado="cargar" />
</template>

<style scoped>
.cab { display: flex; align-items: center; justify-content: space-between; }
h2 { font-size: 1.1rem; margin: 1rem 0 .5rem; }
.acciones { display: flex; gap: .25rem; }
</style>
