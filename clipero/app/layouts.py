"""Layouts desde la app: VODs/tramos con seg/, fotograma, CRUD con fusión en ruamel y «probar detección»."""
import io
import json
import math
import re
import subprocess
import time
from pathlib import Path

import yaml
from ruamel.yaml.comments import CommentedMap

from .. import config, frame, herramientas, render
from .publicar import Fallo

FUENTE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VOD_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SEG_RE = re.compile(r"^\d+_\d+$")
MIN_SEG = 10_000          # bytes: un tramo bajado de verdad pesa más (render.get_segment)
FRAMES_DIAS = 14

_dims: dict = {}          # (ruta, mtime_ns) → (w, h)


# --- validación de nombres y rutas ----------------------------------------------

def check_fuente(fuente):
    if not FUENTE_RE.fullmatch(fuente):
        raise Fallo(404, "no_encontrado")


def check_vod(vod):
    if not VOD_RE.fullmatch(vod) or vod == "vods":
        raise Fallo(404, "no_encontrado")


def _dentro(base: Path, ruta: Path) -> bool:
    return base.resolve() in ruta.resolve().parents


def _vods_dir(root) -> Path:
    return Path(root) / "data" / "vods"


# --- VODs y tramos --------------------------------------------------------------

def _wh(mp4: Path):
    """(w, h) con ffprobe, cacheado por ruta y mtime; (None, None) si no se puede leer."""
    clave = (str(mp4), mp4.stat().st_mtime_ns)
    if clave not in _dims:
        w = h = None
        ffprobe = herramientas.ruta("ffprobe")
        if ffprobe:
            r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height", "-of", "csv=p=0:s=x", str(mp4)],
                               capture_output=True, text=True)
            lineas = r.stdout.split() if r.returncode == 0 else []   # ffprobe puede repetir la línea
            m = re.fullmatch(r"(\d+)x(\d+)", lineas[0]) if lineas else None
            if m:
                w, h = int(m.group(1)), int(m.group(2))
        _dims[clave] = (w, h)
    return _dims[clave]


