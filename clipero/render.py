"""render: short.yaml → out/<fecha>/<slug>.mp4 + <slug>.meta.md.

1. Valida el short.yaml contra la tabla de rótulos mínimos (`REGLAS`) y comprueba, antes de bajar nada,
   que cada tramo cae en una ventana ya transcrita y no toca un segmento silenciado. Si algo falla,
   sale con error y no crea ningún fichero en `out/`.
2. Baja los tramos en vídeo (`fetch_section`, caché en `data/vods/<id>/seg/`).
3. Encuadre por tramo (layout, escenas por muestra o seguimiento de cara) → concat → zoompan → drawtext → ass.
4. Exporta H.264 crf 20, AAC 160 k, 1080×1920, 30 fps. Escribe el meta.md y avisa de música.
El trabajo intermedio (ASS, textos, filtro) vive en `data/render/<slug>/`, nunca en `out/`.
"""
import json
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

import numpy as np
import yaml

from . import herramientas, rutas
from . import frame, subs
from .fetch import fetch_section, probe_duration

FPS = 30
DUR_MIN, DUR_MAX = 20.0, 59.0
CREDITO_DUR = 1.5
TIPOS = ("gancho", "transicion", "desenlace")
FORMATOS = ("arco", "momento", "recopilacion")
TONOS = ("critica", "positivo", "neutro")
ESCENAS_ROT_Y = 1100   # rótulos con escenas: sobre la parte baja de la franja 16:9, sin tapar el recuadro ni los subtítulos
TW_FMT = "1080p60/best[height<=1080]"

# Tabla de rótulos mínimos (contrato del plan). Cada formato: nº de tramos, VODs, y lo obligatorio.
REGLAS = {
    "arco": {"tramos": (2, 3), "vods": "uno", "obligatorios": ("gancho",), "gancho_en_cero": True},
    "momento": {"tramos": (1, 1), "vods": "uno", "obligatorios": ("gancho",), "gancho_en_cero": True,
                "max_s": 45.0, "zoom_min": 1},
    "recopilacion": {"tramos": (3, 5), "vods": "varios", "obligatorios": ("gancho",),
                     "gancho_en_cero": True},
}


# --- carga y validación (puras) -------------------------------------------------

def load_spec(path):
    try:
        spec = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise RuntimeError(f"no puedo leer {path}: {e}")
    if not isinstance(spec, dict):
        raise RuntimeError(f"{path}: no es un mapa YAML")
    for t in spec.get("tramos") or []:
        if isinstance(t, dict) and "vod" in t:
            t["vod"] = str(t["vod"])
    return spec


def total_dur(spec):
    return sum(float(t["end"]) - float(t["start"]) for t in spec["tramos"])


def tramo_starts(spec):
    out, t = [], 0.0
    for tr in spec["tramos"]:
        out.append(t)
        t += float(tr["end"]) - float(tr["start"])
    return out


