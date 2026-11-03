"""frame: encuadre 9:16 de un tramo 16:9 → filtros de ffmpeg.

- Con plantilla `layouts/<fuente>.yaml`: facecam arriba y juego abajo, cada una escalada a 1080×810
  (`layout_graph`); la franja central (y 810–1110) queda para los subtítulos.
- Con `escenas:` en la plantilla (ver `escenas_graph`): el encuadre se elige por muestra (2 fps) entre
  una escena detectable (la que declara un recuadro `facecam`: se reconoce por el marco recto del
  recuadro, `detect_scenes`) y la escena por defecto (`ancho` o `cara`); el cambio entra como corte limpio.
- Sin plantilla: YuNet a 2 fps sobre el tramo, centro x de la cara mayor, suavizado exponencial
  (α = 0,15) y recorte de relación 9:16 (608×1080 en una fuente 1080p) → 1080×1920 (`track_face`,
  `smooth`, `crop_x_expr`). Sin cara en > 50 % de las muestras → recorte centrado (`aviso`).
- `zoompan_filter`: énfasis (`zoom:` del short.yaml) sobre el short ya montado.
"""
import re
import subprocess

import numpy as np
import yaml

from . import herramientas, rutas

W, H = 1080, 1920


def model():
    return rutas.modelo_yunet()


def layouts():
    return rutas.home() / "layouts"


ALPHA = 0.15          # suavizado exponencial del centro x
DET_FPS = 2           # muestras de YuNet por segundo
MIN_FACE_RATIO = 0.5  # por debajo, recorte centrado
FACE_PAD = 60          # px de la fuente entre la cara y el borde del recorte, como mínimo
DET_W = 960           # ancho al que se pasa YuNet (la cara se reescala de vuelta)


def _even(v):
    return int(round(v / 2.0)) * 2


# --- plantilla ------------------------------------------------------------------

def layout_path(fuente, vod=None, layouts_dir=None):
    """layouts/<fuente>/<vod>.yaml si hay `vod`; si no, layouts/<fuente>.yaml."""
    base = layouts_dir or layouts()
    if vod:
        return base / str(fuente) / f"{vod}.yaml"
    return base / f"{fuente}.yaml"


def load_layout(fuente, layouts_dir=None, vod=None):
    """Excepción del VOD (layouts/<fuente>/<vod>.yaml) si existe; si no layouts/<fuente>.yaml → dict,
    o None si no hay ninguno."""
    p = layout_path(fuente, vod, layouts_dir)
    if not (vod and p.exists()):
        p = layout_path(fuente, None, layouts_dir)
    if not p.exists():
        return None
    d = yaml.safe_load(p.read_text()) or {}
    validate_layout(d, p)
    return d


def validate_layout(d, origen="layout"):
    """Lanza RuntimeError con el motivo si `d` no es un layout válido."""
    p = origen
    if not isinstance(d, dict) or "entrada" not in d:
        raise RuntimeError(f"{p}: falta `entrada`")
    try:
        iw, ih = parse_size(d["entrada"])
    except (ValueError, TypeError):
        raise RuntimeError(f"{p}: `entrada` tiene que ser AxB (p. ej. 1920x1080)")
    if "escenas" in d:
        _check_escenas(d["escenas"], p)
        rects = [(f"escenas.{n}.{k}", c[k]) for n, c in d["escenas"].items()
                 for k in ("facecam", "juego") if k in c]
    else:
        for k in ("facecam", "juego"):
            if k not in d:
                raise RuntimeError(f"{p}: falta `{k}` (o `escenas`)")
        rects = [(k, d[k]) for k in ("facecam", "juego")]
    for nombre, r in rects:
        _check_rect(nombre, r, iw, ih, p)


def _check_rect(nombre, r, iw, ih, p):
    if not isinstance(r, dict) or any(
            not isinstance(r.get(k), int) or isinstance(r.get(k), bool) for k in "xywh"):
        raise RuntimeError(f"{p}: `{nombre}` tiene que ser {{x, y, w, h}} con enteros")
    if r["w"] <= 0 or r["h"] <= 0 or r["x"] < 0 or r["y"] < 0 or r["x"] + r["w"] > iw \
            or r["y"] + r["h"] > ih:
        raise RuntimeError(f"{p}: `{nombre}` queda fuera de `entrada` ({iw}x{ih}) o tiene w/h ≤ 0")


