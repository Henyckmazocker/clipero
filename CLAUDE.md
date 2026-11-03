# CLAUDE.md — clipero

Pipeline local que saca Shorts verticales (20-59 s, narrativa editada y subtítulos) de VODs de
streamers hispanos. Python 3.12 en `.venv`, CLI única `clipero` (`argparse`, sin frameworks).
Nunca sube nada: la subida es del usuario. Este `CLAUDE.md` es para quien desarrolla el proyecto; el que recibe el usuario final está en `clipero/plantilla/CLAUDE.md`.

**Carpeta de trabajo:** el código vive en este checkout, pero los datos (`data/`, `out/`, `sources.yaml`,
`branding.yaml`, `app.yaml`, `layouts/`, `publicados.csv`, `piloto.csv`, `brand/`) viven en la carpeta de trabajo
(por defecto `~/Clipero`; `CLIPERO_HOME`, también `--home DIR` o `~/.config/clipero/home`, en ese orden de prioridad). La
terminal de tanda se abre **en la carpeta de trabajo**, no en el repo (ahí están el `CLAUDE.md` y la skill que
copia `clipero init`). Se crea con `clipero init [DIR]`; `clipero init --actualizar` refresca allí
`CLAUDE.md`, la skill y `examples/` desde `clipero/plantilla/`. Cualquier comando sin `<home>/.clipero/version`
termina con «no hay carpeta de trabajo…».

## Comandos

```bash
make tools                          # el .onnx de YuNet a clipero/recursos/models/ y `clipero setup` (idempotente)
.venv/bin/pip install -e .[dev]     # instala el paquete y pytest
.venv/bin/pytest -q
# Los comandos corren con `CLIPERO_HOME` apuntando a la carpeta de trabajo (por defecto ~/Clipero)
.venv/bin/clipero init [DIR] [--actualizar]  # crea la carpeta de trabajo desde clipero/plantilla/ (nunca sobrescribe)
.venv/bin/clipero setup [--forzar]  # baja a <home>/.clipero/bin/ ffmpeg+ffprobe (si no están en el PATH), deno y TwitchDownloaderCLI, y precarga Whisper small
.venv/bin/clipero doctor            # tabla herramienta · ruta · versión · ✓/✗ y modo de Claude; código 1 si falta algo obligatorio
.venv/bin/clipero ingest <url_vod>  # info + heatmap + chat (+ muted en Twitch) → data/vods/<id>/
.venv/bin/clipero candidates <id>   # → data/vods/<id>/candidatos.json
.venv/bin/clipero transcribe <id> [n…] [--force]  # audio de las ventanas → win/<n>.words.json + candidatos.md
.venv/bin/clipero vods [--dias 7] [--fuentes a,b]   # VODs recientes de sources.yaml sin ingerir, ordenados por score (repercusión vs su canal × recencia; solo metadatos)
.venv/bin/clipero clean [--dias 14] # borra data/vods/*/seg/ más viejos de N días
.venv/bin/clipero stats [--publicados publicados.csv] [--piloto piloto.csv]  # yt-dlp -j de cada url → piloto.csv
.venv/bin/pip install -e .[dev,app] # extra `app`: fastapi + uvicorn + httpx + ruamel.yaml + claude-agent-sdk

.venv/bin/clipero app [--port 8765] [--abrir] # servidor de la app de escritorio en 127.0.0.1 (sin el extra `app` el resto de la CLI sigue funcionando)
make app                            # compila el frontend (cd web && npm ci && npm run build → clipero/app/static, dentro del paquete); necesita node (nvm)
.venv/bin/clipero app --host 0.0.0.0  # por defecto 127.0.0.1; 0.0.0.0 solo dentro de Docker (la API no tiene autenticación)
mkdir -p ~/Clipero && docker build -t clipero . && docker run -d --name clipero --user "$(id -u):$(id -g)" -p 127.0.0.1:8765:8765 -v ~/Clipero:/datos clipero  # sin --user (y sin crear antes ~/Clipero) los ficheros quedan de root; única vía de instalación; imagen: ffmpeg + deno + TDL + Whisper; /datos = CLIPERO_HOME (WORKDIR); publicar solo en 127.0.0.1
docker exec -i --user "$(id -u):$(id -g)" clipero clipero doctor  # el CLI dentro del contenedor (docker exec no pasa por el ENTRYPOINT)
```

La tanda diaria (`tanda de hoy`) la describe la skill `.claude/skills/tanda/SKILL.md`: léela y síguela entera.

`render <short.yaml>` valida, baja los tramos a `data/vods/<id>/seg/` y escribe `out/<fecha>/<slug>.mp4` + `.meta.md`. `stats` mide también las URL con sufijo `#claim` (columna `claim`=1 en `piloto.csv`).
`vod_id`: el de YouTube tal cual; el de Twitch es el numérico sin la `v` (`2909530977`).

## Estructura