def validate(spec):
    """short.yaml (dict) → lista de errores (vacía = válido). No toca disco."""
    err = []
    fmt = spec.get("formato")
    if fmt not in REGLAS:
        return [f"`formato` debe ser uno de {', '.join(FORMATOS)} (hay {fmt!r})"]
    r = REGLAS[fmt]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(spec.get("slug", ""))):
        err.append("`slug` obligatorio, en minúsculas, dígitos y guiones")
    if not spec.get("titulo"):
        err.append("`titulo` obligatorio")
    if spec.get("tono") not in TONOS:
        err.append(f"`tono` obligatorio: {' | '.join(TONOS)} (hay {spec.get('tono')!r})")
    if spec.get("voz"):
        err.append("`voz:` está reservado para el plan B y todavía no se mezcla")
    tramos = spec.get("tramos") or []
    lo, hi = r["tramos"]
    if not lo <= len(tramos) <= hi:
        err.append(f"{fmt}: hacen falta {lo}–{hi} tramos (hay {len(tramos)})")
    ok_t = True
    for i, t in enumerate(tramos, 1):
        try:
            if not (t["vod"] and float(t["end"]) > float(t["start"]) >= 0):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            err.append(f"tramo {i}: necesita `vod`, `start` y `end` con end > start >= 0")
            ok_t = False
    if not ok_t or not tramos:
        return err
    vods = {t["vod"] for t in tramos}
    if r["vods"] == "uno" and len(vods) != 1:
        err.append(f"{fmt}: todos los tramos deben ser del mismo VOD (hay {len(vods)})")
    if r["vods"] == "varios" and len(vods) < 2:
        err.append(f"{fmt}: los tramos deben ser de al menos 2 VODs (hay {len(vods)})")
    total = total_dur(spec)
    if not DUR_MIN <= total <= DUR_MAX:
        err.append(f"duración {total:.1f} s fuera de {DUR_MIN:.0f}–{DUR_MAX:.0f} s "
                   f"(incluye el crédito final de {CREDITO_DUR} s)")
    if "max_s" in r and total > r["max_s"]:
        err.append(f"{fmt}: el tramo continuo no puede pasar de {r['max_s']:.0f} s (hay {total:.1f})")
    rot = spec.get("rotulos") or []
    clean = []
    for i, x in enumerate(rot, 1):
        try:
            t, d = float(x["t"]), float(x["dur"])
            tipo, txt = x["tipo"], str(x["texto"]).strip()
        except (KeyError, TypeError, ValueError):
            err.append(f"rótulo {i}: necesita t, dur, tipo y texto")
            continue
        if tipo == "numero":
            err.append(f"rótulo {i}: el tipo `numero` ya no existe (no hay rótulos numerados); "
                       "quítalo")
        elif tipo not in TIPOS:
            err.append(f"rótulo {i}: tipo {tipo!r} desconocido (válidos: {', '.join(TIPOS)}; "
                       "el crédito se añade solo)")
        if not txt:
            err.append(f"rótulo {i}: texto vacío")
        if d <= 0 or t < 0 or t + d > total + 0.01:
            err.append(f"rótulo {i} ({tipo}): [{t}, {t + d}] fuera del short (0–{total:.1f} s)")
        clean.append((t, d, tipo, txt))
    for a in range(len(clean)):
        for b in range(a + 1, len(clean)):
            (t1, d1, k1, _), (t2, d2, k2, _) = clean[a], clean[b]
            if t1 < t2 + d2 - 0.01 and t2 < t1 + d1 - 0.01:
                err.append(f"los rótulos {k1} (t={t1}) y {k2} (t={t2}) se solapan")
    byt = {}
    for t, d, k, txt in clean:
        byt.setdefault(k, []).append((t, d, txt))
    for k in r["obligatorios"]:
        if k not in byt:
            err.append(f"{fmt}: falta el rótulo obligatorio `{k}`")
    if r.get("gancho_en_cero") and "gancho" in byt and not any(abs(t) < 0.05 for t, _, _ in byt["gancho"]):
        err.append(f"{fmt}: el `gancho` debe empezar en t=0")
    zooms = spec.get("zoom") or []
    if len(zooms) < r.get("zoom_min", 0):
        err.append(f"{fmt}: hace falta al menos {r['zoom_min']} `zoom`")
    for i, z in enumerate(zooms, 1):
        try:
            t, d, f = float(z["t"]), float(z["dur"]), float(z["factor"])
            if not (d > 0 and t >= 0 and t + d <= total + 0.01 and 1.0 < f <= 2.0):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            err.append(f"zoom {i}: necesita t, dur y factor (1 < factor ≤ 2) dentro del short")
    return err


# --- fuentes y créditos ---------------------------------------------------------

def load_sources(path=None):
    p = path or rutas.home() / "sources.yaml"
    return {s["id"]: s for s in (yaml.safe_load(p.read_text()) or [])}


def source_of_info(info, sources):
    """id de la fuente de un VOD según su info.json (uploader_id frente a twitch/youtube de sources)."""
    up = str(info.get("uploader_id") or info.get("channel_id") or "").lstrip("@").lower()
    if not up:
        return None
    for sid, s in sources.items():
        if up == str(s.get("twitch", "")).lower() or (s.get("youtube") and f"@{up}" in s["youtube"].lower()):
            return sid
    return None