def _check_escenas(esc, p):
    if not isinstance(esc, dict) or not esc:
        raise RuntimeError(f"{p}: `escenas` tiene que ser un mapa nombre → configuración")
    for name, cfg in esc.items():
        if not isinstance(name, str) or not re.match(r"^[a-z0-9_]+$", name):
            raise RuntimeError(f"{p}: el nombre de escena `{name}` solo admite a-z, 0-9 y _")
        tipos = [k for k in ("facecam", "ancho", "cara") if isinstance(cfg, dict) and k in cfg]
        if len(tipos) != 1 or ("facecam" in cfg and "juego" not in cfg):
            raise RuntimeError(f"{p}: la escena `{name}` tiene que ser {{facecam, juego}}, {{ancho: true}} "
                               f"o {{cara: true}}")
    if sum("facecam" in c for c in esc.values()) > 1:
        raise RuntimeError(f"{p}: solo una escena puede declarar `facecam` (la detectable)")
    if sum("facecam" not in c for c in esc.values()) > 1:
        raise RuntimeError(f"{p}: solo una escena puede ser la de por defecto (sin `facecam`)")


def has_escenas(layout):
    return bool(layout) and "escenas" in layout


def parse_size(s):
    w, h = str(s).lower().split("x")
    return int(w), int(h)


def _crop(rect, sx, sy):
    return "crop={}:{}:{}:{}".format(_even(rect["w"] * sx), _even(rect["h"] * sy),
                                     int(round(rect["x"] * sx)), int(round(rect["y"] * sy)))


def layout_graph(layout, src_w, src_h, tag="0"):
    """Cadena de filtros (empieza en `split`, sin etiquetas de entrada/salida) que deja facecam arriba
    y juego abajo, 1080×810 cada una, sobre un lienzo 1080×1920. Si la fuente no mide lo que dice
    `entrada`, las coordenadas se escalan proporcionalmente."""
    iw, ih = parse_size(layout["entrada"])
    sx, sy = src_w / iw, src_h / ih
    return (f"split=2[lf{tag}][lg{tag}];"
            f"[lf{tag}]{_crop(layout['facecam'], sx, sy)},scale={W}:810:flags=lanczos[ff{tag}];"
            f"[lg{tag}]{_crop(layout['juego'], sx, sy)},scale={W}:810:flags=lanczos[gg{tag}];"
            f"[ff{tag}][gg{tag}]vstack=inputs=2,pad={W}:{H}:0:0:black")


# --- escenas --------------------------------------------------------------------

FACE_Y = 80            # y del recuadro en el 9:16 (escena con facecam)
STRIP_Y = 690          # y de la franja 16:9 (1080×608) en las escenas
STRIP_H = 608
EDGE_DIFF = 8          # salto de brillo (0-255) que cuenta como borde (medido: partida ≥ 0,57 y resto ≤ 0,15)
EDGE_OFF = 2           # px (a DET_W) a cada lado del borde al comparar
EDGE_SEARCH = 40       # px de la fuente en los que se busca el marco, por fuera del recuadro `facecam`
SCENE_THR = 0.35       # fracción mínima del marco (el menor de los dos lados) con borde
MIN_SCENE_S = 1.0      # duración mínima de una escena


def scene_roles(layout):
    """→ (nombre_detectable, nombre_por_defecto|None). La detectable declara `facecam`."""
    esc = layout["escenas"]
    det = next((n for n, c in esc.items() if "facecam" in c), None)
    dflt = next((n for n, c in esc.items() if "facecam" not in c), None)
    return det, dflt


