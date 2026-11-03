# syntax=docker/dockerfile:1
# Etapa 1: interfaz (vite escribe en ../clipero/app/static)
FROM node:22 AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Etapa 2: paquete + herramientas
FROM python:3.12-slim
# libicu: TwitchDownloaderCLI (.NET) no arranca sin ella
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libicu-dev ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY pyproject.toml README.md ./
COPY clipero/ clipero/
COPY --from=web /src/clipero/app/static clipero/app/static
RUN pip install --no-cache-dir ".[app]"

# Binarios y modelo de Whisper en un home interno de la imagen (/opt/clipero), no en /datos:
# al montar un volumen en /datos no se pierden. deno y TDL se encuentran por el PATH;
# Whisper, con CLIPERO_WHISPER_DIR.
ENV PATH=/opt/clipero/.clipero/bin:$PATH \
    CLIPERO_WHISPER_DIR=/opt/clipero/.clipero/modelos/whisper
RUN CLIPERO_HOME=/opt/clipero clipero setup

ENV CLIPERO_HOME=/datos
VOLUME /datos
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint
RUN chmod +x /usr/local/bin/docker-entrypoint
EXPOSE 8765
ENTRYPOINT ["docker-entrypoint"]
CMD ["app", "--host", "0.0.0.0"]
