import Aura from '@primevue/themes/aura';
import { definePreset } from '@primevue/themes';

// Aura con primario neutro-azulado; la marca del canal se aplica como --marca (ver App.vue).
export const ClipeoPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{zinc.50}', 100: '{zinc.100}', 200: '{zinc.200}', 300: '{zinc.300}', 400: '{zinc.400}',
      500: '{zinc.500}', 600: '{zinc.600}', 700: '{zinc.700}', 800: '{zinc.800}', 900: '{zinc.900}', 950: '{zinc.950}',
    },
  },
});
