import { computed, ref } from 'vue';
import { api, type ConfigClaude } from '../api';

/** Estado de Configuración › Claude para saber si se puede lanzar una sesión (tanda o retoque).
 *  Mientras no se sabe (cargando o sin respuesta) no bloquea: el servidor responde 409 igualmente. */
export function useClaude() {
  const cfg = ref<ConfigClaude | null>(null);

  async function cargar() {
    try { cfg.value = await api.claudeConfig(); } catch { cfg.value = null; }
  }

  const motivo = computed(() => {
    const c = cfg.value;
    if (!c) return '';
    if (c.modo === 'ninguno') return 'Claude está desactivado: elige un modo en';
    if (!c.disponibles[c.modo]) {
      return c.modo === 'api_key' ? 'El modo API key no tiene clave: ponla en'
        : 'El modo suscripción no encuentra `claude` en el PATH: revísalo en';
    }
    return '';
  });
  return { cfg, cargar, motivo, bloqueado: computed(() => motivo.value !== '') };
}
