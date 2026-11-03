#!/bin/sh
# Crea la carpeta de trabajo en /datos la primera vez y ejecuta `clipero <args>`.
set -e
if [ ! -f "${CLIPERO_HOME:-/datos}/.clipero/version" ]; then
    clipero init "${CLIPERO_HOME:-/datos}"
fi
exec clipero "$@"