def creditos(spec, sources, vod_src):
    """Créditos únicos, en orden de aparición. Recopilación: el de cada VOD (con `fuente` de respaldo);
    el resto: el de `fuente`."""
    ids = []
    if spec["formato"] == "recopilacion":
        for t in spec["tramos"]:
            ids.append(vod_src.get(t["vod"]) or spec.get("fuente"))
    else:
        ids.append(spec.get("fuente") or vod_src.get(spec["tramos"][0]["vod"]))
    out = []
    for i in ids:
        s = sources.get(i)
        if not s or not s.get("credito"):
            raise RuntimeError(f"sin `credito` en sources.yaml para la fuente {i!r}; "
                               "pon `fuente:` en el short.yaml o completa sources.yaml")
        if s["credito"] not in out:
            out.append(s["credito"])
    return out


# --- ventanas transcritas, muted ------------------------------------------------

def find_words(vod, a, b):
    """Palabras (s del VOD) de la ventana transcrita que contiene [a, b]. Error con la orden a lanzar."""
    d = rutas.vods() / vod
    cands = json.loads((d / "candidatos.json").read_text()) if (d / "candidatos.json").exists() else []
    cover = [c for c in cands if c["start"] - 0.5 <= a and b <= c["end"] + 0.5]
    for c in cover:
        f = d / "win" / f"{c['n']}.words.json"
        if f.exists():
            return json.loads(f.read_text())
    if cover:
        n = " ".join(str(c["n"]) for c in cover)
        raise RuntimeError(f"tramo {vod} {a}-{b}: la ventana {n} no está transcrita; "
                           f"lanza `clipero transcribe {vod} {n}`")
    raise RuntimeError(f"tramo {vod} {a}-{b} no cae dentro de ninguna ventana de candidatos.json; "
                       "elige un tramo dentro de una ventana (y transcríbela con `clipero transcribe`)")


def check_muted(vod, a, b):
    f = rutas.vods() / vod / "muted.json"
    if f.exists():
        for lo, hi in json.loads(f.read_text()):
            if a < hi and b > lo:
                raise RuntimeError(f"tramo {vod} {a}-{b} toca un segmento silenciado por DMCA ({lo}-{hi}); elige otro")


def vod_info(vod):
    f = rutas.vods() / vod / "info.json"
    if not f.exists():
        raise RuntimeError(f"VOD {vod} no ingerido (falta {f}); lanza `clipero ingest <url>`")
    info = json.loads(f.read_text())
    plat = "twitch" if str(info.get("extractor", "")).startswith("twitch") else "youtube"
    return info, plat


# --- descarga con caché ---------------------------------------------------------

def probe_stream_starts(path):
    """(start_video, start_audio, w, h, fps) de un fichero, con ffprobe."""
    r = subprocess.run([herramientas.ruta("ffprobe") or "ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,start_time,width,height,avg_frame_rate", "-of", "json", str(path)],
                       capture_output=True, text=True)
    st = json.loads(r.stdout or "{}").get("streams", [])
    v = next((s for s in st if s["codec_type"] == "video"), None)
    a = next((s for s in st if s["codec_type"] == "audio"), None)
    if not v or not a:
        raise RuntimeError(f"{path}: el tramo bajado no trae vídeo y audio")
    return float(v.get("start_time") or 0), float(a.get("start_time") or 0), int(v["width"]), int(v["height"])


def get_segment(vod, plat, a, b):
    """→ (ruta, offset_real, descargado). Caché en data/vods/<id>/seg/."""
    d = rutas.vods() / vod / "seg"
    d.mkdir(parents=True, exist_ok=True)
    name = f"{round(a * 100)}_{round(b * 100)}"
    f, side = d / f"{name}.mp4", d / f"{name}.json"
    if f.exists() and side.exists() and f.stat().st_size > 10_000:
        return f, json.loads(side.read_text())["offset"], False
    f.unlink(missing_ok=True)
    if plat == "twitch":
        path, off = fetch_section(vod, plat, a, b, f, audio_only=False, fmt=TW_FMT)
    else:  # +1 s al final para no quedarnos cortos en el último fotograma
        path, off = fetch_section(vod, plat, a, b + 1.0, f, audio_only=False)
    side.write_text(json.dumps({"offset": off}))
    return f, off, True