def _tramos(seg_dir: Path) -> list[dict]:
    out = []
    for mp4 in sorted(seg_dir.glob("*.mp4")):
        if not SEG_RE.fullmatch(mp4.stem) or mp4.stat().st_size <= MIN_SEG:
            continue
        a, b = (int(x) / 100 for x in mp4.stem.split("_"))
        try:
            offset = float(json.loads(mp4.with_suffix(".json").read_text())["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            offset = a
        w, h = _wh(mp4)
        out.append({"seg": mp4.stem, "start": a, "end": b, "offset": offset, "w": w, "h": h})
    out.sort(key=lambda t: t["start"])
    return out


def vods_de(root, fuente) -> list[dict]:
    """VODs de `fuente` con algún seg/*.mp4 válido, los más recientes primero."""
    srcs = render.load_sources(Path(root) / "sources.yaml")
    out = []
    for info_f in sorted(_vods_dir(root).glob("*/info.json")):
        try:
            info = json.loads(info_f.read_text())
        except (OSError, ValueError):
            continue
        if render.source_of_info(info, srcs) != fuente:
            continue
        tramos = _tramos(info_f.parent / "seg")
        if not tramos:
            continue
        f = str(info.get("upload_date") or "")
        out.append({"vod": info_f.parent.name,
                    "plataforma": "twitch" if str(info.get("extractor", "")).startswith("twitch") else "youtube",
                    "fecha": f"{f[:4]}-{f[4:6]}-{f[6:8]}" if len(f) == 8 else "",
                    "titulo": info.get("title") or "",
                    "tramos": tramos})
    out.sort(key=lambda v: v["fecha"], reverse=True)
    return out


# --- fotograma ------------------------------------------------------------------

def _frames_dir(root) -> Path:
    return Path(root) / "data" / "app" / "frames"


def fotograma(root, vod, seg, t) -> Path:
    """JPG cacheado del segundo `t` (s del VOD) del tramo `seg`. Fallo 404 / 422 fuera_de_tramo."""
    if not VOD_RE.fullmatch(vod) or not SEG_RE.fullmatch(seg):
        raise Fallo(404, "no_encontrado")
    mp4 = _vods_dir(root) / vod / "seg" / f"{seg}.mp4"
    if not _dentro(_vods_dir(root), mp4) or not mp4.is_file() or mp4.stat().st_size <= MIN_SEG:
        raise Fallo(404, "no_encontrado")
    a, b = (int(x) / 100 for x in seg.split("_"))
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not (a <= t <= b):
        raise Fallo(422, "fuera_de_tramo")
    jpg = _frames_dir(root) / vod / f"{seg}_{round(t * 10)}.jpg"
    if jpg.is_file():
        return jpg
    try:
        offset = float(json.loads(mp4.with_suffix(".json").read_text())["offset"])
    except (OSError, ValueError, KeyError, TypeError):
        offset = a
    ffmpeg = herramientas.ruta("ffmpeg")
    if not ffmpeg:
        raise Fallo(500, "ffmpeg")
    jpg.parent.mkdir(parents=True, exist_ok=True)
    tmp = jpg.with_name(jpg.stem + ".tmp.jpg")
    r = subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(t - offset, 0):.3f}", "-i", str(mp4),
                        "-frames:v", "1", "-q:v", "3", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise Fallo(500, "ffmpeg")
    tmp.replace(jpg)
    return jpg


def purgar_frames(root, dias=FRAMES_DIAS) -> int:
    """Borra los fotogramas cacheados con más de `dias` días. → nº de ficheros borrados."""
    n, limite = 0, time.time() - dias * 86400
    for f in _frames_dir(root).glob("*/*.jpg"):
        if f.stat().st_mtime < limite:
            f.unlink(missing_ok=True)
            n += 1
    return n


# --- probar detección -----------------------------------------------------------

def probar(root, layout, vod, seg, t) -> dict:
    import cv2
    try:
        frame.validate_layout(layout, "layout")
    except RuntimeError as e:
        raise Fallo(422, "invalido", [str(e)])
    if not frame.has_escenas(layout):
        raise Fallo(422, "sin_escena_detectable")
    det, _ = frame.scene_roles(layout)
    if det is None:
        raise Fallo(422, "sin_escena_detectable")
    jpg = fotograma(root, vod, seg, t)
    img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise Fallo(500, "fotograma")
    iw, ih = frame.parse_size(layout["entrada"])
    dw = frame.DET_W
    dh = frame._even(img.shape[0] * dw / img.shape[1])
    g = cv2.resize(img, (dw, dh), interpolation=cv2.INTER_AREA).astype("int16")
    try:
        score = frame.edge_score(g, layout["escenas"][det]["facecam"], dw / iw, dh / ih)
    except ValueError:      # max() sobre un rango vacío: la facecam toca el borde izquierdo o superior
        score = float("nan")
    if not math.isfinite(score):   # slice vacío (facecam diminuta) → NaN
        return {"score": 0.0, "umbral": frame.SCENE_THR, "detecta": False,
                "aviso": "la facecam toca el borde o es demasiado pequeña para detectar el marco"}
    return {"score": round(score, 3), "umbral": frame.SCENE_THR, "detecta": score >= frame.SCENE_THR}


# --- CRUD de layouts ------------------------------------------------------------

def listar(root, ids_nombres) -> list[dict]:
    """Una fila por canal activo: [(id, nombre)]."""
    base = Path(root) / "layouts"
    out = []
    for fid, nombre in ids_nombres:
        exc = sorted(p.stem for p in (base / fid).glob("*.yaml")) if (base / fid).is_dir() else []
        out.append({"fuente": fid, "nombre": nombre, "canal": (base / f"{fid}.yaml").is_file(),
                    "excepciones": exc})
    return out


def ruta(root, fuente, vod=None) -> Path:
    return frame.layout_path(fuente, vod, Path(root) / "layouts")


def leer(root, fuente, vod=None) -> dict:
    p = ruta(root, fuente, vod)
    if not p.is_file():
        raise Fallo(404, "sin_layout")
    return yaml.safe_load(p.read_text()) or {}


def _nuevo(valor, rect=False):
    """JSON → estructura ruamel; los rectángulos {x,y,w,h} en estilo flujo."""
    if isinstance(valor, dict):
        m = CommentedMap()
        for k, v in valor.items():
            m[k] = _nuevo(v, rect=isinstance(v, dict) and not any(isinstance(x, dict) for x in v.values()))
        if rect:
            m.fa.set_flow_style()
        return m
    return valor


def fusionar(dest, nuevo: dict) -> None:
    """Vuelca `nuevo` en el CommentedMap `dest`: las claves que siguen conservan sus comentarios y su
    orden, las que desaparecen se borran y las nuevas van al final."""
    for k in [k for k in dest if k not in nuevo]:
        del dest[k]
    for k, v in nuevo.items():
        if k in dest and isinstance(dest[k], CommentedMap) and isinstance(v, dict):
            fusionar(dest[k], v)
        elif k in dest and not isinstance(v, dict):
            dest[k] = v
        else:
            dest[k] = _nuevo(v, rect=isinstance(v, dict) and not any(isinstance(x, dict) for x in v.values()))


def guardar(root, fuente, vod, layout) -> dict:
    p = ruta(root, fuente, vod)
    try:
        frame.validate_layout(layout, p.name)
    except RuntimeError as e:
        raise Fallo(422, "invalido", [str(e)])
    y = config.make_yaml()
    if p.is_file():
        actual = y.load(p.read_text())
        if not isinstance(actual, CommentedMap):
            actual = CommentedMap()
        fusionar(actual, layout)
    else:
        actual = _nuevo(layout)
    buf = io.StringIO()
    y.dump(actual, buf)
    p.parent.mkdir(parents=True, exist_ok=True)
    config.write_atomic(p, buf.getvalue())
    return leer(root, fuente, vod)


def borrar(root, fuente, vod=None) -> None:
    p = ruta(root, fuente, vod)
    if not p.is_file():
        raise Fallo(404, "sin_layout")
    p.unlink()
    if vod and not any(p.parent.iterdir()):
        p.parent.rmdir()