- `clipero/herramientas.py` — `ruta(nombre)` (`.clipero/bin` → PATH), `ytdlp()` (`python -m yt_dlp --js-runtimes deno:…`), `setup`/`doctor`; versiones y sha256 fijados. `clipero/sistema.py` — `notificar`/`abrir` (solo Linux: `notify-send`/`xdg-open`).
- `clipero/ingest.py` — yt-dlp -j, heatmap, chat de YouTube (`live_chat`) o Twitch (TwitchDownloaderCLI), `muted.json`.
- `clipero/score.py` — puntuación por plataforma, ventanas pico −90 s / +30 s, descartes.
- `clipero/fetch.py` — `fetch_section(vod_id, plataforma, start, end, out, audio_only) -> (ruta, offset_real)`; Twitch por segmentos HLS, YouTube por `--download-sections`.
- `clipero/transcribe.py` — faster-whisper `small` int8 por ventana (words.json en s del VOD) y `candidatos.md`.
- `clipero/sources.py` — `vods` (flat-playlist + `-j` hasta salir de la ventana) y `clean`. `clipero/stats.py` — `publicados.csv` → `piloto.csv` y tabla de vistas por `tono`.
- `sources.yaml` — canales a rastrear (10, ampliable por el usuario). `publicados.csv` — registro de lo subido (`fecha,slug,fuente,formato,tono,vod_id,start,end,url`; `tono` = critica | positivo | neutro, lo apunta el usuario al subir).
- `clipero/app/` — app de escritorio: `server.py` (FastAPI: `/api/*`, `/media/out/…` con `Range`, estáticos de `clipero/app/static` (build de `web/`) con fallback a `index.html`), `clips.py` (escanea `out/`, versiones `-vN`, miniaturas en `data/app/thumbs/`), `publicar.py` (fila de `publicados.csv` desde el yaml, claim), `rendimiento.py` (series, agregados por tono/fuente/formato/día y totales desde `piloto.csv` + `publicados.csv`; usa `stats.resumen_por`), `medidor.py` (el servicio lanza `stats` al arrancar y cada 6 h si `piloto.csv` no tiene filas de hoy; botón «Medir ahora»; no mide si hay sesión en curso). `sesiones.py` (tandas y retoques `-vN` lanzados desde la app con el Agent SDK de Python, una sesión a la vez; historial en `data/runs/<id>/{run.json,eventos.jsonl}`; fases deducidas de los `clipero <cmd>`; `notify-send` al terminar; reiniciar el servicio deja `interrumpida` la sesión en curso). `layouts.py` (VODs/tramos con `seg/`, fotograma en `data/app/frames/` purgado a los 14 días, CRUD de layouts con fusión ruamel, «Probar detección» con `edge_score`). `/config` (Canales · Marca · Layouts · Tanda) sale de `/api/config/*`, `/api/layouts*` y `/api/frame`. `web/` — Vue 3 + Vite + TS + PrimeVue 4 (`npm run dev` hace proxy de `/api` y `/media` a `127.0.0.1:8765`).
- `app.yaml` — defaults del formulario de Tanda y lista de modelos (los edita Configuración › Tanda; sin él, constantes). `clipero/config.py` — lee/escribe `sources.yaml`, `branding.yaml` y `app.yaml` con ruamel (comentarios intactos, escritura atómica, validación) y la reserva de canales; solo lo usa la app.
- `layouts/<fuente>.yaml` — layout del canal; `layouts/<fuente>/<vod>.yaml` — excepción de un VOD (copia completa), la que `frame.load_layout(fuente, vod=)` busca primero; `render` registra `layout <ruta>` en el log.
- `Dockerfile` + `deploy/docker-entrypoint.sh` (hace `init /datos` si falta `.clipero/version`; los binarios y Whisper viven en `/opt/clipero/.clipero` con `CLIPERO_WHISPER_DIR`, no en el volumen). `.github/workflows/{ci,release}.yml` (release en tags `v*`: un solo job que comprueba tag = `v<version>` salvo `-rc`, publica la imagen amd64+arm64 en ghcr.io y crea la GitHub Release con notas; solo imagen, sin paquete en índices).
- `data/` (spike del M0 incluido), `out/`, `bin/`, `.venv/`, `clipero/app/static/` — en `.gitignore`.

## Trampas

- `av<17` obligatorio: faster-whisper 1.2.1 se rompe con `av` 19.
- Algunos directos de YouTube (p. ej. los de Ibai) no traen `live_chat`: `chat.jsonl` queda vacío y se avisa. El `heatmap` existe según el vídeo.
- YouTube sin `heatmap` → VOD descartado con aviso. Twitch solo usa chat. Si una fuente emite en ambas, se ingiere por Twitch.
- Twitch silencia tramos por DMCA (`-muted` en la playlist HLS): `muted.json`, y `score.py` descarta las ventanas que los toquen.
- `yt-dlp --download-sections` falla en Twitch (ficheros de 258 B): los tramos se bajan por segmentos HLS (M2).
- Montserrat no está instalada en el sistema: `clipero/recursos/fonts/` (dentro del paquete, fuera de `home()`), con `fontsdir=<ruta absoluta escapada>` en el filtro `ass`; el modelo YuNet vive en `clipero/recursos/models/`.
- Siempre `127.0.0.1`, nunca `localhost` (puede resolver a `::1` y uvicorn solo escucha en IPv4).
- ruamel solo en la app; la reserva de `sources.yaml` (desde `# Reserva`) se trata como texto, porque ruamel la cuelga del último canal y se perdería al borrarlo. `render` y `vods` siguen con PyYAML.
- Nunca bajar el VOD entero; ingest no descarga vídeo.
- Una tanda lanzada desde la app (página Tanda) llega con un bloque `<parametros_tanda>` que `SKILL.md` interpreta; no hay cerrojo con la terminal, así que no lances las dos a la vez. Un VOD de un canal desconocido lo da de alta, activo, en `sources.yaml`.