# --- filtros --------------------------------------------------------------------

def esc(p):
    """Escapa una ruta para un valor de filtro de ffmpeg."""
    return re.sub(r"([\\:',\[\];])", r"\\\1", str(p))


def wrap_text(texto, width):
    lines = []
    for par in str(texto).split("\n"):
        lines += textwrap.wrap(par, width) or [""]
    return lines


def font():
    return rutas.fuentes() / "Montserrat-ExtraBold.ttf"


def fontsdir():
    return rutas.fuentes()


def rel(p):
    """Ruta relativa a home() (ffmpeg corre con cwd=home()) o absoluta si cae fuera (p. ej. las fuentes)."""
    p, h = Path(p), rutas.home()
    return p.relative_to(h) if p.is_absolute() and h in p.parents else p


def load_branding(path=None):
    """branding.yaml → dict, o None si no existe o está todo vacío (sin marca)."""
    p = Path(path) if path else rutas.home() / "branding.yaml"
    if not p.exists():
        return None
    d = yaml.safe_load(p.read_text()) or {}
    d = {k: v for k, v in d.items() if v not in (None, "")}
    return d or None


def drawtext(textfile, lines, t0, t1, y, fsize=64, maxfs=None, boxcolor="black@0.7"):
    """drawtext de un rótulo. El texto va en un fichero (`textfile`, `expansion=none`): así no hay que
    escapar `:`, `'`, `%` ni comas del texto. Reduce el cuerpo si una palabra no cabe."""
    longest = max((len(l) for l in lines), default=1)
    fs = min(fsize, int(928 / (0.66 * longest)))
    return (f"drawtext=fontfile={esc(font())}:textfile={esc(rel(textfile))}:expansion=none:text_align=center:fontsize={fs}:"
            f"fontcolor=white:line_spacing=10:box=1:boxcolor={boxcolor}:boxborderw=26:"
            f"x=(w-text_w)/2:y={y}:enable='between(t,{t0:.2f},{t1:.2f})'")


def watermark_filter(branding, workdir, total):
    """Marca de agua del canal arriba a la izquierda durante todo el clip ('' sin marca)."""
    if not branding or not branding.get("marca_agua"):
        return ""
    tf = workdir / "marca.txt"
    tf.write_text(branding["marca_agua"])
    color = branding.get("color", "0x2A6FDB")
    return (f"drawtext=fontfile={esc(font())}:textfile={esc(rel(tf))}:expansion=none:fontsize=30:"
            f"fontcolor=white:box=1:boxcolor={color}@0.9:boxborderw=12:x=40:y=26:"
            f"enable='between(t,0,{total:.2f})'")


def rotulo_filters(spec, creds, workdir, y, branding=None):
    """drawtext de los rótulos del yaml + el crédito final fijo (últimos 1,5 s) + la marca de agua.
    Con marca, el gancho lleva el color de la marca de fondo."""
    total = total_dur(spec)
    fl = []
    wm = watermark_filter(branding, workdir, total)
    if wm:
        fl.append(wm)
    gancho_box = f"{branding.get('color', '0x2A6FDB')}@0.92" if branding else "black@0.7"
    for i, x in enumerate(spec.get("rotulos") or []):
        lines = wrap_text(x["texto"], 23)
        tf = workdir / f"rot{i}.txt"
        tf.write_text("\n".join(lines))
        box = gancho_box if x.get("tipo") == "gancho" else "black@0.7"
        fl.append(drawtext(tf, lines, float(x["t"]), float(x["t"]) + float(x["dur"]), y, boxcolor=box))
    clines = []
    for i, c in enumerate(creds):
        clines += wrap_text(("Fuente: " if i == 0 else "") + c, 28)
    tf = workdir / "credito.txt"
    tf.write_text("\n".join(clines))
    fl.append(drawtext(tf, clines, total - CREDITO_DUR, total, "h-text_h-90", fsize=50))
    return fl