def _scene_canvas(cfg, sx, sy, tag, centers, src_w, src_h):
    """Cadena (sin etiquetas) que deja la escena `cfg` en un lienzo 1080×1920."""
    if "cara" in cfg:
        return track_filter(centers, src_w, src_h)
    fondo = (f"scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,"
             f"scale={W}:{H}:flags=bilinear")
    if "ancho" in cfg:
        return (f"split=2[sa{tag}][sb{tag}];[sa{tag}]{fondo}[bg{tag}];"
                f"[sb{tag}]scale={W}:{STRIP_H}:flags=lanczos[st{tag}];"
                f"[bg{tag}][st{tag}]overlay=0:{STRIP_Y}")
    fc, jg = cfg["facecam"], cfg["juego"]
    fh = _even(W * fc["h"] / fc["w"])
    return (f"split=3[sa{tag}][sb{tag}][sc{tag}];[sa{tag}]{fondo}[bg{tag}];"
            f"[sb{tag}]{_crop(jg, sx, sy)},scale={W}:{STRIP_H}:flags=lanczos[st{tag}];"
            f"[sc{tag}]{_crop(fc, sx, sy)},scale={W}:{fh}:flags=lanczos[fc{tag}];"
            f"[bg{tag}][st{tag}]overlay=0:{STRIP_Y}[bs{tag}];[bs{tag}][fc{tag}]overlay=0:{FACE_Y}")


def _enable(segs):
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segs)


def escenas_graph(layout, src_w, src_h, tag, segments, centers=None):
    """Cadena de encuadre (sin etiquetas de entrada/salida) de una plantilla con `escenas`.
    `segments` = [(t0, t1, nombre)] en s desde el inicio del tramo, de `scene_segments`. Cada escena es un
    lienzo 1080×1920 y la detectable se superpone con `overlay enable=between(t,…)`: corte limpio.
    Si solo aparece una escena, se compone solo esa."""
    iw, ih = parse_size(layout["entrada"])
    sx, sy = src_w / iw, src_h / ih
    esc = layout["escenas"]
    det, dflt = scene_roles(layout)
    usadas = {n for _, _, n in segments}
    if det is None or dflt is None or usadas == {det} or usadas == {dflt}:
        n = next(iter(usadas)) if len(usadas) == 1 else (dflt or det)
        return _scene_canvas(esc[n], sx, sy, tag, centers, src_w, src_h)
    en = _enable([(a, b) for a, b, n in segments if n == det])
    return (f"split=2[ia{tag}][ib{tag}];"
            f"[ia{tag}]{_scene_canvas(esc[dflt], sx, sy, tag + 'd', centers, src_w, src_h)}[cd{tag}];"
            f"[ib{tag}]{_scene_canvas(esc[det], sx, sy, tag + 't', centers, src_w, src_h)}[ct{tag}];"
            f"[cd{tag}][ct{tag}]overlay=0:0:enable='{en}'")


def edge_score(g, rect, sx, sy, d=EDGE_OFF):
    """Fuerza del marco del recuadro `rect` (en px de `entrada`) en el fotograma gris `g` (alto×ancho, int16,
    a escala sx, sy): se busca por fuera del recuadro un borde izquierdo (vertical) y uno superior
    (horizontal) rectos y nítidos, que ocupen el lado entero; → el menor de los dos (0–1)."""
    es = EDGE_SEARCH
    x0, x1 = int(rect["x"] * sx), int((rect["x"] + rect["w"]) * sx)
    y0, y1 = int(rect["y"] * sy), int((rect["y"] + rect["h"]) * sy)
    m = 8
    rows = slice(y0 + m, y1 - m)
    cols = slice(x0 + m, x1 - m)
    best_v = max((np.abs(g[rows, x - d] - g[rows, x + d]) > EDGE_DIFF).mean()
                 for x in range(max(int((rect["x"] - es) * sx), d), x0 - 1))
    best_h = max((np.abs(g[y - d, cols] - g[y + d, cols]) > EDGE_DIFF).mean()
                 for y in range(max(int((rect["y"] - es) * sy), d), y0 - 1))
    return float(min(best_v, best_h))


