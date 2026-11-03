"""score: fusión de señales → candidatos.json (10-15 ventanas por VOD).

Fórmula por plataforma:
- YouTube con heatmap y chat: 0.6·heatmap_norm + 0.4·min(chat_z/4, 1)
- YouTube con heatmap sin chat: heatmap_norm
- YouTube sin heatmap: VOD descartado con aviso
- Twitch: min(chat_z/4, 1)
Ventana = pico −90 s / +30 s. Se descartan las que solapan >50 % con publicados.csv (mismo vod_id)
y, en Twitch, las que tocan un segmento -muted.
"""
import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np

from . import rutas

BUCKET = 10          # s
PRE, POST = 90.0, 30.0
SEP = PRE + POST     # separación mínima entre picos: las ventanas elegidas no se solapan
MAX_CANDS = 15
HALF = 30            # cubos a cada lado = mediana móvil de 10 min


def warn(msg):
    print(f"AVISO: {msg}", file=sys.stderr)


def chat_zscores(times, duration):
    """Cubos de 10 s → (conteos, z) con z = (n − mediana móvil de 10 min) / desviación en la ventana."""
    nb = int(duration // BUCKET) + 1
    cnt = np.zeros(nb)
    for t in times:
        cnt[min(max(int(t // BUCKET), 0), nb - 1)] += 1
    z = np.zeros(nb)
    for i in range(nb):
        w = cnt[max(0, i - HALF):min(nb, i + HALF)]
        z[i] = (cnt[i] - np.median(w)) / (w.std() or 1.0)
    return cnt, z


def chat_top(chat, lo, hi, k=3):
    c = collections.Counter()
    for m in chat:
        if lo <= m["t"] < hi:
            tok = (m["msg"].split() or [""])[0]
            if tok:
                c[tok] += 1
    return [w for w, _ in c.most_common(k)]


def load_published(path, vod_id):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if str(r.get("vod_id", "")).strip() in (vod_id, "v" + vod_id) and r.get("start") and r.get("end"):
                out.append((float(r["start"]), float(r["end"])))
    return out


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_candidates(platform, duration, chat, heatmap, muted=(), published=(), vod_id=""):
    """Devuelve (lista de candidatos, avisos). platform: 'youtube' | 'twitch'."""
    avisos = []
    times = [m["t"] for m in chat]
    if platform == "youtube" and not heatmap:
        return [], [f"{vod_id}: YouTube sin heatmap: VOD descartado (sin señal no hay candidatos)"]
    if platform == "twitch" and not chat:
        return [], [f"{vod_id}: Twitch sin chat: no hay señal"]
    cnt, z = chat_zscores(times, duration) if chat else (None, None)

    # puntos candidatos: (peak, score, desempate, heatmap_norm|None, chat_z); en Twitch el score satura
    # en z≥4 y desempata el cubo con más mensajes
    pts = []
    if platform == "youtube":
        hmax = max(p["value"] for p in heatmap) or 1.0
        for p in heatmap:
            hn = p["value"] / hmax
            peak, cz = (p["start"] + p["end"]) / 2, 0.0
            if z is not None:
                b0 = int(p["start"] // BUCKET)
                b1 = max(b0 + 1, int(np.ceil(p["end"] / BUCKET)))
                seg = z[b0:min(b1, len(z))]
                if len(seg):
                    j = int(np.argmax(seg))
                    cz = max(float(seg[j]), 0.0)
                    peak = (b0 + j) * BUCKET + BUCKET / 2
            score = 0.6 * hn + 0.4 * min(cz / 4, 1.0) if chat else hn
            pts.append((peak, score, cz, hn, cz))
    else:
        for i, zz in enumerate(z):
            cz = max(float(zz), 0.0)
            pts.append((i * BUCKET + BUCKET / 2, min(cz / 4, 1.0), cnt[i], None, cz))

    pts.sort(key=lambda x: (-x[1], -x[2]))
    chosen = []
    for peak, score, _, hn, cz in pts:
        if len(chosen) >= MAX_CANDS:
            break
        if any(abs(peak - c["peak"]) < SEP for c in chosen):
            continue
        s, e = max(0.0, peak - PRE), min(duration, peak + POST)
        if platform == "twitch" and any(overlap(s, e, a, b) > 0 for a, b in muted):
            avisos.append(f"{vod_id}: ventana {s:.0f}-{e:.0f} toca un tramo silenciado: descartada")
            continue
        if any(overlap(s, e, a, b) > 0.5 * (e - s) for a, b in published):
            avisos.append(f"{vod_id}: ventana {s:.0f}-{e:.0f} ya publicada (>50 %): descartada")
            continue
        chosen.append({"start": round(s, 1), "end": round(e, 1), "peak": round(peak, 1),
                       "score": round(score, 4), "heatmap": None if hn is None else round(hn, 4),
                       "chat_z": round(cz, 2),
                       "chat_top": chat_top(chat, peak - 10, peak + 15) if chat else []})
    for n, c in enumerate(chosen, 1):
        c["n"] = n
    chosen = [{k: c[k] for k in ("n", "start", "end", "peak", "score", "heatmap", "chat_z", "chat_top")}
              for c in chosen]
    if len(chosen) < 10:
        avisos.append(f"{vod_id}: solo {len(chosen)} ventanas (<10)")
    return chosen, avisos


def candidates(vod_id, publicados=None):
    vod_id = vod_id[1:] if vod_id[:1] == "v" and vod_id[1:].isdigit() else vod_id
    d = rutas.vods() / vod_id
    if not (d / "info.json").exists():
        raise SystemExit(f"{vod_id}: no está ingerido (clipero ingest <url>)")
    info = json.loads((d / "info.json").read_text(encoding="utf-8"))
    platform = "twitch" if "twitch" in (info.get("extractor_key") or info.get("extractor") or "").lower() else "youtube"
    heatmap = json.loads((d / "heatmap.json").read_text()) if (d / "heatmap.json").exists() else []
    chat = []
    if (d / "chat.jsonl").exists():
        chat = [json.loads(l) for l in open(d / "chat.jsonl", encoding="utf-8") if l.strip()]
    muted = json.loads((d / "muted.json").read_text()) if (d / "muted.json").exists() else []
    pub = load_published(publicados or rutas.home() / "publicados.csv", vod_id)
    cands, avisos = build_candidates(platform, float(info["duration"]), chat, heatmap, muted, pub, vod_id)
    for a in avisos:
        warn(a)
    (d / "candidatos.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    if not cands:
        print(f"{vod_id}: DESCARTADO, 0 candidatos")
    for c in cands:
        m, s = divmod(int(c["peak"]), 60)
        print(f"#{c['n']:>2} pico {m // 60}:{m % 60:02d}:{s:02d} ({c['peak']:.0f}s) score={c['score']:.3f} "
              f"heatmap={c['heatmap']} chat_z={c['chat_z']} ventana={c['start']:.0f}-{c['end']:.0f} {c['chat_top']}")
    return cands
