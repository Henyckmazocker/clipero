import { ref } from 'vue';

export type Eleccion = 'sistema' | 'claro' | 'oscuro';
const KEY = 'clipero-tema';

export const eleccion = ref<Eleccion>((localStorage.getItem(KEY) as Eleccion) || 'sistema');

export function aplicar(e: Eleccion) {
  const oscuro = e === 'oscuro' || (e === 'sistema' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('app-dark', oscuro);
}

export function elegir(e: Eleccion) {
  eleccion.value = e;
  localStorage.setItem(KEY, e);
  aplicar(e);
}

matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => aplicar(eleccion.value));
