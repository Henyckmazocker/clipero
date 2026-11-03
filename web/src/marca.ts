import { ref } from 'vue';
import type { Marca } from './api';

export const marca = ref<Marca>({ nombre: 'Clipero', color: null });
