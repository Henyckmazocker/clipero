"""vods y clean: qué VODs recientes quedan por ingerir y limpieza de los tramos de vídeo en caché.

Solo usa `yt-dlp --flat-playlist` y `yt-dlp -j`: nunca baja vídeo. `vods` sale ordenado por `score` (de mayor a
menor, mezclando plataformas): `rel` = vistas del VOD / mediana de `view_count` de la lista plana de su canal y
plataforma, y `score` = `rel` * 0,5 ** (edad en días / VIDA_MEDIA). Las listas planas no traen fecha
(`upload_date`/`timestamp` vienen a null en Twitch y en la pestaña /streams de YouTube), así que se pide
`-j` del VOD, de más nuevo a más viejo, hasta toparse con el primero fuera de la ventana (o con el tope N).
"""
import json
import shutil
import subprocess
import sys
import time

import yaml

from . import rutas
from .ingest import ytdlp_bin, vod_id_from_info, warn

MAX_ENTRADAS = 10  # tope de VODs que se miran por lista
VIDA_MEDIA = 2.0   # días: peso por recencia = 0,5 ** (edad / VIDA_MEDIA)


def flat_playlist(url, n=MAX_ENTRADAS, timeout=None):
    out = subprocess.run([*ytdlp_bin(), "--flat-playlist", "-j", "--playlist-end", str(n), url],
                         capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"yt-dlp --flat-playlist falló en {url}: {out.stderr.strip()[-300:]}")
    return [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]


def vod_info(url):
    out = subprocess.run([*ytdlp_bin(), "-j", "--no-playlist", "--skip-download", url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"yt-dlp -j falló en {url}: {out.stderr.strip()[-300:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def load_sources(path=None):
    return yaml.safe_load((path or rutas.home() / "sources.yaml").read_text(encoding="utf-8")) or []


def twitch_url(canal):
    return f"https://www.twitch.tv/{canal}/videos?filter=archives&sort=time"


def mediana_canal(entradas):
    """Mediana de `view_count` de las entradas de la lista plana (sin is_upcoming/is_live ni view_count None).

    None si no queda ninguna o la mediana es 0.
    """
    v = sorted(e["view_count"] for e in entradas
               if e.get("live_status") not in ("is_upcoming", "is_live") and e.get("view_count") is not None)
    if not v:
        return None
    n = len(v)
    m = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return m or None


def puntua(view_count, mediana, ts, now):
    """→ (score, rel). rel = view_count / mediana (1.0 si falta alguno de los dos);
    score = rel * 0.5 ** (max(now - ts, 0) / 86400 / VIDA_MEDIA). Redondeo: score 3 dec, rel 2 dec."""
    rel = view_count / mediana if view_count is not None and mediana else 1.0
    score = rel * 0.5 ** (max(now - ts, 0) / 86400 / VIDA_MEDIA)
    return round(score, 3), round(rel, 2)


def recent_vods(sources, dias=7, now=None, ingeridos=None, flat=flat_playlist, info=vod_info, fuentes=None):
    """Lista de dicts (plataforma, fuente, vod_id, fecha, duracion, url, titulo, score, rel, vistas),
    ordenada por score descendente (empate: Twitch antes).

    `ingeridos`: ids ya en data/vods/ (por defecto, los que tienen info.json).
    `fuentes`: ids de `sources` a rastrear (None = todas); un id que no existe → RuntimeError.
    """
    if fuentes is not None:
        for f in fuentes:
            if not any(s["id"] == f for s in sources):
                raise RuntimeError(f"fuente desconocida: {f}")
        sources = [s for s in sources if s["id"] in fuentes]
    now = time.time() if now is None else now
    corte = now - dias * 86400
    if ingeridos is None:
        ingeridos = {p.parent.name for p in rutas.vods().glob("*/info.json")}
    res = {"twitch": [], "youtube": []}
    for s in sources:
        for plat, url in (("twitch", twitch_url(s["twitch"]) if s.get("twitch") else None),
                          ("youtube", s.get("youtube"))):
            if not url:
                continue
            try:
                entradas = flat(url)
            except RuntimeError as e:
                warn(f"{s['id']} ({plat}): {e}")
                continue
            mediana = mediana_canal(entradas)  # con todas las entradas, no solo las de la ventana
            for e in entradas:
                if e.get("live_status") in ("is_upcoming", "is_live"):
                    continue
                vurl = e.get("url") or e.get("webpage_url")
                try:
                    d = info(vurl)
                except RuntimeError as err:
                    warn(f"{s['id']} ({plat}): {err}")
                    continue
                ts = d.get("timestamp") or d.get("release_timestamp")
                if ts is None:
                    warn(f"{s['id']} ({plat}): {vurl} sin fecha, se salta")
                    continue
                if ts < corte:
                    break  # las listas vienen de más nuevo a más viejo
                vid = vod_id_from_info(d)
                if vid in ingeridos:
                    continue
                vistas = d.get("view_count")
                if vistas is None:
                    vistas = e.get("view_count")
                score, rel = puntua(vistas, mediana, ts, now)
                res[plat].append({
                    "plataforma": plat, "fuente": s["id"], "vod_id": vid,
                    "fecha": time.strftime("%Y-%m-%d", time.gmtime(ts)),
                    "duracion": int(d.get("duration") or 0),
                    "url": d.get("webpage_url") or vurl, "titulo": d.get("title") or "",
                    "score": score, "rel": rel, "vistas": vistas,
                })
    return sorted(res["twitch"] + res["youtube"], key=lambda r: (-r["score"], r["plataforma"] != "twitch"))


def vods(dias=7, fuentes=None):
    filas = recent_vods(load_sources(), dias, fuentes=fuentes)
    if not filas:
        print(f"Sin VODs nuevos en los últimos {dias} días.")
    for f in filas:
        h, m = divmod(f["duracion"] // 60, 60)
        vistas = "" if f["vistas"] is None else f["vistas"]
        print(f"{f['score']:.3f}\t{f['rel']:.2f}×\t{f['plataforma']}\t{f['fuente']}\t{f['vod_id']}\t"
              f"{f['fecha']}\t{h}h{m:02d}\t{vistas}\t{f['url']}\t{f['titulo']}")
    return filas


def clean_seg(dias=14, now=None, root=None):
    """Borra data/vods/*/seg/ cuyo fichero más reciente tenga más de `dias` días. Devuelve los borrados."""
    now = time.time() if now is None else now
    corte = now - dias * 86400
    borrados = []
    for seg in sorted((root or rutas.vods()).glob("*/seg")):
        if not seg.is_dir():
            continue
        mt = max([p.stat().st_mtime for p in seg.rglob("*")] + [seg.stat().st_mtime])
        if mt < corte:
            shutil.rmtree(seg)
            borrados.append(seg)
    return borrados


def clean(dias=14):
    b = clean_seg(dias)
    for p in b:
        print(f"borrado {p}")
    print(f"clean: {len(b)} carpeta(s) seg/ de más de {dias} días borradas")
    return b
