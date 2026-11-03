"""Rendimiento: series, agregados y totales a partir de piloto.csv + publicados.csv."""
from datetime import date
from pathlib import Path

from .. import stats

DOW = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
OBJETIVO_SEMANAL = 21   # 3 al día


def _leer(path):
    return stats._leer(Path(path))


def _fecha(txt):
    try:
        return date.fromisoformat((txt or "").strip())
    except ValueError:
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    n = _num(v)
    return None if n is None else int(n)


def _dow(fila):
    d = _fecha(fila.get("fecha"))
    return DOW[d.weekday()] if d else ""


def _thumb(root, slug):
    """URL de la miniatura si hay mp4 en out/*/ (la carpeta puede no ser la fecha de publicación)."""
    mp4s = sorted((Path(root) / "out").glob(f"*/{slug}.mp4"))
    return f"/api/thumbs/{mp4s[-1].parent.name}/{slug}.jpg" if mp4s else None


def rendimiento(root, hoy=None) -> dict:
    root = Path(root)
    hoy = _fecha(hoy) if isinstance(hoy, str) else (hoy or date.today())
    pub_rows = [r for r in _leer(root / "publicados.csv") if (r.get("slug") or "").strip()]
    pil_rows = _leer(root / "piloto.csv")
    ultimas = stats.ultimas_filas(pil_rows)
    por_slug = {r["slug"]: r for r in pub_rows}   # si un slug se repite, gana la última fila

    publicados = []
    for slug, r in por_slug.items():
        u = ultimas.get(slug)
        url = (r.get("url") or "").strip()
        claim = url.endswith("#claim")
        f = _fecha(r.get("fecha"))
        publicados.append({
            "slug": slug, "fecha": r.get("fecha", ""), "fuente": r.get("fuente", ""),
            "tono": r.get("tono", ""), "formato": r.get("formato", ""),
            "url": url[: -len("#claim")] if claim else url, "claim": claim,
            "dias": (hoy - f).days if f else 0,
            "vistas": _int(u["vistas"]) if u else None,
            "likes": _int(u.get("likes")) if u else None,
            "comentarios": _int(u.get("comentarios")) if u else None,
            "thumb": _thumb(root, slug),
        })

    # series: un punto por (slug, día); si hay dos filas el mismo día (claim 0 y 1) gana la última.
    series = {}
    for r in pil_rows:
        p = por_slug.get(r["slug"])
        v, f, m = _num(r.get("vistas")), _fecha(p.get("fecha")) if p else None, _fecha(r.get("fecha_medida"))
        if v is None or f is None or m is None:
            continue
        series.setdefault(r["slug"], {})[(m - f).days] = int(v)
    series = {s: [{"dia": d, "vistas": v} for d, v in sorted(pts.items())] for s, pts in series.items()}

    suscriptores = {}
    for r in pil_rows:
        n = _num(r.get("suscriptores_canal"))   # vacío (vídeo oculto) se salta, no es 0
        if n is not None and r.get("fecha_medida"):
            suscriptores[r["fecha_medida"]] = int(n)

    semanas = {}
    for r in por_slug.values():
        f = _fecha(r.get("fecha"))
        if f:
            y, w, _ = f.isocalendar()
            semanas[f"{y}-W{w:02d}"] = semanas.get(f"{y}-W{w:02d}", 0) + 1

    pub_list = list(por_slug.values())
    return {
        "ultima_medida": max((r["fecha_medida"] for r in pil_rows if r.get("fecha_medida")), default=None),
        "publicados": publicados,
        "series": series,
        "agregados": {"tono": stats.resumen_por("tono", pub_list, pil_rows),
                      "fuente": stats.resumen_por("fuente", pub_list, pil_rows),
                      "formato": stats.resumen_por("formato", pub_list, pil_rows),
                      "dow": stats.resumen_por(_dow, pub_list, pil_rows)},
        "canal": {
            "vistas_total": sum(int(float(u["vistas"])) for s, u in ultimas.items() if s in por_slug),
            "suscriptores": [{"fecha": k, "n": v} for k, v in sorted(suscriptores.items())],
            "por_semana": [{"semana": k, "n": n, "objetivo": OBJETIVO_SEMANAL} for k, n in sorted(semanas.items())],
        },
    }