def detect_scenes(path, a, b, src_w, src_h, layout):
    """Por muestra (DET_FPS, como `detect_faces`) → [True si es la escena detectable]."""
    iw, ih = parse_size(layout["entrada"])
    det, _ = scene_roles(layout)
    rect = layout["escenas"][det]["facecam"]
    dw = DET_W
    dh = _even(src_h * dw / src_w)
    vf = (f"trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,"
          f"fps={DET_FPS},scale={dw}:{dh},format=gray")
    r = subprocess.run([herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf", vf,
                        "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg (detección de escena) falló: {r.stderr.decode()[-300:]}")
    n = len(r.stdout) // (dw * dh)
    frames = np.frombuffer(r.stdout, np.uint8, n * dw * dh).reshape(n, dh, dw).astype(np.int16)
    return [edge_score(g, rect, dw / iw, dh / ih) >= SCENE_THR for g in frames]


def smooth_scenes(flags, min_len=None):
    """Quita los tramos de escena más cortos que `min_len` muestras (por defecto MIN_SCENE_S): el más corto
    se funde con su vecino mayor, repetido hasta que no quede ninguno. → lista de booleanos."""
    min_len = min_len or int(round(MIN_SCENE_S * DET_FPS))
    runs = []
    for f in flags:
        if runs and runs[-1][0] == f:
            runs[-1][1] += 1
        else:
            runs.append([f, 1])
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: runs[k][1])
        if runs[i][1] >= min_len:
            break
        nb = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
        j = max(nb, key=lambda k: runs[k][1])
        runs[j][1] += runs[i][1]
        del runs[i]
        k = 0
        while k < len(runs) - 1:      # vecinos iguales tras fundir
            if runs[k][0] == runs[k + 1][0]:
                runs[k][1] += runs[k + 1][1]
                del runs[k + 1]
            else:
                k += 1
    return [f for f, n in runs for _ in range(n)]


def scene_segments(flags, names, dur):
    """flags (ya suavizados, una muestra cada 1/DET_FPS s) → [(t0, t1, nombre)]. `names` = (detectable,
    por_defecto). El corte cae entre dos muestras (media muestra antes de la primera de la nueva escena)."""
    step = 1.0 / DET_FPS
    segs, start = [], 0
    for i in range(1, len(flags) + 1):
        if i == len(flags) or flags[i] != flags[start]:
            t0 = 0.0 if start == 0 else start * step - step / 2
            t1 = dur if i == len(flags) else i * step - step / 2
            segs.append((t0, t1, names[0] if flags[start] else names[1]))
            start = i
    return segs


def plan_scenes(path, a, b, src_w, src_h, layout, log=None):
    """→ segmentos [(t0, t1, nombre)] del tramo [a, b] (s del fichero), con la escena suavizada."""
    flags = smooth_scenes(detect_scenes(path, a, b, src_w, src_h, layout))
    if not flags:
        return [(0.0, b - a, scene_roles(layout)[1] or scene_roles(layout)[0])]
    return scene_segments(flags, scene_roles(layout), b - a)


def scene_seconds(segments):
    """{nombre: segundos} de unos segmentos."""
    out = {}
    for a, b, n in segments:
        out[n] = out.get(n, 0.0) + (b - a)
    return out


# --- seguimiento de cara --------------------------------------------------------

def crop_width(src_h):
    """Ancho del recorte 9:16 para una fuente de alto src_h (608 para 1080)."""
    return _even(src_h * 9 / 16)


