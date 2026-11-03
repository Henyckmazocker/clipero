"""stats: métricas públicas de lo publicado. publicados.csv (con url) → yt-dlp -j → piloto.csv.

Sin API key. Solo `yt-dlp -j --skip-download`. Una URL con sufijo `#claim` (short con reclamo de
Content ID) se mide igual, quitando el sufijo, y se marca con claim=1.
"""
import csv
import json
import subprocess
from datetime import date

from . import rutas
from .render import TONOS
from .ingest import warn, ytdlp_bin

PILOTO_COLS = ["fecha_medida", "slug", "vistas", "likes", "comentarios", "suscriptores_canal", "claim"]


def load_publicados(path):
    """[(slug, url_limpia, claim)] de las filas con url."""
    filas = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            url = (r.get("url") or "").strip()
            if not url:
                continue
            claim = url.endswith("#claim")
            if claim:
                url = url[: -len("#claim")]
            filas.append((r["slug"], url, claim))
    return filas


def fetch_metrics(url):
    out = subprocess.run([*ytdlp_bin(), "-j", "--skip-download", "--no-playlist", url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[-300:] or "yt-dlp falló")
    d = json.loads(out.stdout.strip().splitlines()[-1])
    g = lambda k: "" if d.get(k) is None else d[k]  # noqa: E731 (likes ocultos → vacío)
    return {"vistas": g("view_count"), "likes": g("like_count"), "comentarios": g("comment_count"),
            "suscriptores_canal": g("channel_follower_count")}


def append_piloto(path, filas):
    """Añade filas (dicts) a piloto.csv: crea la cabecera si falta y no duplica (fecha, slug, claim)."""
    nuevas = []
    vistas = set()
    existe = path.exists() and path.stat().st_size > 0
    if existe:
        with open(path, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            if rd.fieldnames != PILOTO_COLS:
                raise RuntimeError(f"{path}: cabecera {rd.fieldnames}, esperaba {PILOTO_COLS}")
            vistas = {(r["fecha_medida"], r["slug"], r["claim"]) for r in rd}
    for r in filas:
        k = (r["fecha_medida"], r["slug"], str(r["claim"]))
        if k in vistas:
            continue
        vistas.add(k)
        nuevas.append(r)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, PILOTO_COLS, lineterminator="\n")
        if not existe:
            w.writeheader()
        w.writerows(nuevas)
    return nuevas


def ultimas_filas(piloto_rows):
    """{slug: fila} con la última medida de cada slug (vistas numéricas; la fecha ISO se compara como
    texto y, a igualdad, gana la fila posterior del CSV)."""
    ultima = {}
    for r in piloto_rows:
        try:
            float(r.get("vistas"))
        except (TypeError, ValueError):
            continue
        if r["slug"] not in ultima or r["fecha_medida"] >= ultima[r["slug"]]["fecha_medida"]:
            ultima[r["slug"]] = r
    return ultima


def resumen_por(clave, publicados_rows, piloto_rows):
    """{valor: {"shorts": n, "media": x, "mediana": y}} con la última medida de cada slug.

    `clave` es el nombre de una columna de publicados o una función fila → valor. Un slug de
    publicados sin medidas no cuenta; el valor vacío se agrupa como "(sin <clave>)"."""
    from statistics import mean, median
    ultima = {s: float(r["vistas"]) for s, r in ultimas_filas(piloto_rows).items()}
    f = clave if callable(clave) else (lambda r: r.get(clave))
    nombre = clave if isinstance(clave, str) else "valor"
    grupos = {}
    for r in publicados_rows:
        if r["slug"] in ultima:
            grupos.setdefault((f(r) or "").strip() or f"(sin {nombre})", []).append(ultima[r["slug"]])
    return {t: {"shorts": len(v), "media": round(mean(v)), "mediana": round(median(v))}
            for t, v in grupos.items()}


def resumen_tono(publicados_rows, piloto_rows):
    """{tono: {"shorts": n, "media": x, "mediana": y}}; el tono vacío es "(sin tono)"."""
    return resumen_por("tono", publicados_rows, piloto_rows)


def _leer(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def imprime_resumen_tono(res):
    print(f"{'tono':<11}{'shorts':<8}{'vistas_media':<14}vistas_mediana")
    for t in [*TONOS, "(sin tono)"]:
        d = res.get(t)
        if d:
            print(f"{t:<11}{d['shorts']:<8}{d['media']:<14}{d['mediana']}")
        else:
            print(f"{t:<11}0")


def stats(publicados=None, piloto=None, hoy=None, fetch=fetch_metrics):
    from pathlib import Path
    publicados = Path(publicados) if publicados else rutas.home() / "publicados.csv"
    piloto = Path(piloto) if piloto else rutas.home() / "piloto.csv"
    hoy = hoy or date.today().isoformat()
    vistos = set()
    if piloto.exists() and piloto.stat().st_size > 0:
        with open(piloto, encoding="utf-8", newline="") as f:
            vistos = {(r["fecha_medida"], r["slug"], r["claim"]) for r in csv.DictReader(f)}
    medidas = []
    for slug, url, claim in load_publicados(publicados):
        if (hoy, slug, str(int(claim))) in vistos:
            continue  # ya medido hoy: ni se pide
        try:
            m = fetch(url)
        except RuntimeError as e:
            warn(f"{slug}: no se pudo medir {url}: {e}")
            continue
        medidas.append({"fecha_medida": hoy, "slug": slug, **m, "claim": int(claim)})
    nuevas = append_piloto(piloto, medidas)
    print(f"stats: {len(nuevas)} fila(s) añadidas a {piloto}")
    imprime_resumen_tono(resumen_tono(_leer(publicados), _leer(piloto)))
    return nuevas
