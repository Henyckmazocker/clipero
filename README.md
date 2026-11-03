# Clipero

Pipeline local que saca Shorts verticales (20-59 s, narrativa editada y subtítulos quemados) a partir
de VODs de streamers hispanos de Twitch y YouTube. Puntúa el chat y el heatmap para encontrar los
momentos fuertes, transcribe con Whisper, deja que Claude elija y escriba cada short (opcional) y
renderiza el vídeo con ffmpeg. Trae una app web local para revisar los clips, medir el rendimiento y
configurar canales, marca y layouts.

**Clipero no sube nada.** Deja los `.mp4` y un `.meta.md` con título, descripción y hashtags en
`out/<fecha>/`; subirlos es cosa tuya.

Licencia: AGPL-3.0-or-later (ver `LICENSE`; el software de terceros está en `THIRD_PARTY.md`).

## Instalación (Docker)

La única vía de instalación es la imagen Docker (Linux x64 y arm64; la imagen ya trae ffmpeg, deno,
TwitchDownloaderCLI y Whisper):

```bash
mkdir -p ~/Clipero   # antes del docker run: si no existe, Docker la crea como root
docker run -d --name clipero --restart unless-stopped \
  --user "$(id -u):$(id -g)" -p 127.0.0.1:8765:8765 -v ~/Clipero:/datos \
  ghcr.io/henyckmazocker/clipero
```

Abre <http://127.0.0.1:8765>. `/datos` es la carpeta de trabajo (la imagen la crea con `clipero init`
si está vacía) y es el directorio de trabajo del contenedor. **La API de la app no tiene
autenticación**, y desde ella se puede cambiar hasta la API key: publica el puerto **solo en
`127.0.0.1`**, como arriba, y nunca en `0.0.0.0` ni en una red a la que no te fíes.

**Actualizar:** baja la imagen nueva y vuelve a crear el contenedor (tus datos están en `~/Clipero`):

```bash
docker pull ghcr.io/henyckmazocker/clipero
docker rm -f clipero
# ...y el mismo docker run de arriba
docker exec --user "$(id -u):$(id -g)" clipero clipero init --actualizar   # refresca CLAUDE.md, la skill y examples/ de ~/Clipero
```

**Comprobar la instalación:**

```bash
docker exec --user "$(id -u):$(id -g)" clipero clipero doctor
```

Muestra una tabla con cada herramienta, su ruta, su versión y un ✓/✗ (solo da ✓ a un binario que
arranca), más el modo de Claude. Sale con código 1 si falta algo obligatorio.

macOS y Windows no tienen soporte oficial; si quieres probarlo, la imagen es lo único que puede
servirte.

## Carpeta de trabajo

Dentro de `~/Clipero` (que `clipero init` crea al primer arranque) viven la configuración y los datos:

```
sources.yaml  branding.yaml  app.yaml  publicados.csv  piloto.csv   configuración
layouts/                      dónde está la facecam y el juego en cada canal
data/  out/                   VODs ingeridos y shorts renderizados
brand/                        avatar y banner opcionales
linea-editorial.md            el enfoque de los textos (ver más abajo)
CLAUDE.md  .claude/skills/tanda/SKILL.md   lo que lee Claude en el modo terminal
.clipero/                     versión, binarios, modelos y credenciales
```

En Docker la carpeta es `/datos`, el `~/Clipero` montado (`CLIPERO_HOME=/datos`). Tras actualizar la
imagen, ejecuta `clipero init --actualizar`: reescribe solo `CLAUDE.md`, la skill, `examples/` y
`.clipero/version`; tus ficheros no se tocan.

Empieza por añadir canales en la app (Configuración › Canales) o en `sources.yaml`.

## El flujo

Con Docker, `clipero` es el alias de `docker exec` de más abajo (modo terminal).

```bash
clipero vods                     # VODs recientes de tus canales, ordenados por repercusión
clipero ingest <url_vod>         # info, heatmap y chat
clipero candidates <id>          # ventanas candidatas
clipero transcribe <id>          # audio de las ventanas → transcripción
clipero render <short.yaml>      # baja los tramos y escribe out/<fecha>/<slug>.mp4 + .meta.md
```

Hay `short.yaml` de ejemplo en `examples/` de tu carpeta de trabajo (los copia `clipero init`). Usan VODs
públicos de Ibai y elxokas: antes de renderizarlos, da de alta el canal en Configuración › Canales
(`render` exige el `credito` de la fuente en `sources.yaml`) y haz `ingest` del VOD y `transcribe` de su ventana. La tanda diaria automatiza todo esto con Claude (ver abajo),
pero se puede hacer a mano sin él.

## Claude: tres formas de usarlo

