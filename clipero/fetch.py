"""fetch: baja un tramo de un VOD (audio o vídeo) sin bajar el VOD entero.

API estable (la reutiliza el M3 para vídeo):
    fetch_section(vod_id, plataforma, start, end, out, audio_only=True) -> (ruta, offset_real)
`offset_real` = segundo del VOD donde empieza de verdad el fichero devuelto.
- Twitch: solo el init y los segmentos HLS que cubren [start, end] (`--download-sections` deja
  ficheros de 258 B). El offset es el inicio del primer segmento (múltiplo de 10 s).
- YouTube: `yt-dlp --download-sections "*s-e"`; el offset es `end − duración real` (ffprobe).
"""
import re
import sys
import subprocess
import urllib.request
from pathlib import Path

from . import herramientas

YT = "https://www.youtube.com/watch?v={}"
TW = "https://www.twitch.tv/videos/{}"


def ytdlp_bin():
    """Comando base de yt-dlp (lista) con deno como runtime de JS."""
    return herramientas.ytdlp()


# --- HLS (puro, testeable) ------------------------------------------------------

def parse_hls(text):
    """Playlist HLS → (init_uri|None, [(uri, inicio_s, dur_s)]) con inicio acumulado desde 0."""
    init = None
    m = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
    if m:
        init = m.group(1)
    segs, t, dur = [], 0.0, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            dur = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            d = dur if dur is not None else 10.0
            segs.append((line, t, d))
            t += d
            dur = None
    return init, segs


def select_segments(segs, start, end):
    """Segmentos que cubren [start, end] → (lista, offset_real = inicio del primero)."""
    sel = [s for s in segs if s[1] + s[2] > start and s[1] < end]
    if not sel:
        raise RuntimeError(f"ningún segmento HLS cubre {start}-{end}")
    return sel, sel[0][1]


def to_vod_time(t_file, offset):
    """Segundos del fichero → segundos del VOD."""
    return round(offset + t_file, 2)


# --- Twitch ---------------------------------------------------------------------

def _http(url):
    return urllib.request.urlopen(url, timeout=60).read()


def _twitch_playlist_url(vod_id, audio_only, fmt):
    sel = fmt or ("Audio_Only" if audio_only else "worst[vcodec!=none]")
    r = subprocess.run([*ytdlp_bin(), "--no-update", "-g", "-f", sel, TW.format(vod_id)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"yt-dlp -g -f {sel} falló: {r.stderr.strip()[-300:]}")
    return r.stdout.strip().splitlines()[0]


def _fetch_twitch(vod_id, start, end, out, audio_only, fmt):
    u = _twitch_playlist_url(vod_id, audio_only, fmt)
    base = u.rsplit("/", 1)[0]
    init, segs = parse_hls(_http(u).decode())
    sel, offset = select_segments(segs, start, end)
    raw = Path(out).with_suffix(".raw")
    with open(raw, "wb") as f:
        if init:
            f.write(_http(f"{base}/{init}"))
        for uri, _, _ in sel:
            if "muted" in uri:
                print(f"AVISO: segmento silenciado {uri}", file=sys.stderr)
            f.write(_http(f"{base}/{uri}"))
    if audio_only:
        r = subprocess.run([herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-f", "mp4", "-i", str(raw), "-vn",
                            "-c:a", "copy", str(out)], capture_output=True, text=True)
        if r.returncode != 0:  # contenedor .ts u otro: reencodar
            r = subprocess.run([herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vn", "-c:a", "aac",
                                "-b:a", "96k", str(out)], capture_output=True, text=True)
        raw.unlink()
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {r.stderr.strip()[-300:]}")
    else:
        raw.replace(out)
    return Path(out), offset


# --- YouTube --------------------------------------------------------------------

def probe_start(path):
    """start_time del primer stream según ffprobe (s)."""
    r = subprocess.run([herramientas.ruta("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "stream=start_time",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    vals = [float(x) for x in r.stdout.split() if re.fullmatch(r"-?[\d.]+", x)]
    return min(vals) if vals else 0.0


def probe_duration(path):
    """Duración del contenedor según ffprobe (s)."""
    r = subprocess.run([herramientas.ruta("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.split()[0])
    except (IndexError, ValueError):
        raise RuntimeError(f"ffprobe no dio duración para {path}: {r.stderr.strip()[-200:]}")


def youtube_offset(start, end, duration):
    """Segundo del VOD donde empieza el fichero = end pedido − duración real (puro)."""
    if duration > end - start + 15 or duration < end - start - 1:
        print(f"AVISO: duración {duration:.2f}s fuera de lo esperado para {start}-{end}; "
              "el corte no ha ido como se esperaba", file=sys.stderr)
    return round(max(end - duration, 0.0), 3)


def _fetch_youtube(vod_id, start, end, out, audio_only, fmt):
    out = Path(out)
    sel = fmt or ("ba" if audio_only else "bv*[height<=1080]+ba/b")
    tmpl = str(out.with_suffix("")) + ".yt.%(ext)s"
    r = subprocess.run([*ytdlp_bin(), "--no-update", "--no-playlist", "--download-sections",
                        f"*{start}-{end}", "-f", sel, "-o", tmpl, YT.format(vod_id)],
                       capture_output=True, text=True)
    got = sorted(out.parent.glob(out.stem + ".yt.*"))
    if r.returncode != 0 or not got:
        raise RuntimeError(f"yt-dlp --download-sections falló: {r.stderr.strip()[-300:]}")
    src = got[0]
    if audio_only:
        # ffmpeg corta en copy en el paquete/keyframe anterior; lo reencodamos a m4a conservando tiempos
        r = subprocess.run([herramientas.ruta("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-c:a", "aac",
                            "-b:a", "96k", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {r.stderr.strip()[-300:]}")
    else:
        src.replace(out)
        src = None
    # offset: el fichero termina en `end` (-t de yt-dlp) y el muxer reescala los timestamps a >= 0,
    # así que probe_start no sirve; se ancla por el final: end − duración real.
    dur = probe_duration(out)
    offset = youtube_offset(start, end, dur)
    if src:
        src.unlink()
    return out, offset


def fetch_section(vod_id, plataforma, start, end, out, audio_only=True, fmt=None):
    """Baja [start, end] (s del VOD) a `out`. Devuelve (ruta, offset_real)."""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if plataforma == "twitch":
        return _fetch_twitch(vod_id, start, end, out, audio_only, fmt)
    if plataforma == "youtube":
        return _fetch_youtube(vod_id, start, end, out, audio_only, fmt)
    raise ValueError(f"plataforma desconocida: {plataforma}")
