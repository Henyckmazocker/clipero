# Software de terceros

Clipero se distribuye bajo **AGPL-3.0-or-later** (`LICENSE`). Usa, descarga o incluye lo que sigue,
cada uno con su licencia. Las licencias de la tabla se comprobaron en la fuente el 2026-11-03.

| Componente | Licencia | Cómo llega a tu máquina |
|---|---|---|
| **ffmpeg** y ffprobe | GPL (el build de BtbN `FFmpeg-Builds` que baja `clipero setup` es el `gpl`; el ffmpeg de Debian de la imagen Docker también es GPL) | La imagen Docker lo instala con `apt` de Debian. En un entorno de desarrollo, `clipero setup` baja la build BtbN n8.1 a `<carpeta de trabajo>/.clipero/bin/` si no hay uno en el PATH. Código fuente: <https://ffmpeg.org/> |
| **Montserrat** (ExtraBold) | SIL Open Font License 1.1 | Dentro de la imagen, en `clipero/recursos/fonts/`, con su texto en `clipero/recursos/fonts/OFL.txt`. Fuente: <https://github.com/JulietaUla/Montserrat> |
| **YuNet** (`face_detection_yunet_2023mar.onnx`) | MIT (Shiqi Yu), de `opencv_zoo` | Dentro de la imagen, en `clipero/recursos/models/`. Fuente: <https://github.com/opencv/opencv_zoo> |
| **TwitchDownloaderCLI** | MIT (lay295) | La imagen lo trae (lo baja `clipero setup` al construirla). Fuente: <https://github.com/lay295/TwitchDownloader> |
| **yt-dlp** | Unlicense (dominio público) | Dependencia de pip, instalada en la imagen (`yt-dlp[default]`). Fuente: <https://github.com/yt-dlp/yt-dlp> |
| **faster-whisper** | MIT (SYSTRAN) | Dependencia de pip. Fuente: <https://github.com/SYSTRAN/faster-whisper> |
| Modelo Whisper `small` | MIT (OpenAI) | La imagen lo trae, bajado por `clipero setup` al construirla |
| **deno** | MIT | La imagen lo trae, bajado por `clipero setup` al construirla (runtime de JS que usa yt-dlp para YouTube). Fuente: <https://github.com/denoland/deno> |
| **claude-agent-sdk** | Su `LICENSE` es MIT, pero el README del proyecto dice que su uso se rige por las [Commercial Terms of Service de Anthropic](https://www.anthropic.com/legal/commercial-terms) | Dependencia de pip del extra `app`. Fuente: <https://github.com/anthropics/claude-agent-sdk-python> |
| **opencv-python**, numpy, PyAV, PyYAML, FastAPI, uvicorn, httpx, ruamel.yaml | Licencias permisivas (Apache-2.0, BSD, MIT) | Dependencias de pip. Sus licencias van en el metadato de cada paquete instalado |

## Notas

- Clipero no incluye ni redistribuye el binario `claude`. El modo `suscripcion` usa el que tú tengas
  instalado, bajo las condiciones de Anthropic para ese producto.
- El frontend (`web/`) lleva Vue, PrimeVue y las demás dependencias de `web/package.json`, todas con
  licencias permisivas; se compilan dentro de `clipero/app/static/`.
- La imagen Docker lleva ffmpeg (GPL), así que al distribuirla se distribuye también ese software bajo
  sus términos; las fuentes están en los repositorios de Debian.