def detect_faces(path, a, b, src_w, src_h):
    """YuNet a DET_FPS sobre [a, b] del fichero (s del fichero: ffmpeg ya resta el inicio del contenedor).
    Devuelve [(cx, ancho_cara)|None] (px de la fuente) con una muestra cada 1/DET_FPS s desde `a`."""
    import cv2
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # sin el aviso de setPreferableTarget
    dw = DET_W
    dh = _even(src_h * dw / src_w)
    det = cv2.FaceDetectorYN.create(str(model()), "", (dw, dh), 0.6, 0.3, 5000)
    vf = (f"trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,"
          f"fps={DET_FPS},scale={dw}:{dh}")
    cmd = [herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg (detección de cara) falló: {r.stderr.decode()[-300:]}")
    n = len(r.stdout) // (dw * dh * 3)
    out = []
    for i in range(n):
        img = np.frombuffer(r.stdout, np.uint8, dw * dh * 3, i * dw * dh * 3).reshape(dh, dw, 3)
        _, faces = det.detect(img)
        if faces is None or len(faces) == 0:
            out.append(None)
        else:
            f = max(faces, key=lambda q: q[2] * q[3])
            out.append((float((f[0] + f[2] / 2) * src_w / dw), float(f[2] * src_w / dw)))
    return out


def smooth(samples, alpha=ALPHA, cw=None, pad=FACE_PAD):
    """Suavizado exponencial del centro x de la cara. Sin cara mantiene el último valor; las primeras
    muestras sin cara toman la primera detección. Todo None → None.
    Con `cw` (ancho del recorte) el centro suavizado nunca deja la cara a menos de `pad` px del borde del
    recorte en las muestras con cara: α = 0,15 a 2 fps va con retraso si la persona se mueve deprisa y la
    cara se salía del encuadre (se midió en el M3); el límite lo evita sin cambiar el suavizado."""
    first = next((c for c in samples if c is not None), None)
    if first is None:
        return None
    out, s = [], first[0]
    for c in samples:
        if c is not None:
            s = s + alpha * (c[0] - s)
            if cw:
                lim = max(cw / 2 - c[1] / 2 - pad, 0.0)
                s = min(max(s, c[0] - lim), c[0] + lim)
        out.append(s)
    return out


def face_ratio(cxs):
    return sum(c is not None for c in cxs) / len(cxs) if cxs else 0.0


def crop_x_expr(centers, step, src_w, cw):
    """Posición x del recorte (esquina izquierda) como expresión de `t` (s desde el inicio del tramo):
    interpolación lineal entre muestras como suma de rampas `clip((t-ti)/step,0,1)` (sin anidar `if`)."""
    xs = [min(max(c - cw / 2, 0), src_w - cw) for c in centers]
    expr = f"{xs[0]:.2f}"
    for i in range(len(xs) - 1):
        d = xs[i + 1] - xs[i]
        if abs(d) >= 0.005:
            expr += f"{d:+.2f}*clip((t-{i * step:.3f})/{step:.3f},0,1)"
    return expr


def track_filter(centers, src_w, src_h):
    """Filtro de recorte: con trayectoria sigue la cara; sin ella (`None`), centrado."""
    cw = crop_width(src_h)
    if centers is None:
        x = f"{(src_w - cw) / 2:.2f}"
    else:
        x = crop_x_expr(centers, 1.0 / DET_FPS, src_w, cw)
    return f"crop={cw}:{src_h}:x='{x}':y=0,scale={W}:{H}:flags=lanczos"


def plan_tracking(path, a, b, src_w, src_h):
    """→ (centers|None, ratio, n_muestras). centers None = recorte centrado (aviso)."""
    cxs = detect_faces(path, a, b, src_w, src_h)
    ratio = face_ratio(cxs)
    if not cxs or ratio <= MIN_FACE_RATIO:
        return None, ratio, len(cxs)
    return smooth(cxs, cw=crop_width(src_h)), ratio, len(cxs)


# --- zoom -----------------------------------------------------------------------

def zoompan_filter(zooms, fps=30, ease=0.25):
    """zoompan con una rampa suave (ease s) de entrada y de salida por cada zoom {t,dur,factor}.
    Se hace en 2× para que el movimiento no vibre; devuelve '' si no hay zooms."""
    if not zooms:
        return ""
    z = "1"
    for zm in zooms:
        t0, t1, f = float(zm["t"]), float(zm["t"]) + float(zm["dur"]), float(zm["factor"])
        z += (f"+{f - 1:.3f}*clip(min((on/{fps}-{t0:.3f})/{ease},({t1:.3f}-on/{fps})/{ease}),0,1)")
    return (f"scale={W * 2}:{H * 2}:flags=bilinear,"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
