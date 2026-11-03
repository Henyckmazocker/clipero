# CLAUDE.md — carpeta de trabajo de Clipero

Esta carpeta es tu espacio de trabajo de Clipero: pipeline local que saca Shorts verticales (20-59 s,
narrativa editada y subtítulos) de VODs de streamers. Nunca sube nada: la subida es del usuario.
El programa (`clipero`) está instalado aparte, en el PATH; aquí solo viven tus datos.

## Comandos

```bash
clipero ingest <url_vod>              # info + heatmap + chat (+ muted en Twitch) → data/vods/<id>/
clipero candidates <id>               # → data/vods/<id>/candidatos.json
clipero transcribe <id> [n…] [--force]  # audio de las ventanas → win/<n>.words.json + candidatos.md
clipero vods [--dias 7] [--fuentes a,b]  # VODs recientes de sources.yaml sin ingerir, ordenados por score
clipero render <short.yaml>           # valida, baja los tramos y escribe out/<fecha>/<slug>.mp4 + .meta.md
clipero clean [--dias 14]             # borra data/vods/*/seg/ más viejos de N días
clipero stats                         # publicados.csv → piloto.csv (métricas de lo subido)
clipero app [--port 8765] [--abrir]   # app local en http://127.0.0.1:8765
clipero init --actualizar             # refresca este CLAUDE.md y la skill tanda tras actualizar Clipero
```

La tanda diaria («tanda de hoy») la describe la skill `.claude/skills/tanda/SKILL.md`: léela y síguela entera.
El enfoque del texto de los shorts lo fija `linea-editorial.md` (en esta carpeta, es tuyo y `init --actualizar` no lo toca): la skill lo lee y lo aplica; sin él, no hay línea editorial.
`vod_id`: el de YouTube tal cual; el de Twitch es el numérico sin la `v` (`2909530977`).

## Modos de Claude

- **Terminal (siempre disponible):** abre `claude` en esta carpeta y di «tanda de hoy». Funciona sea
  cual sea `claude.modo` de `app.yaml`.
- **Desde la app** (Configuración › Claude), `claude.modo` puede ser `ninguno` (por defecto: la app no
  lanza tandas ni retoques), `api_key` (se paga por tokens; la clave va en `ANTHROPIC_API_KEY` o en
  `.clipero/credenciales`) o `suscripcion` (usa el `claude` que tengas instalado, con tu sesión).

## Carpetas

- `sources.yaml` — canales a rastrear (ampliable). `branding.yaml` — marca del canal (vacío = sin marca).
  `app.yaml` — valores por defecto de la app. `layouts/<fuente>.yaml` — encuadre de cada canal.
- `publicados.csv` — registro de lo subido (`fecha,slug,fuente,formato,tono,vod_id,start,end,url`;
  `tono` = critica | positivo | neutro). `piloto.csv` — métricas medidas por `stats`.
- `data/` — VODs ingeridos (`data/vods/<id>/`) y trabajo de render. `out/<fecha>/` — los shorts.
  `brand/` — avatar y banner opcionales. `.clipero/` — versión y herramientas de la carpeta.

## Trampas de uso

- YouTube sin `heatmap` → el VOD se descarta con aviso. Twitch solo usa chat. Si una fuente emite en
  ambas plataformas, se ingiere por Twitch.
- Los directos de YouTube sin `live_chat` dejan `chat.jsonl` vacío (se avisa).
- Twitch silencia tramos por DMCA (`muted.json`): las ventanas que los toquen se descartan.
- Nunca se baja el VOD entero: `ingest` no descarga vídeo; `transcribe` y `render` bajan solo los tramos.
- Usa siempre `127.0.0.1` y no `localhost` para la app.
- Una tanda desde la terminal y otra desde la app no deben lanzarse a la vez.
