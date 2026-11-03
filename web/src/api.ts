// Cliente tipado contra los contratos HTTP del plan (M1: salud, fuentes, marca · M2: clips).
export type Fuente = { id: string; nombre: string };
export type Marca = { nombre: string; color: string | null };
export type Tono = 'critica' | 'positivo' | 'neutro';
export type Publicado = { fecha: string; url: string; claim: boolean };
export type Version = {
  slug: string; n: number; fecha: string;
  fuente: string | null; formato: string | null; tono: Tono | null;
  duracion_s: number | null; encuadre: string | null; avisos: string[];
  titulo: string; descripcion: string; hashtags: string;
  editable: boolean;
  publicado: Publicado | null;
  mp4: string; thumb: string; mtime: number;
};
export type ClipGroup = { base: string; fecha: string; fuente: string | null; versiones: Version[] };
export type FiltrosClips = {
  fuente?: string; tono?: string; formato?: string; desde?: string; hasta?: string; publicado?: string;
};
export type PublicadoRend = {
  slug: string; fecha: string; fuente: string; tono: string; formato: string; url: string; claim: boolean;
  dias: number; vistas: number | null; likes: number | null; comentarios: number | null; thumb: string | null;
};
export type Agregado = { shorts: number; media: number; mediana: number };
export type Rendimiento = {
  ultima_medida: string | null;
  publicados: PublicadoRend[];
  series: Record<string, Array<{ dia: number; vistas: number }>>;
  agregados: Record<'tono' | 'fuente' | 'formato' | 'dow', Record<string, Agregado>>;
  canal: { vistas_total: number; suscriptores: Array<{ fecha: string; n: number }>;
           por_semana: Array<{ semana: string; n: number; objetivo: 21 }> };
};
export type EstadoMedidor = { midiendo: boolean; ultima: string | null; error: string | null };
export type Overrides = { tono?: string; fuente?: string; formato?: string };
export type Canal = { id: string; nombre: string; tamaño: 'grande' | 'mediano'; twitch?: string; youtube?: string; credito: string };
export type Canales = { activos: Canal[]; reserva: Canal[] };
export type Prueba = { ok: boolean; vods: number; error: string | null };
export type PruebaCanal = { twitch: Prueba | null; youtube: Prueba | null };
export type Branding = {
  nombre: string; handle?: string; lema?: string; color: string; marca_agua?: string;
  linea_descripcion?: string; hashtag?: string;
};
export type Rect = { x: number; y: number; w: number; h: number };
export type Escena = { facecam?: Rect; juego?: Rect; ancho?: true; cara?: true };
export type Layout = {
  entrada: string; facecam?: Rect; juego?: Rect; escenas?: Record<string, Escena>; [k: string]: unknown;
};
export type LayoutFila = { fuente: string; nombre: string; canal: boolean; excepciones: string[] };
export type Tramo = { seg: string; start: number; end: number; offset: number; w: number | null; h: number | null };
export type VodLayout = { vod: string; plataforma: string; fecha: string; titulo: string; tramos: Tramo[] };
export type ResultadoProbar = { score: number; umbral: number; detecta: boolean; aviso?: string };

export type TandaIn = {
  fuentes: string[]; vod_url: string | null; clips: number;
  editorial: 'mixta' | 'positiva' | 'critica'; dias: number; modelo: string; nota: string;
};
export type TandaDefaults = { clips: number; dias: number; editorial: TandaIn['editorial']; modelo: string; modelos: string[] };
export type ModoClaude = 'ninguno' | 'api_key' | 'suscripcion';
export type ConfigClaude = {
  modo: ModoClaude; disponibles: { api_key: boolean; suscripcion: boolean };
  clave: { puesta: boolean; origen: 'entorno' | 'fichero' | null }; claude_cli: string | null;
};
export type EstadoRun = 'en_curso' | 'ok' | 'error' | 'detenida' | 'interrumpida';
export type RunParams = Partial<TandaIn> & { fecha?: string; slug?: string; destino?: string; peticion?: string };
export type RunJson = {
  id: string; tipo: 'tanda' | 'retoque'; estado: EstadoRun; creado: string; terminado: string | null;
  modelo: string; params: RunParams; canal_creado: { id: string; nombre: string; credito: string } | null;
  fase: string | null; session_id: string | null; eventos: number;
  resultado: { shorts: Array<{ fecha: string; slug: string }>; coste_usd: number | null; error: string | null };
};
export type Evento = {
  i: number; t: string; tipo: 'texto' | 'herramienta' | 'salida' | 'fase' | 'denegado' | 'fin';
  texto?: string; nombre?: string; resumen?: string; error?: boolean; fase?: string; motivo?: string; estado?: string;
};
export type LecturaRun = { run: RunJson; eventos: Evento[]; siguiente: number };