def build_filtergraph(spec, infos, framings, creds, ass_path, workdir, rot_y, zoom, branding=None):
    """infos[i] = (sv, sa, w, h, offset) del segmento i; framings[i] = cadena de encuadre (sin etiquetas).
    Devuelve el texto del filtergraph con salidas [v] y [a]."""
    fc = []
    n = len(spec["tramos"])
    for i, (t, (sv, sa, w, h, off), fr) in enumerate(zip(spec["tramos"], infos, framings)):
        a, b = float(t["start"]) - off, float(t["end"]) - off
        # ffmpeg ya resta el inicio del contenedor (min de los streams) a las dos pistas: t=0 del fichero
        # es el `offset` del VOD, y la diferencia vídeo/audio se conserva.
        fc.append(f"[{i}:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,"
                  f"fps={FPS},{fr},setsar=1[v{i}]")
        fc.append(f"[{i}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                  f"aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    fc.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    chain = [zoom] if zoom else []
    chain += rotulo_filters(spec, creds, workdir, rot_y, branding)
    chain.append(f"ass={esc(rel(ass_path))}:fontsdir={esc(fontsdir())}")
    chain.append("format=yuv420p")
    fc.append("[vc]" + ",".join(chain) + "[v]")
    return ";\n".join(fc)


# --- música ---------------------------------------------------------------------

MUSIC_VOICE_BAND = (80.0, 3400.0)   # Hz; fuera de esta banda = «no voz»
MUSIC_RATIO = 0.35                  # proporción de energía fuera de banda para marcar un segundo
MUSIC_SECONDS = 5                   # segundos seguidos por encima para avisar


def music_ratios(samples, sr):
    """Proporción de energía fuera de la banda de voz, por segundo (los segundos casi mudos → nan)."""
    n, hop = 2048, 1024
    win = np.hanning(n)
    nfr = 1 + (len(samples) - n) // hop
    if nfr < 1:
        return np.array([])
    idx = np.arange(n)[None, :] + hop * np.arange(nfr)[:, None]
    spec = np.abs(np.fft.rfft(samples[idx] * win, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    inside = (f >= MUSIC_VOICE_BAND[0]) & (f <= MUSIC_VOICE_BAND[1])
    tot = spec.sum(axis=1)
    out_e = spec[:, ~inside].sum(axis=1)
    per_s = int(sr // hop)
    res = []
    for k in range(nfr // per_s):
        t, o = tot[k * per_s:(k + 1) * per_s].sum(), out_e[k * per_s:(k + 1) * per_s].sum()
        res.append(o / t if t > 1e-6 * per_s * n else np.nan)
    return np.array(res)


def music_warning(ratios, thr=MUSIC_RATIO, secs=MUSIC_SECONDS):
    """Heurística: ≥ `secs` segundos seguidos con más de `thr` de la energía fuera de la banda de voz
    (graves/agudos sostenidos = probablemente música). Solo avisa. → texto del aviso o None."""
    run = best = 0
    end = 0
    for i, r in enumerate(ratios):
        run = run + 1 if (not np.isnan(r) and r > thr) else 0
        if run > best:
            best, end = run, i
    if best >= secs:
        return f"posible música de fondo ({best} s seguidos fuera de la banda de voz, hasta t={end + 1} s)"
    return None


def audio_samples(path, sr=22050):
    r = subprocess.run([herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32), sr


# --- meta.md --------------------------------------------------------------------

def fmt_dur(s):
    return f"{s:.1f}".replace(".", ",")


def write_meta(path, spec, creds, infos_vod, total, encuadre, avisos, branding=None):
    pl = [p for _, p in infos_vod.values()]
    fuente = spec.get("fuente") or ""
    donde = {}
    for t in spec["tramos"]:
        mins = donde.setdefault(t["vod"], [])
        m = int(float(t["start"]) // 60)
        if m not in mins:
            mins.append(m)
    partes = []
    for vod, mins in donde.items():
        info, _ = infos_vod[vod]
        d = str(info.get("upload_date", ""))
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else "?"
        partes.append(f"directo del {d}, min {', '.join(map(str, mins))}")
    desc = (spec.get("descripcion") or spec["titulo"]).strip().replace("\n", "\\n")
    tags = spec.get("hashtags") or " ".join(
        [f"#{fuente}"] * bool(fuente) + sorted({f"#{p}" for p in pl}) + ["#streamer"])
    fuente_txt = "Fuente: " + " · ".join(creds) + " — " + "; ".join(partes) + "."
    if branding and branding.get("linea_descripcion"):
        fuente_txt += "\\n" + branding["linea_descripcion"].strip()
    if branding and branding.get("hashtag") and branding["hashtag"] not in tags.split():
        tags = f"{branding['hashtag']} {tags}"
    txt = (f"**Título:** {spec['titulo']} #shorts\n"
           f"**Descripción:** {desc}\\n{fuente_txt}\n"
           f"**Hashtags:** {tags}\n"
           f"**Formato:** {spec['formato']} · **Tono:** {spec.get('tono') or '?'} · **Duración:** {fmt_dur(total)} s · **Encuadre:** {encuadre}\n"
           f"**Avisos:** {'; '.join(avisos) if avisos else 'ninguno'}\n")
    Path(path).write_text(txt)


# --- orquestación ---------------------------------------------------------------

def out_dir_for(spec_path):
    p = Path(spec_path).resolve()
    if p.parent.parent == rutas.home() / "out" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.parent.name):
        return p.parent
    return rutas.home() / "out" / date.today().isoformat()


def render(spec_path, log=print):
    spec = load_spec(spec_path)
    err = validate(spec)
    if err:
        raise RuntimeError(f"{spec_path}: no válido, no se renderiza:\n  - " + "\n  - ".join(err))
    sources = load_sources()
    tramos = spec["tramos"]
    vods = {}
    for t in tramos:
        if t["vod"] not in vods:
            vods[t["vod"]] = vod_info(t["vod"])
    vod_src = {v: source_of_info(i, sources) for v, (i, _) in vods.items()}
    creds = creditos(spec, sources, vod_src)
    branding = load_branding()
    # lo que puede fallar sin red: ventanas transcritas y segmentos silenciados
    words = []
    for t in tramos:
        a, b = float(t["start"]), float(t["end"])
        check_muted(t["vod"], a, b)
        words.append(find_words(t["vod"], a, b))
    slug, total = spec["slug"], total_dur(spec)
    work = rutas.home() / "data" / "render" / slug
    work.mkdir(parents=True, exist_ok=True)

    # descarga (con caché) y encuadre
    segs, infos, framings, enc, avisos = [], [], [], [], []
    escena_s = {}   # segundos por escena, de todos los tramos con `escenas`
    for i, t in enumerate(tramos):
        a, b = float(t["start"]), float(t["end"])
        plat = vods[t["vod"]][1]
        seg, off, nuevo = get_segment(t["vod"], plat, a, b)
        log(f"tramo {i + 1}: {t['vod']} {a}-{b} → {seg.relative_to(rutas.home())} (offset {off}; "
            f"{'bajado' if nuevo else 'en caché'})")
        sv, sa, w, h = probe_stream_starts(seg)
        log(f"  inicio de stream vídeo={sv:.3f} audio={sa:.3f} · {w}x{h}")
        m0 = min(sv, sa)
        if off > a + 0.1 or max(sv, sa) - m0 > (a - off) + 0.1:
            raise RuntimeError(f"el segmento {seg} (vídeo desde {off + sv - m0:.2f}, audio desde "
                               f"{off + sa - m0:.2f}) no cubre el inicio del tramo en {a}")
        segs.append(seg)
        infos.append((sv, sa, w, h, off))
        src = vod_src.get(t["vod"]) or spec.get("fuente")
        lay = frame.load_layout(src, vod=t["vod"]) if src else None
        if lay:
            lp = frame.layout_path(src, t["vod"])
            lp = lp if lp.exists() else frame.layout_path(src)
            log(f"  layout {lp.relative_to(rutas.home())}")
        if frame.has_escenas(lay):
            for k in lay["escenas"]:
                escena_s.setdefault(k, 0.0)
            segs_e = frame.plan_scenes(seg, a - off, b - off, w, h, lay)
            centers = None
            if "cara" in lay["escenas"].get(frame.scene_roles(lay)[1] or "", {}):
                centers, _, _ = frame.plan_tracking(seg, a - off, b - off, w, h)
            framings.append(frame.escenas_graph(lay, w, h, str(i), segs_e, centers))
            enc.append("escenas")
            for k, v in frame.scene_seconds(segs_e).items():
                escena_s[k] = escena_s.get(k, 0.0) + v
            log("  encuadre: escenas " + ", ".join(f"{n} {t0:.1f}-{t1:.1f}" for t0, t1, n in segs_e))
        elif lay:
            framings.append(frame.layout_graph(lay, w, h, str(i)))
            enc.append("layout")
        else:
            centers, ratio, n = frame.plan_tracking(seg, a - off, b - off, w, h)
            framings.append(frame.track_filter(centers, w, h))
            if centers is None:
                enc.append("centrado (aviso)")
                avisos.append(f"sin cara en el tramo {i + 1} ({ratio:.0%} de {n} muestras): recorte centrado")
            else:
                enc.append("cara")
            log(f"  encuadre: {enc[-1]} (cara en {ratio:.0%} de {n} muestras)")
    all_layout = all(e == "layout" for e in enc)

    # subtítulos
    starts = tramo_starts(spec)
    events = []
    for i, t in enumerate(tramos):
        y = {"layout": subs.Y_LAYOUT, "escenas": subs.Y_ESCENAS}.get(enc[i], subs.Y_SIN_LAYOUT)
        events += subs.tramo_events(words[i], float(t["start"]), float(t["end"]), starts[i], y)
    ass = work / "short.ass"
    ass.write_text(subs.build_ass(events))

    zoom = frame.zoompan_filter(spec.get("zoom") or [], FPS)
    graph = build_filtergraph(spec, infos, framings, creds, ass, work,
                              1250 if all_layout else (ESCENAS_ROT_Y if all(e == "escenas" for e in enc) else 160),
                              zoom, branding)
    # los textos de rótulos se escribieron con rutas relativas a home()
    fgs = work / "filter.txt"
    fgs.write_text(graph)
    partial = work / f"{slug}.partial.mp4"
    partial.unlink(missing_ok=True)
    cmd = [herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-y"]
    for s in segs:
        cmd += ["-i", str(s)]
    # el grafo va en línea: -filter_complex_script no existe en ffmpeg 8 (filter.txt queda solo para depurar)
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", "[ac]", "-r", str(FPS),
            "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(partial)]
    log("ffmpeg …")
    r = subprocess.run(cmd, cwd=rutas.home(), capture_output=True, text=True)
    if r.returncode == 0 and partial.exists() and abs(probe_duration(partial) - total) > 0.5:
        r.returncode, r.stderr = 1, f"salida de {probe_duration(partial):.2f} s en vez de {total:.2f} s"
    if r.returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg falló: {r.stderr.strip()[-600:]}")

    s, sr = audio_samples(partial)
    ratios = music_ratios(s, sr)
    log("música: proporción fuera de banda por segundo (máx {:.2f}, mediana {:.2f})".format(
        np.nanmax(ratios) if len(ratios) else 0, np.nanmedian(ratios) if len(ratios) else 0))
    m = music_warning(ratios)
    if m:
        avisos.append(m)
    out = out_dir_for(spec_path)
    out.mkdir(parents=True, exist_ok=True)
    final = out / f"{slug}.mp4"
    shutil.move(str(partial), final)
    if escena_s:
        tot = sum(escena_s.values()) or 1.0
        txt = "escenas (" + ", ".join(f"{n} {round(100 * t / tot)} %" for n, t in escena_s.items()) + ")"
        enc = [txt if e == "escenas" else e for e in enc]
    encuadre = enc[0] if len(set(enc)) == 1 else " + ".join(f"t{i + 1}:{e}" for i, e in enumerate(enc))
    write_meta(out / f"{slug}.meta.md", spec, creds, vods, total, encuadre, avisos, branding)
    log(f"OK {final}")
    return final
