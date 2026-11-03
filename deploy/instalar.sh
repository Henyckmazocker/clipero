#!/usr/bin/env bash
# Instala el servicio de usuario y el lanzador de Clipero. Idempotente.
# Usa el `clipero` del PATH; si no hay, el .venv/bin/clipero de este checkout.
set -euo pipefail
aqui="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v clipero >/dev/null; then
  clipero_bin="$(command -v clipero)"
elif [ -x "$aqui/../.venv/bin/clipero" ]; then
  clipero_bin="$(cd "$aqui/.." && pwd)/.venv/bin/clipero"
else
  echo "no encuentro clipero: instálalo (uv tool install) o crea el .venv del repo" >&2
  exit 1
fi
mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
sed "s|@CLIPERO@|$clipero_bin|" "$aqui/clipero-app.service" > "$HOME/.config/systemd/user/clipero-app.service"
sed "s|@HOME@|$HOME|g" "$aqui/clipero.desktop" > "$HOME/.local/share/applications/clipero.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true
systemctl --user daemon-reload
systemctl --user enable --now clipero-app
systemctl --user restart clipero-app