export class ApiError extends Error {
  constructor(public status: number, public codigo: string, public detalle?: string[], public run?: string | null) {
    super(`${status} ${codigo}`);
  }
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(ruta, init);
  if (!r.ok) {
    let codigo = 'error';
    let detalle: string[] | undefined;
    let run: string | null | undefined;
    try {
      const j = await r.json();
      codigo = j.error ?? (typeof j.detail === 'string' ? 'claude_no_disponible' : codigo);
      detalle = Array.isArray(j.detalle) ? j.detalle : typeof j.detalle === 'string' ? [j.detalle]
        : typeof j.detail === 'string' ? [j.detail] : undefined;
      run = j.run;
    } catch { /* sin cuerpo */ }
    throw new ApiError(r.status, codigo, detalle, run);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

const get = <T>(ruta: string) => pedir<T>(ruta);
const enviar = <T>(metodo: string, ruta: string, cuerpo?: unknown) =>
  pedir<T>(ruta, {
    method: metodo,
    ...(cuerpo === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) }),
  });
const ruta = (c: { fecha: string; slug: string }) => `/api/clips/${c.fecha}/${c.slug}`;

const layoutRuta = (fuente: string, vod?: string) =>
  `/api/layouts/${encodeURIComponent(fuente)}${vod ? `/${encodeURIComponent(vod)}` : ''}`;
export const urlFotograma = (vod: string, seg: string, t: number) =>
  `/api/frame/${encodeURIComponent(vod)}/${encodeURIComponent(seg)}.jpg?t=${t}`;

const canalRuta = (id: string) => `/api/config/canales/${encodeURIComponent(id)}`;

export const api = {
  salud: () => get<{ ok: boolean }>('/api/salud'),
  fuentes: () => get<Fuente[]>('/api/fuentes'),
  marca: () => get<Marca>('/api/marca'),
  clips: (f: FiltrosClips) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v) q.set(k, v);
    return get<ClipGroup[]>(`/api/clips?${q}`);
  },
  rendimiento: () => get<Rendimiento>('/api/rendimiento'),
  estadoMedidor: () => get<EstadoMedidor>('/api/stats/estado'),
  medir: () => pedir<{ estado: string }>('/api/stats/medir', { method: 'POST' }),
  borrar: (v: Version) => pedir<void>(ruta(v), { method: 'DELETE' }),
  abrirCarpeta: (v: Version) => pedir<void>(`${ruta(v)}/abrir-carpeta`, { method: 'POST' }),
  claim: (v: Version) => pedir<void>(`${ruta(v)}/claim`, { method: 'POST' }),
  publicar: (v: Version, url: string, o: Overrides) =>
    pedir<{ fila: Record<string, string> }>(`${ruta(v)}/publicar`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, ...o }),
    }),
  canales: () => get<Canales>('/api/config/canales'),
  altaCanal: (c: Canal) => enviar<Canal>('POST', '/api/config/canales', c),
  editarCanal: (c: Canal) => enviar<Canal>('PUT', canalRuta(c.id), c),
  canalAReserva: (id: string) => enviar<Canales>('POST', `${canalRuta(id)}/reserva`),
  reactivarCanal: (id: string) => enviar<Canales>('POST', `${canalRuta(id)}/reactivar`),
  probarCanal: (c: Canal) => enviar<PruebaCanal>('POST', '/api/config/canales/probar', c),
  branding: () => get<Branding>('/api/config/marca'),
  layouts: () => get<LayoutFila[]>('/api/layouts'),
  layout: (fuente: string, vod?: string) => get<Layout>(layoutRuta(fuente, vod)),
  guardarLayout: (fuente: string, vod: string | undefined, l: Layout) => enviar<Layout>('PUT', layoutRuta(fuente, vod), l),
  borrarLayout: (fuente: string, vod?: string) => enviar<void>('DELETE', layoutRuta(fuente, vod)),
  layoutVods: (fuente: string) => get<VodLayout[]>(`${layoutRuta(fuente)}/vods`),
  probarLayout: (layout: Layout, vod: string, seg: string, t: number) =>
    enviar<ResultadoProbar>('POST', '/api/layouts/probar', { layout, vod, seg, t }),
  tandaDefaults: () => get<TandaDefaults>('/api/tandas/defaults'),
  lanzarTanda: (t: TandaIn) =>
    enviar<{ id: string; canal_creado: RunJson['canal_creado'] }>('POST', '/api/tandas', t),
  retocar: (c: { fecha: string; slug: string }, peticion: string, modelo?: string) =>
    enviar<{ id: string; destino: string }>('POST', `${ruta(c)}/retoque`, { peticion, ...(modelo ? { modelo } : {}) }),
  runs: () => get<RunJson[]>('/api/runs'),
  runActual: () => get<RunJson | null>('/api/runs/actual'),
  run: (id: string, desde = 0) => get<LecturaRun>(`/api/runs/${encodeURIComponent(id)}?desde=${desde}`),
  detener: (id: string) => enviar<{ estado: string }>('POST', `/api/runs/${encodeURIComponent(id)}/detener`),
  tandaConfig: () => get<TandaDefaults>('/api/config/tanda'),
  guardarTandaConfig: (t: TandaDefaults) => enviar<TandaDefaults>('PUT', '/api/config/tanda', t),
  claudeConfig: () => get<ConfigClaude>('/api/config/claude'),
  guardarClaude: (modo: ModoClaude, api_key?: string) =>
    enviar<ConfigClaude>('PUT', '/api/config/claude', { modo, ...(api_key === undefined ? {} : { api_key }) }),
  guardarBranding: (b: Branding) => enviar<Branding>('PUT', '/api/config/marca', b),
};

