import 'primeicons/primeicons.css';
import './styles.css';
import PrimeVue from 'primevue/config';
import ConfirmationService from 'primevue/confirmationservice';
import ToastService from 'primevue/toastservice';
import { createApp } from 'vue';
import App from './App.vue';
import { aplicar, eleccion } from './composables/useTheme';
import { router } from './router';
import { ClipeoPreset } from './theme';

const app = createApp(App);
app.use(PrimeVue, {
  theme: { preset: ClipeoPreset, options: { prefix: 'p', cssLayer: false, darkModeSelector: '.app-dark' } },
});
app.use(ConfirmationService);
app.use(ToastService);
app.use(router);
aplicar(eleccion.value);
app.mount('#app');