Claude es opcional. Dentro de Docker hay dos modos, porque la imagen no trae `claude`. Elige el modo en la app, en Configuración › Claude (`app.yaml › claude.modo`).
Por defecto es `ninguno`: una instalación nueva nunca gasta tokens por su cuenta.

| Modo | Qué hace |
|---|---|
| `ninguno` | Sin Claude desde la app. La página Tanda y «Pedir cambio» quedan desactivadas. Todo lo demás funciona. |
| `api_key` | Las tandas y los retoques de la app usan tu API key de Anthropic (variable `ANTHROPIC_API_KEY`, o guardada desde Configuración › Claude en `.clipero/credenciales`, con permisos 0600). **Se paga por tokens**, a precio de API, aparte de cualquier suscripción Pro o Max. El coste por tanda aún no está medido (la app lo guarda en `run.json › coste_usd`). |
| Terminal | Funciona sea cual sea el modo. Abre tu propio `claude` en `~/Clipero` (la carpeta montada, `cd ~/Clipero && claude`) y di **«tanda de hoy»**. La skill `tanda` llama a `clipero …`, que resuelves con un alias a `docker exec` (ver abajo). Ahí eres tú quien usa tu Claude; Clipero solo pone la skill. También sirven «tanda positiva» y «tanda crítica». |

Para la API key, el coste lo pone Anthropic: revisa su tarifa vigente antes de lanzar tandas seguidas.

### Modo terminal con Docker

Añade a tu `~/.bashrc` (o `~/.zshrc`):

```bash
alias clipero='docker exec -i --user "$(id -u):$(id -g)" clipero clipero'
```

`docker exec` llama al binario `clipero` del contenedor llamado `clipero` (no pasa por el
entrypoint), con `/datos` como directorio actual, así que las rutas relativas de la skill, como
`clipero render out/<fecha>/x.short.yaml`, funcionan igual que en `~/Clipero`. Comprueba que va:
`clipero doctor`.

### Línea editorial

El enfoque del texto de los shorts (`gancho`, `titulo`, `descripcion`, `hashtags`) está en
`linea-editorial.md`, en la carpeta de trabajo. `clipero init` crea uno con un ejemplo neutro y
comentado; edítalo con tu postura y tu tono. La skill lo lee antes de cada tanda y lo aplica; si lo
borras, la tanda trabaja sin línea editorial. `init --actualizar` no lo toca nunca.

## Desarrollo

```bash
git clone https://github.com/Henyckmazocker/clipero && cd clipero
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,app]"
make app                         # compila el frontend (web/ → clipero/app/static); necesita node
make tools                       # YuNet y `clipero setup` (ffmpeg, deno, TwitchDownloaderCLI, Whisper)
.venv/bin/pytest -q              # y `-m humo` para la prueba con ffmpeg real (necesita `make tools`)
```

Más detalle para quien desarrolla en `CLAUDE.md`.

## Aviso legal

- Clipero **no sube nada**: lo que publiques lo publicas tú.
- **Tú respondes** de los derechos del material que descargas y recortas, de las [políticas de
  contenido reutilizado de YouTube](https://support.google.com/youtube/answer/1311392) (un short hecho
  con el directo de otro puede considerarse contenido reutilizado y no monetizar) y de las condiciones
  de servicio de **Twitch** y **YouTube**. Descargar VODs o recortarlos puede estar prohibido por ellas
  según el caso.
- Respeta los derechos de música y de terceros (Content ID) y el consentimiento de las personas que
  salen.
- El software se ofrece tal cual, sin garantías (ver `LICENSE`).

## Summary in English

Clipero is a local pipeline that turns VODs from Spanish-speaking streamers (Twitch and YouTube) into
vertical Shorts (20-59 s, edited narrative, burned-in subtitles). It scores chat and heatmap data,
transcribes with Whisper, optionally lets Claude pick and write each short, and renders with ffmpeg.
It never uploads anything. The interface is in Spanish.

Install with Docker only (Linux x64 and arm64; unsupported on macOS and Windows):
`docker run -d --name clipero --restart unless-stopped --user "$(id -u):$(id -g)" -p 127.0.0.1:8765:8765 -v ~/Clipero:/datos ghcr.io/henyckmazocker/clipero`.
The app API has no authentication: only publish the port on 127.0.0.1. For terminal use, alias
`clipero` to `docker exec -i --user "$(id -u):$(id -g)" clipero clipero` and run your own `claude` in `~/Clipero`. Claude is optional (`ninguno` by default;
`api_key`, billed per token; or run your own `claude` in the working folder and say "tanda de hoy"). You are responsible for the rights to the
material, for YouTube's reused-content policies and for the terms of Twitch and YouTube. License:
AGPL-3.0-or-later.
