# Clipero

Pipeline local que saca Shorts verticales (20-59 s, narrativa editada y subtítulos quemados) a partir
de VODs de streamers hispanos de Twitch y YouTube. Puntúa el chat y el heatmap para encontrar los
momentos fuertes, transcribe con Whisper, deja que Claude elija y escriba cada short (opcional) y
renderiza el vídeo con ffmpeg. Trae una app web local para revisar los clips, medir el rendimiento y
configurar canales, marca y layouts.

**Clipero no sube nada.** Deja los `.mp4` y un `.meta.md` con título, descripción y hashtags en
`out/<fecha>/`; subirlos es cosa tuya.

Licencia: AGPL-3.0-or-later (ver `LICENSE`; el software de terceros está en `THIRD_PARTY.md`).

## Instalación en Linux

Linux x64 y arm64. Necesitas Python 3.12 y [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install "clipero[app]"   # alternativa: pipx install "clipero[app]"
clipero init                     # crea la carpeta de trabajo ~/Clipero
clipero setup                    # baja ffmpeg (si no lo tienes), deno, TwitchDownloaderCLI y el modelo Whisper
clipero app --abrir              # arranca la app en http://127.0.0.1:8765 y abre el navegador
```

Sin el extra `app` (`uv tool install clipero`) tienes solo la línea de comandos.

`clipero doctor` comprueba la instalación: una tabla con cada herramienta, su ruta, su versión y un
✓/✗ (solo da ✓ a un binario que arranca), más el modo de Claude. Sale con código 1 si falta algo
obligatorio.

### Plan B: ffmpeg y deno con `apt`

Si `clipero setup` no puede bajar algo (red restringida, arquitectura rara), instala lo del sistema y
Clipero lo encontrará en el PATH:

```bash
sudo apt install ffmpeg
curl -fsSL https://deno.land/install.sh | sh   # deno, el runtime de JS que usa yt-dlp para YouTube
```

`TwitchDownloaderCLI` y el modelo Whisper siguen saliendo de `clipero setup`. Necesita `libicu`
(`sudo apt install libicu-dev` en Debian y Ubuntu).

### Docker

```bash
docker run -p 127.0.0.1:8765:8765 -v ~/Clipero:/datos ghcr.io/henyckmazocker/clipero
```

La imagen lleva ffmpeg, deno, TwitchDownloaderCLI y Whisper, y usa `/datos` como carpeta de trabajo
(la crea con `clipero init` si está vacía). **La API de la app no tiene autenticación**, y desde ella
se puede cambiar hasta la API key: publica el puerto **solo en `127.0.0.1`**, como en el comando de
arriba, y nunca en `0.0.0.0` ni en una red a la que no te fíes. Dentro del contenedor no hay `claude`,
así que solo están los modos `ninguno` y `api_key`.

### macOS y Windows

Sin soporte. Si quieres probarlo, usa Docker.

## Carpeta de trabajo

`clipero init` crea `~/Clipero` (o la ruta que le des) con la configuración y los datos:

```
sources.yaml  branding.yaml  app.yaml  publicados.csv  piloto.csv   configuración
layouts/                      dónde está la facecam y el juego en cada canal
data/  out/                   VODs ingeridos y shorts renderizados
brand/                        avatar y banner opcionales
linea-editorial.md            el enfoque de los textos (ver más abajo)
CLAUDE.md  .claude/skills/tanda/SKILL.md   lo que lee Claude en el modo terminal
.clipero/                     versión, binarios, modelos y credenciales
```

La carpeta se resuelve en este orden: `--home DIR`, la variable `CLIPERO_HOME`, la primera línea de
`~/.config/clipero/home` (la escribe `init`) y, si no, `~/Clipero`. Tras actualizar Clipero, ejecuta
`clipero init --actualizar`: reescribe solo `CLAUDE.md`, la skill y `.clipero/version`; tus ficheros
no se tocan.

Empieza por añadir canales en la app (Configuración › Canales) o en `sources.yaml`.

## El flujo

```bash
clipero vods                     # VODs recientes de tus canales, ordenados por repercusión
clipero ingest <url_vod>         # info, heatmap y chat
clipero candidates <id>          # ventanas candidatas
clipero transcribe <id>          # audio de las ventanas → transcripción
clipero render <short.yaml>      # baja los tramos y escribe out/<fecha>/<slug>.mp4 + .meta.md
```

Hay `short.yaml` de ejemplo en `examples/` de tu carpeta de trabajo (los copia `clipero init`). La tanda diaria automatiza todo esto con Claude (ver abajo),
pero se puede hacer a mano sin él.

## Claude: cuatro formas de usarlo

Claude es opcional. Elige el modo en la app, en Configuración › Claude (`app.yaml › claude.modo`).
Por defecto es `ninguno`: una instalación nueva nunca gasta tokens por su cuenta.

| Modo | Qué hace |
|---|---|
| `ninguno` | Sin Claude desde la app. La página Tanda y «Pedir cambio» quedan desactivadas. Todo lo demás funciona. |
| `api_key` | Las tandas y los retoques de la app usan tu API key de Anthropic (variable `ANTHROPIC_API_KEY`, o guardada desde Configuración › Claude en `.clipero/credenciales`, con permisos 0600). **Se paga por tokens**, a precio de API, aparte de cualquier suscripción Pro o Max. El coste por tanda aún no está medido (la app lo guarda en `run.json › coste_usd`). |
| `suscripcion` | «Claude (tu suscripción, con tu `claude` instalado)». Clipero no ofrece ningún login: usa el `claude` oficial que **tú** hayas instalado y en el que **tú** hayas iniciado sesión, y nunca el binario que trae el SDK. Si no hay `claude` en el PATH, el modo no está disponible. Es una zona gris de la política del Agent SDK de Anthropic, que no permite que terceros ofrezcan el login de claude.ai en sus productos: si lo usas, es en tu cuenta y bajo tu responsabilidad, y puede cambiar si Anthropic cambia sus condiciones. |
| Terminal | Funciona sea cual sea el modo. Abre `claude` en la carpeta de trabajo (`cd ~/Clipero && claude`) y di **«tanda de hoy»**. Ahí eres tú quien usa tu Claude; Clipero solo pone la skill `tanda`. También sirven «tanda positiva» y «tanda crítica». |

Para la API key, el coste lo pone Anthropic: revisa su tarifa vigente antes de lanzar tandas seguidas.

### Línea editorial

El enfoque del texto de los shorts (`gancho`, `titulo`, `descripcion`, `hashtags`) está en
`linea-editorial.md`, en la carpeta de trabajo. `clipero init` crea uno con un ejemplo neutro y
comentado; edítalo con tu postura y tu tono. La skill lo lee antes de cada tanda y lo aplica; si lo
borras, la tanda trabaja sin línea editorial. `init --actualizar` no lo toca nunca.

## Autoarranque opcional en Linux

`deploy/` trae una unidad de systemd de usuario y un lanzador de escritorio para tener la app siempre
levantada. Desde un checkout del repo:

```bash
bash deploy/instalar.sh          # unidad `clipero-app` (con CLIPERO_HOME=%h/Clipero) + lanzador «Clipero»
systemctl --user restart clipero-app   # tras actualizar Clipero
```

Usa el `clipero` de tu PATH. El lanzador abre la app en una ventana de Chromium del snap; si usas otro
navegador, edita `deploy/clipero.desktop`.

## Desarrollo

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,app]"
.venv/bin/pytest -q              # y `-m humo` para la prueba con ffmpeg real (necesita `clipero setup`)
make app                         # compila el frontend (web/ → clipero/app/static); necesita node
.venv/bin/python -m build        # wheel + sdist (exige `make app` antes)
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

Linux only (x64 and arm64): `uv tool install "clipero[app]"`, then `clipero init`, `clipero setup`
and `clipero app --abrir`. Docker works anywhere, unsupported on macOS and Windows:
`docker run -p 127.0.0.1:8765:8765 -v ~/Clipero:/datos ghcr.io/henyckmazocker/clipero`. The app API
has no authentication: only publish the port on 127.0.0.1. Claude is optional (`ninguno` by default;
`api_key`, billed per token; `suscripcion`, using your own installed and logged-in `claude`; or run
`claude` in the working folder and say "tanda de hoy"). You are responsible for the rights to the
material, for YouTube's reused-content policies and for the terms of Twitch and YouTube. License:
AGPL-3.0-or-later.