export const ERRORES: Record<string, string> = {
  url: 'La URL tiene que ser de YouTube (Shorts, watch o youtu.be).',
  tono: 'Elige el tono.', fuente: 'Elige la fuente.', formato: 'Elige el formato.',
  ya_publicado: 'Esta versión ya está publicada.', publicado: 'Esta versión está publicada: no se puede borrar ni retocar.',
  no_publicado: 'Esta versión aún no está publicada.', no_encontrado: 'No se encuentra el clip.',
  ya_midiendo: 'Ya hay una medición en curso.',
  id_repetido: 'Ya hay un canal con ese id (en activos o en reserva).',
  invalido: 'Hay datos no válidos.',
  sin_layout: 'Este canal no tiene layout.',
  sin_escena_detectable: 'El layout plano no tiene escena detectable: activa «Con escenas» para probar la detección.',
  fuera_de_tramo: 'Ese segundo queda fuera del tramo.',
  ffmpeg: 'ffmpeg no pudo sacar el fotograma.', fotograma: 'No se pudo leer el fotograma.',
  sin_yaml: 'Esta versión no tiene short.yaml: no se puede retocar.',
  ocupado: 'Ya hay una sesión en curso: espera a que termine.',
  vod_invalido: 'No se pudo leer ese VOD.',
  canal_no_creable: 'No se pudo crear el canal del VOD: dalo de alta en Configuración › Canales.',
  no_en_curso: 'Esa sesión ya no está en curso.',
  tanda_en_curso: 'Hay una sesión en curso: no se puede medir ahora.',
  modo_desconocido: 'Modo de Claude desconocido.',
  modo_no_disponible: 'Ese modo de Claude no está disponible.',
  cabecera: 'La cabecera de publicados.csv no es la esperada: no se ha escrito nada.',
};
export const mensajeError = (e: unknown) => {
  if (!(e instanceof ApiError)) return 'No se pudo conectar con el servidor.';
  const base = ERRORES[e.codigo] ?? `Error ${e.status}`;
  if (e.codigo === 'claude_no_disponible' && e.detalle?.length) return e.detalle[0];
  return ['invalido', 'vod_invalido', 'canal_no_creable', 'modo_no_disponible'].includes(e.codigo) && e.detalle?.length ? `${base} ${e.detalle.join(' · ')}` : base;
};
