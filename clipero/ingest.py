"""ingest: yt-dlp -j, heatmap, chat de YouTube/Twitch y segmentos -muted de Twitch.

Nunca descarga vídeo: solo metadatos, subtítulo live_chat, chat de Twitch y la playlist HLS.
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import herramientas, rutas



def tdl():
    r = herramientas.ruta("TwitchDownloaderCLI")
    if not r:
        raise RuntimeError("falta TwitchDownloaderCLI: ejecuta `clipero setup`")
    return r


MUTED_RE = re.compile(r"-muted\.(ts|mp4|m4s)")


def warn(msg):
    print(f"AVISO: {msg}", file=sys.stderr)


def ytdlp_bin():
    """Comando base de yt-dlp (lista) con deno como runtime de JS. Nombre histórico."""
    return herramientas.ytdlp()


def is_twitch(url):
    return "twitch.tv" in url


def vod_id_from_info(info):
    vid = str(info["id"])
    if re.fullmatch(r"v\d+", vid):  # Twitch: id numérico sin la «v»
        vid = vid[1:]
    return vid


def fetch_info(url):
    out = subprocess.run([*ytdlp_bin(), "-j", "--no-playlist", "--skip-download", url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"yt-dlp -j falló: {out.stderr.strip()[-400:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def heatmap_from_info(info):
    return [{"start": p["start_time"], "end": p["end_time"], "value": p["value"]}
            for p in (info.get("heatmap") or [])]


# --- chat de YouTube ---------------------------------------------------------

def _runs_text(msg):
    if not msg:
        return ""
    if "simpleText" in msg:
        return msg["simpleText"]
    return "".join(r.get("text") or r.get("emoji", {}).get("shortcuts", [""])[0]
                   for r in msg.get("runs", []))


def parse_youtube_livechat(path):
    """live_chat.json de yt-dlp: una acción por línea. Devuelve [{t,user,msg}]."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rep = obj.get("replayChatItemAction")
            if not rep:
                continue
            t = int(rep.get("videoOffsetTimeMsec", 0)) / 1000.0
            for act in rep.get("actions", []):
                item = act.get("addChatItemAction", {}).get("item", {})
                r = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if not r:
                    continue
                rows.append({"t": t, "user": _runs_text(r.get("authorName")),
                             "msg": _runs_text(r.get("message"))})
    return rows


def download_youtube_chat(url, tmp):
    subprocess.run([*ytdlp_bin(), "--skip-download", "--write-subs", "--sub-langs", "live_chat",
                    "--no-playlist", "-o", str(Path(tmp) / "chat.%(ext)s"), url],
                   capture_output=True, text=True)
    found = list(Path(tmp).glob("chat*.live_chat.json"))
    return parse_youtube_livechat(found[0]) if found else None


# --- chat de Twitch ----------------------------------------------------------

def normalize_twitch_chat(path):
    """JSON de TwitchDownloaderCLI → [{t,user,msg}]."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [{"t": c["content_offset_seconds"],
             "user": (c.get("commenter") or {}).get("name", ""),
             "msg": c["message"]["body"]} for c in data.get("comments", [])]


def download_twitch_chat(vid, tmp):
    exe = tdl()
    out = Path(tmp) / "chat.json"
    r = subprocess.run([exe, "chatdownload", "--id", vid, "-o", str(out),
                        "--collision", "Overwrite", "--banner", "false"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"TwitchDownloaderCLI falló: {(r.stderr or r.stdout).strip()[-400:]}")
    return normalize_twitch_chat(out)


# --- segmentos silenciados de Twitch ------------------------------------------

def parse_muted_ranges(playlist_text):
    """Playlist HLS → rangos [start,end] (s del VOD) de los segmentos «-muted», fusionando contiguos."""
    ranges, t, dur = [], 0.0, None
    for line in playlist_text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            dur = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            d = dur if dur is not None else 10.0
            if MUTED_RE.search(line):
                if ranges and abs(ranges[-1][1] - t) < 1e-6:
                    ranges[-1][1] = t + d
                else:
                    ranges.append([t, t + d])
            t += d
            dur = None
    return [[round(a, 3), round(b, 3)] for a, b in ranges]


def fetch_muted(info):
    for fmt in info.get("formats", []):
        u = fmt.get("url", "")
        if ".m3u8" in u and fmt.get("vcodec") != "none":
            text = urllib.request.urlopen(u, timeout=60).read().decode()
            return parse_muted_ranges(text)
    raise RuntimeError("no hay playlist HLS en los formatos del VOD")


# --- orquestación ---------------------------------------------------------------

def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ingest(url, force=False):
    info = fetch_info(url)
    vid = vod_id_from_info(info)
    d = rutas.vods() / vid
    d.mkdir(parents=True, exist_ok=True)
    (d / "info.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    hm = heatmap_from_info(info)
    (d / "heatmap.json").write_text(json.dumps(hm), encoding="utf-8")
    twitch = is_twitch(url)
    chat_path = d / "chat.jsonl"
    if chat_path.exists() and chat_path.stat().st_size > 0 and not force:
        print(f"chat.jsonl ya existe ({chat_path.stat().st_size} B), no se vuelve a bajar (--force)")
    else:
        with tempfile.TemporaryDirectory(dir=d) as tmp:
            if twitch:
                rows = download_twitch_chat(vid, tmp)
            else:
                rows = download_youtube_chat(url, tmp)
        if rows is None:
            warn(f"{vid}: el directo de YouTube no tiene live_chat; chat.jsonl queda vacío")
            rows = []
        elif not rows and not twitch:
            warn(f"{vid}: live_chat sin mensajes; chat.jsonl queda vacío")
        write_jsonl(chat_path, rows)
    if twitch:
        muted = fetch_muted(info)
        (d / "muted.json").write_text(json.dumps(muted), encoding="utf-8")
        print(f"muted: {len(muted)} rango(s) {muted}")
    elif not hm:
        warn(f"{vid}: YouTube sin heatmap; `candidates` lo descartará")
    n = sum(1 for _ in open(chat_path, encoding="utf-8"))
    print(f"ingest OK: {vid} → {d} (heatmap {len(hm)} puntos, chat {n} mensajes)")
    return vid
