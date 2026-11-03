import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/clips' },
    { path: '/clips', name: 'clips', component: () => import('./pages/ClipsPage.vue') },
    { path: '/rendimiento', name: 'rendimiento', component: () => import('./pages/RendimientoPage.vue') },
    { path: '/tanda', name: 'tanda', component: () => import('./pages/TandaPage.vue') },
    {
      path: '/config', component: () => import('./pages/ConfigPage.vue'), redirect: '/config/canales',
      children: [
        { path: 'canales', name: 'config-canales', component: () => import('./pages/config/CanalesTab.vue') },
        { path: 'marca', name: 'config-marca', component: () => import('./pages/config/MarcaTab.vue') },
        { path: 'layouts/:fuente?', name: 'config-layouts', component: () => import('./pages/config/LayoutsTab.vue') },
        { path: 'tanda', name: 'config-tanda', component: () => import('./pages/config/TandaTab.vue') },
        { path: 'claude', name: 'config-claude', component: () => import('./pages/config/ClaudeTab.vue') },
      ],
    },
    { path: '/:resto(.*)*', redirect: '/clips' },
  ],
});
