"""transcribe: audio de cada ventana → win/<n>.m4a → faster-whisper → win/<n>.words.json + candidatos.md.

Nunca transcribe el VOD entero. El modelo se carga una vez para todas las ventanas.
"""
import collections
import json
import sys
import time

from . import herramientas, rutas
from .fetch import fetch_section, to_vod_time

MODEL = "small"


def mmss(t):
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"


def platform_of(info):
    return "twitch" if str(info.get("extractor", "")).startswith("twitch") else "youtube"


def words_to_vod(words, offset):
    """[(w, s, e)] en segundos del fichero → [{w,s,e}] en segundos del VOD (con el offset real)."""
    return [{"w": w.strip(), "s": to_vod_time(s, offset), "e": to_vod_time(e, offset)}
            for w, s, e in words if w.strip()]


def top_chat(chat, lo, hi, k=8):
    """Mensajes completos más repetidos en [lo, hi) → [(msg, n)], normalizados por minúsculas."""
    c, shown = collections.Counter(), {}
    for m in chat:
        if lo <= m["t"] < hi:
            msg = " ".join(m["msg"].split())
            if msg:
                c[msg.lower()] += 1
                shown.setdefault(msg.lower(), msg)
    return [(shown[k_], n) for k_, n in c.most_common(k)]


def paragraphs(words, start, end, step=10):
    """Palabras del VOD → [(marca_s, texto)] una por cada tramo de `step` s con voz."""
    out, cur, base = [], [], None
    for w in sorted(words, key=lambda x: x["s"]):
        slot = int((w["s"] - start) // step)
        if base is None or slot != base:
            if cur:
                out.append((start + base * step, " ".join(cur)))
            cur, base = [], slot
        cur.append(w["w"])
    if cur:
        out.append((start + base * step, " ".join(cur)))
    return out


def render_md(vod_id, title, cands, words_by_n, chat, nchat_top=8):
    L = [f"# Candidatos — {title} (`{vod_id}`)", "",
         "Tiempos `[mm:ss]` = minuto del VOD. Una marca cada 10 s de ventana.", ""]
    for c in cands:
        hm = "—" if c.get("heatmap") is None else f"{c['heatmap']:.2f}"
        L += [f"## #{c['n']} · {mmss(c['start'])}–{mmss(c['end'])} · score {c['score']:.2f} "
              f"· heatmap {hm} · chat_z {c['chat_z']:.1f} · pico {mmss(c['peak'])}", ""]
        tc = top_chat(chat, c["start"], c["end"], nchat_top)
        L.append("**Chat más repetido:** " + (" · ".join(f"{m} (×{n})" for m, n in tc) if tc else "—"))
        L.append("")
        ws = words_by_n.get(c["n"])
        if ws is None:
            L.append("_sin transcribir_")
        elif not ws:
            L.append("_sin voz detectada_")
        else:
            for t, txt in paragraphs(ws, c["start"], c["end"]):
                L.append(f"[{mmss(t)}] {txt}")
                L.append("")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def load_chat(d):
    p = d / "chat.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def transcribe(vod_id, ns=None, force=False):
    d = rutas.vods() / vod_id
    cands = json.loads((d / "candidatos.json").read_text(encoding="utf-8"))
    info = json.loads((d / "info.json").read_text(encoding="utf-8"))
    plat = platform_of(info)
    sel = [c for c in cands if not ns or c["n"] in ns]
    if ns and len(sel) != len(set(ns)):
        raise RuntimeError(f"ventanas inexistentes en candidatos.json: {sorted(set(ns) - {c['n'] for c in sel})}")
    win = d / "win"
    win.mkdir(exist_ok=True)
    t_dl = t_load = t_wh = audio_s = 0.0
    model = None
    for c in sel:
        wj = win / f"{c['n']}.words.json"
        if wj.exists() and not force:
            print(f"#{c['n']}: words.json ya existe, se salta (--force)")
            continue
        m4a = win / f"{c['n']}.m4a"
        t0 = time.time()
        path, offset = fetch_section(vod_id, plat, c["start"], c["end"], m4a, audio_only=True)
        dl = time.time() - t0
        t_dl += dl
        if model is None:
            from faster_whisper import WhisperModel
            t0 = time.time()
            model = WhisperModel(MODEL, device="cpu", compute_type="int8",
                                 download_root=str(herramientas.modelos_whisper()))
            t_load = time.time() - t0
        t0 = time.time()
        segs, ainfo = model.transcribe(str(path), language="es", word_timestamps=True, vad_filter=True)
        raw = [(w.word, w.start, w.end) for s in segs for w in (s.words or [])]
        wh = time.time() - t0
        t_wh += wh
        audio_s += ainfo.duration
        words = words_to_vod(raw, offset)
        wj.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        print(f"#{c['n']}: offset {offset}s, audio {ainfo.duration:.1f}s, {len(words)} palabras "
              f"(descarga {dl:.1f}s, whisper {wh:.1f}s)", flush=True)
    words_by_n = {}
    for c in cands:
        wj = win / f"{c['n']}.words.json"
        if wj.exists():
            words_by_n[c["n"]] = json.loads(wj.read_text(encoding="utf-8"))
    (d / "candidatos.md").write_text(
        render_md(vod_id, info.get("title", vod_id), cands, words_by_n, load_chat(d)), encoding="utf-8")
    if audio_s:
        print(f"TIEMPOS: descarga {t_dl:.1f}s · carga modelo {t_load:.1f}s · whisper {t_wh:.1f}s "
              f"para {audio_s:.0f}s de audio = {t_wh / audio_s * 60:.1f} s/min")
    print(f"candidatos.md → {d / 'candidatos.md'}")
