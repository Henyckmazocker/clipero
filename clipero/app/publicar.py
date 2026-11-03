"""Fila de publicados.csv a partir del short.yaml, publicar y marcar claim."""
import csv
import os
import re
import threading
from datetime import date
from pathlib import Path

from ..render import FORMATOS, TONOS, load_sources, load_spec

COLS = ["fecha", "slug", "fuente", "formato", "tono", "vod_id", "start", "end", "url"]
URL_RE = re.compile(r"^https://(www\.)?(youtube\.com/(shorts/|watch\?v=)|youtu\.be/)")
_LOCK = threading.Lock()


class Fallo(Exception):
    """Error de la API: status HTTP + código para {"error": código} (+ `detalle` opcional, solo en el 422)."""

    def __init__(self, status: int, codigo: str, detalle: list[str] | None = None):
        super().__init__(codigo)
        self.status, self.codigo, self.detalle = status, codigo, detalle


def ruta_csv(root) -> Path:
    return Path(root) / "publicados.csv"


def leer_publicados(root) -> dict:
    """{slug: {"fecha", "url" (sin #claim), "claim"}}. Si un slug repite fila, gana la última."""
    p = ruta_csv(root)
    if not p.exists():
        return {}
    out = {}
    with open(p, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            slug, url = (r.get("slug") or "").strip(), (r.get("url") or "").strip()
            if not slug or not url:
                continue
            claim = url.endswith("#claim")
            out[slug] = {"fecha": (r.get("fecha") or "").strip(),
                         "url": url[: -len("#claim")] if claim else url, "claim": claim}
    return out


def _num(x) -> str:
    return f"{float(x):.2f}"


def fila_publicado(spec, slug, url, hoy, overrides=None, fuentes=None) -> dict:
    """Fila en el orden de COLS. `spec` puede ser None (sin yaml). Lanza Fallo(400, campo)."""
    spec = spec or {}
    overrides = overrides or {}
    url = (url or "").strip()
    if not URL_RE.match(url):
        raise Fallo(400, "url")
    validos = {"tono": TONOS, "formato": FORMATOS, "fuente": tuple(fuentes) if fuentes is not None else None}
    fila = {"fecha": hoy, "slug": slug}
    for campo in ("fuente", "formato", "tono"):
        v = spec.get(campo)
        if not v:
            v = (overrides.get(campo) or "").strip() if isinstance(overrides.get(campo), str) else None
            if not v or (validos[campo] is not None and v not in validos[campo]):
                raise Fallo(400, campo)
        fila[campo] = str(v)
    tramos = spec.get("tramos") or []
    if tramos:
        vod = str(tramos[0]["vod"])
        mismos = [t for t in tramos if str(t["vod"]) == vod]
        fila["vod_id"] = vod
        fila["start"] = _num(min(float(t["start"]) for t in mismos))
        fila["end"] = _num(max(float(t["end"]) for t in mismos))
    else:
        fila["vod_id"] = fila["start"] = fila["end"] = ""
    fila["url"] = url
    return fila


def _comprobar_cabecera(p: Path):
    with open(p, encoding="utf-8", newline="") as f:
        cab = next(csv.reader(f), None)
    if cab != COLS:
        raise Fallo(500, "cabecera")


def publicar(root, fecha, slug, url, overrides=None) -> dict:
    root = Path(root)
    if not (root / "out" / fecha / f"{slug}.mp4").is_file():
        raise Fallo(404, "no_encontrado")
    yaml_p = root / "out" / fecha / f"{slug}.short.yaml"
    spec = load_spec(yaml_p) if yaml_p.exists() else None
    src = root / "sources.yaml"
    fuentes = list(load_sources(src)) if src.exists() else []
    p = ruta_csv(root)
    with _LOCK:
        if slug in leer_publicados(root):
            raise Fallo(409, "ya_publicado")
        fila = fila_publicado(spec, slug, url, date.today().isoformat(), overrides, fuentes)
        existe = p.exists() and p.stat().st_size > 0
        if existe:
            _comprobar_cabecera(p)
            with open(p, "rb") as f:
                f.seek(-1, os.SEEK_END)
                sin_salto = f.read(1) != b"\n"
        with open(p, "a", encoding="utf-8", newline="") as f:
            if existe and sin_salto:
                f.write("\n")
            w = csv.DictWriter(f, COLS, lineterminator="\n")
            if not existe:
                w.writeheader()
            w.writerow(fila)
    return fila


def marcar_claim(root, slug) -> bool:
    """Añade #claim a la url de la fila. True si cambió, False si ya lo llevaba. Fallo 409 si no está."""
    p = ruta_csv(root)
    with _LOCK:
        if not p.exists():
            raise Fallo(409, "no_publicado")
        _comprobar_cabecera(p)
        with open(p, encoding="utf-8", newline="") as f:
            filas = list(csv.DictReader(f))
        idx = [i for i, r in enumerate(filas) if r["slug"] == slug and (r.get("url") or "").strip()]
        if not idx:
            raise Fallo(409, "no_publicado")
        r = filas[idx[-1]]
        if r["url"].strip().endswith("#claim"):
            return False
        r["url"] = r["url"].strip() + "#claim"
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, COLS, lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
        os.replace(tmp, p)
    return True
