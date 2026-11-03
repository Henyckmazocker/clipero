"""Escanea out/, parsea meta.md, agrupa versiones, miniaturas y borrado."""
import re
import subprocess
from pathlib import Path

from .. import herramientas
from ..render import load_sources, load_spec
from .publicar import Fallo, leer_publicados

VERSION_RE = re.compile(r"^(?P<base>[a-z0-9][a-z0-9-]*?)(?:-v(?P<n>[2-9]|[1-9]\d+))?$")
FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_meta(texto: str) -> dict:
    """meta.md → dict. Tolera la línea de formato con y sin «Tono». No toca el fichero."""
    claves = {"título": "titulo", "descripción": "descripcion", "hashtags": "hashtags", "avisos": "avisos"}
    campos = {}
    for linea in texto.splitlines():
        m = re.match(r"\*\*(.+?):\*\*\s?(.*)$", linea)
        if m and m.group(1).lower() in claves:
            campos[claves[m.group(1).lower()]] = m.group(2).strip()
    linea_fmt = next((l for l in texto.splitlines() if l.startswith("**Formato:**")), "")
    extra = {}
    for trozo in linea_fmt.split(" · "):
        m = re.match(r"\*\*(.+?):\*\*\s*(.*)$", trozo.strip())
        if m:
            extra[m.group(1).lower().replace("ó", "o")] = m.group(2).strip()
    tono = extra.get("tono")
    dur = re.match(r"([\d.,]+)", extra.get("duracion", ""))
    avisos = campos.get("avisos", "")
    return {
        "titulo": campos.get("titulo", ""),
        "descripcion": campos.get("descripcion", "").replace("\\n", "\n"),
        "hashtags": campos.get("hashtags", ""),
        "formato": extra.get("formato") or None,
        "tono": None if not tono or tono == "?" else tono,
        "duracion_s": float(dur.group(1).replace(",", ".")) if dur else None,
        "encuadre": extra.get("encuadre") or None,
        "avisos": [] if not avisos or avisos == "ninguno" else [a.strip() for a in avisos.split(";") if a.strip()],
    }


def _fuente_de_credito(descripcion: str, fuentes: dict):
    """Id de la fuente cuyo crédito aparece antes en la descripción."""
    mejor = None
    for sid, s in fuentes.items():
        c = s.get("credito")
        i = descripcion.find(c) if c else -1
        if i >= 0 and (mejor is None or i < mejor[0]):
            mejor = (i, sid)
    return mejor[1] if mejor else None


def _version(root: Path, mp4: Path, fuentes: dict, publicados: dict) -> dict | None:
    m = VERSION_RE.match(mp4.stem)
    if not m:
        return None
    slug, fecha = mp4.stem, mp4.parent.name
    meta_p, yaml_p = mp4.with_suffix(".meta.md"), mp4.with_suffix(".short.yaml")
    meta = parse_meta(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else parse_meta("")
    spec = {}
    if yaml_p.exists():
        try:
            spec = load_spec(yaml_p)
        except RuntimeError:
            spec = {}
    pub = publicados.get(slug)
    return {
        "slug": slug, "n": int(m.group("n") or 1), "fecha": fecha,
        "fuente": spec.get("fuente") or _fuente_de_credito(meta["descripcion"], fuentes),
        "formato": spec.get("formato") or meta["formato"],
        "tono": spec.get("tono") or meta["tono"],
        "duracion_s": meta["duracion_s"], "encuadre": meta["encuadre"], "avisos": meta["avisos"],
        "titulo": meta["titulo"] or (f"{spec['titulo']} #shorts" if spec.get("titulo") else slug),
        "descripcion": meta["descripcion"] or spec.get("descripcion") or "",
        "hashtags": meta["hashtags"] or spec.get("hashtags") or "",
        "editable": yaml_p.exists(),
        "publicado": {"fecha": pub["fecha"], "url": pub["url"], "claim": pub["claim"]} if pub else None,
        "mp4": f"/media/out/{fecha}/{slug}.mp4", "thumb": f"/api/thumbs/{fecha}/{slug}.jpg",
        "mtime": mp4.stat().st_mtime,
        "_base": m.group("base"),
    }


def escanear(root) -> list[dict]:
    """[ClipGroup] ordenados por fecha desc y luego mtime desc (el más reciente de sus versiones)."""
    root = Path(root)
    out_dir = root / "out"
    if not out_dir.is_dir():
        return []
    src = root / "sources.yaml"
    fuentes = load_sources(src) if src.exists() else {}
    publicados = leer_publicados(root)
    grupos = {}
    for d in sorted(out_dir.iterdir()):
        if not d.is_dir() or not FECHA_RE.fullmatch(d.name):
            continue
        for mp4 in sorted(d.glob("*.mp4")):
            v = _version(root, mp4, fuentes, publicados)
            if v:
                grupos.setdefault((d.name, v.pop("_base")), []).append(v)
    res = []
    for (fecha, base), vs in grupos.items():
        vs.sort(key=lambda v: v["n"])
        res.append({"base": base, "fecha": fecha, "fuente": next((v["fuente"] for v in vs if v["fuente"]), None),
                    "versiones": vs})
    res.sort(key=lambda g: (g["fecha"], max(v["mtime"] for v in g["versiones"])), reverse=True)
    return res


def filtrar(grupos, fuente=None, tono=None, formato=None, desde=None, hasta=None, publicado=None):
    """Un grupo pasa si alguna de sus versiones cumple todos los filtros; se devuelve entero."""
    def ok(v):
        return ((not fuente or v["fuente"] == fuente) and (not tono or v["tono"] == tono)
                and (not formato or v["formato"] == formato)
                and (not desde or v["fecha"] >= desde) and (not hasta or v["fecha"] <= hasta)
                and (publicado not in ("si", "no") or bool(v["publicado"]) == (publicado == "si")))
    return [g for g in grupos if any(ok(v) for v in g["versiones"])]


def _thumb_path(root, fecha, slug) -> Path:
    return Path(root) / "data" / "app" / "thumbs" / fecha / f"{slug}.jpg"


def miniatura(root, fecha, slug) -> Path:
    """JPG cacheado en data/app/thumbs/, regenerado si el mp4 es más nuevo. FileNotFoundError si no hay mp4."""
    mp4 = Path(root) / "out" / fecha / f"{slug}.mp4"
    if not mp4.is_file():
        raise FileNotFoundError(mp4)
    jpg = _thumb_path(root, fecha, slug)
    if jpg.is_file() and jpg.stat().st_mtime >= mp4.stat().st_mtime:
        return jpg
    ffmpeg = herramientas.ruta("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg no encontrado")
    jpg.parent.mkdir(parents=True, exist_ok=True)
    tmp = jpg.with_name(jpg.stem + ".tmp.jpg")
    r = subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", "1", "-i", str(mp4), "-frames:v", "1",
                        "-vf", "scale=270:-2", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.strip()[-300:] or "ffmpeg falló")
    tmp.replace(jpg)
    return jpg


def borrar(root, fecha, slug):
    """Borra mp4, meta.md, short.yaml y miniatura. Fallo 404 si no hay mp4, 409 si está publicado."""
    root = Path(root)
    mp4 = root / "out" / fecha / f"{slug}.mp4"
    if not mp4.is_file():
        raise Fallo(404, "no_encontrado")
    if slug in leer_publicados(root):
        raise Fallo(409, "publicado")
    for f in (mp4, mp4.with_suffix(".meta.md"), mp4.with_suffix(".short.yaml"), _thumb_path(root, fecha, slug)):
        f.unlink(missing_ok=True)
