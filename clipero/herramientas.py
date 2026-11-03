"""herramientas: dónde están (y cómo se bajan) los binarios externos.

`ruta(nombre)` busca en `<home>/.clipero/bin/` y luego en el PATH. `setup()` baja a `<home>/.clipero/bin/` lo
que falte para el SO y la arquitectura actuales (versión y sha256 fijados aquí) y precarga Whisper `small`;
`doctor()` imprime qué hay y devuelve 1 si falta algo obligatorio. yt-dlp es dependencia pip: se lanza como
módulo con el intérprete actual (`ytdlp()`), y deno es su runtime de JS para YouTube.
"""
import hashlib
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import rutas

TDL_VERSION = "1.56.5"
DENO_VERSION = "2.9.8"
# BtbN conserva las builds diarias ~2 semanas, pero las de fin de mes ~2 años: fija siempre una de fin de mes,
# y de una rama estable (nX.Y), no de master.
BTBN_TAG = "autobuild-2026-10-31-12-59"
BTBN_BUILD = "n8.1.3-27-g8dca1586f4"
BTBN_RAMA = "8.1"
WHISPER_MODELO = "small"

OBLIGATORIAS = ("ffmpeg", "ffprobe", "deno", "TwitchDownloaderCLI")


@dataclass(frozen=True)
class Paquete:
    url: str
    sha256: str
    miembros: tuple[str, ...] | None = None   # nombres base a extraer a bin/ ; None = todo el archivo, plano


def _btbn(sufijo: str, ext: str, sha: str) -> Paquete:
    base = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{BTBN_TAG}"
    return Paquete(f"{base}/ffmpeg-{BTBN_BUILD}-{sufijo}-gpl-{BTBN_RAMA}.{ext}", sha, ("ffmpeg", "ffprobe"))


def _deno(destino: str, sha: str) -> Paquete:
    return Paquete(f"https://github.com/denoland/deno/releases/download/v{DENO_VERSION}/deno-{destino}.zip",
                   sha, ("deno",))


def _tdl(sufijo: str, sha: str) -> Paquete:
    return Paquete("https://github.com/lay295/TwitchDownloader/releases/download/"
                   f"{TDL_VERSION}/TwitchDownloaderCLI-{TDL_VERSION}-{sufijo}.zip", sha)


# arquitectura → paquetes. Solo Linux (x64 y arm64).
FFMPEG: dict[str, tuple[Paquete, ...]] = {
    "x64": (_btbn("linux64", "tar.xz", "41e9c565594c390622cf968d82fa4135d9e9a11d06c1515644288cbc844e3380"),),
    "arm64": (_btbn("linuxarm64", "tar.xz", "a08c0ee6e1c4e02139344b303002dcc7c37cf125d639f1fbd15dabee40fcb525"),),
}
DENO: dict[str, Paquete] = {
    "x64": _deno("x86_64-unknown-linux-gnu", "e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609"),
    "arm64": _deno("aarch64-unknown-linux-gnu", "d49596c20b9788cf8f5d8ddf644103d4bde56ed239753f0bdb92ba9361d51905"),
}
TDL: dict[str, Paquete] = {
    "x64": _tdl("Linux-x64", "f2bcee00d0e6da759d97c23767345634cb9cdb10cdff96cfa96f97983d51bf55"),
    "arm64": _tdl("LinuxArm64", "2fde836f07c3ebfcf61cace23742a2c43543fc30fda96071eb96ab8e10c24f7f"),
}
# herramienta (clave de ruta) → su tabla. ffmpeg y ffprobe viajan juntos.
TABLAS = {"ffmpeg": FFMPEG, "deno": DENO, "TwitchDownloaderCLI": TDL}


# --- resolución ------------------------------------------------------------------

def ruta(nombre: str) -> str | None:
    """`<home>/.clipero/bin/<nombre>` → `shutil.which(nombre)` → None."""
    local = rutas.binario(nombre)
    if local.is_file():
        return str(local)
    return shutil.which(nombre)


def ytdlp() -> list[str]:
    """Comando base de yt-dlp (lista): el módulo del intérprete actual, con deno como runtime de JS si lo hay."""
    cmd = [sys.executable, "-m", "yt_dlp"]
    deno = ruta("deno")
    if deno:
        cmd += ["--js-runtimes", f"deno:{deno}"]
    return cmd


def modelos_whisper() -> Path:
    """`CLIPERO_WHISPER_DIR` (la imagen Docker lleva el modelo fuera de /datos) o `<home>/.clipero/modelos/whisper`."""
    if os.environ.get("CLIPERO_WHISPER_DIR"):
        return Path(os.environ["CLIPERO_WHISPER_DIR"])
    return rutas.home() / ".clipero" / "modelos" / "whisper"


def objetivo() -> str:
    """Arquitectura ('x64' | 'arm64') si es Linux; si no, error claro."""
    arq = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if platform.system() != "Linux" or arq is None:
        raise RuntimeError("Clipero solo es compatible con Linux x64/arm64 "
                           f"(esto es {platform.system()} {platform.machine()})")
    return arq


def paquetes(herramienta: str, arq: str | None = None) -> tuple[Paquete, ...]:
    """Paquetes que instalan `herramienta` ('ffmpeg' | 'deno' | 'TwitchDownloaderCLI') en esa arquitectura."""
    p = TABLAS[herramienta][arq or objetivo()]
    return p if isinstance(p, tuple) else (p,)


# --- descarga --------------------------------------------------------------------

def _descargar(url: str, destino: Path, sha256: str) -> None:
    """url → `<destino>.part`, comprueba el sha256 y renombra. Si no cuadra, borra el .part y falla."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    part = destino.with_name(destino.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "clipero"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while True:
                trozo = r.read(1 << 20)
                if not trozo:
                    break
                h.update(trozo)
                f.write(trozo)
        if h.hexdigest() != sha256.lower():
            raise RuntimeError(f"sha256 incorrecto en {url}: esperado {sha256}, recibido {h.hexdigest()}")
        os.replace(part, destino)
    finally:
        part.unlink(missing_ok=True)


def _escribir(src, destino: Path) -> None:
    part = destino.with_name(destino.name + ".part")
    with open(part, "wb") as f:
        shutil.copyfileobj(src, f)
    part.chmod(part.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(part, destino)


def _pedido(nombre: str, quiero: set[str] | None) -> bool:
    """¿Se extrae este miembro? Con lista, solo por nombre base y en `bin/` o en la raíz del archivo."""
    ruta_ = Path(nombre)
    if quiero is None:
        return bool(ruta_.name)
    return ruta_.name in quiero and ruta_.parent.name in ("", "bin")


def _extraer(archivo: Path, miembros: tuple[str, ...] | None, bin_dir: Path) -> list[str]:
    """Saca del zip/tar los ficheros pedidos (por nombre base) a bin_dir, planos. → nombres escritos."""
    quiero = None if miembros is None else set(miembros)
    hechos: list[str] = []
    if zipfile.is_zipfile(archivo):
        with zipfile.ZipFile(archivo) as z:
            for info in z.infolist():
                base = Path(info.filename).name
                if info.is_dir() or not _pedido(info.filename, quiero):
                    continue
                with z.open(info) as src:
                    _escribir(src, bin_dir / base)
                hechos.append(base)
    else:
        with tarfile.open(archivo) as t:
            for info in t:
                base = Path(info.name).name
                if not info.isfile() or not _pedido(info.name, quiero):
                    continue
                _escribir(t.extractfile(info), bin_dir / base)
                hechos.append(base)
    if quiero is not None and set(hechos) != quiero:
        raise RuntimeError(f"{archivo.name} no trae {sorted(quiero - set(hechos))}")
    return hechos


def instalar(herramienta: str, bin_dir: Path | None = None) -> list[str]:
    """Baja e instala una herramienta de la tabla en bin_dir (por defecto `<home>/.clipero/bin`)."""
    bin_dir = bin_dir or rutas.binario("x").parent
    bin_dir.mkdir(parents=True, exist_ok=True)
    hechos: list[str] = []
    for p in paquetes(herramienta):
        tmp = bin_dir / ("descarga-" + Path(p.url).name)
        try:
            _descargar(p.url, tmp, p.sha256)
            hechos += _extraer(tmp, p.miembros, bin_dir)
        finally:
            tmp.unlink(missing_ok=True)
    return hechos


def whisper_listo() -> bool:
    try:
        from faster_whisper.utils import download_model
        download_model(WHISPER_MODELO, local_files_only=True, cache_dir=str(modelos_whisper()))
        return True
    except Exception:  # noqa: BLE001 — cualquier fallo = no está
        return False


def setup(forzar: bool = False, salida=print) -> None:
    """Baja a `<home>/.clipero/bin/` lo que falte (todo con `forzar`) y precarga Whisper `small`."""
    arq = objetivo()
    salida(f"plataforma: linux {arq} · carpeta: {rutas.home()}")
    for herramienta, comprobar in (("ffmpeg", ("ffmpeg", "ffprobe")), ("deno", ("deno",)),
                                   ("TwitchDownloaderCLI", ("TwitchDownloaderCLI",))):
        if not forzar and all(ruta(n) for n in comprobar):
            salida(f"✓ {herramienta}: ya está ({ruta(comprobar[0])})")
            continue
        salida(f"↓ {herramienta}: descargando…")
        instalar(herramienta)
        salida(f"✓ {herramienta}: instalado en {rutas.binario('x').parent}")
    if not forzar and whisper_listo():
        salida(f"✓ whisper {WHISPER_MODELO}: ya está")
    else:
        salida(f"↓ whisper {WHISPER_MODELO}: descargando (~480 MB)…")
        from faster_whisper.utils import download_model
        modelos_whisper().mkdir(parents=True, exist_ok=True)
        download_model(WHISPER_MODELO, cache_dir=str(modelos_whisper()))
        salida(f"✓ whisper {WHISPER_MODELO}: listo")


# --- doctor ----------------------------------------------------------------------

def _version(cmd: list[str], patron: str) -> tuple[str, str]:
    """Ejecuta el binario (con timeout) → (versión, ""), o ("", motivo) si no arranca o no da versión."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except Exception as e:  # noqa: BLE001 — no existe, sin permiso, timeout…
        return "", f"no arranca: {type(e).__name__}"
    salida = (r.stdout or "") + (r.stderr or "")
    roto = re.search(r"error while loading|GLIBC\w*_[\d.]+'? not found|valid ICU package|cannot execute", salida, re.I)
    m = None if roto else re.search(patron, salida)
    if m:   # basta con que imprima la versión (TwitchDownloaderCLI --version puede salir con rc 1), salvo que el cargador falle
        return m.group(1), ""
    lineas = [ln.strip() for ln in salida.splitlines() if ln.strip()]
    primera = next((ln for ln in lineas if re.search(r"ICU|libicu|error|not found|cannot|No such", ln, re.I)),
                   lineas[0] if lineas else "sin salida")
    return "", f"no arranca (rc {r.returncode}): {primera[:70]}"


def _modo_claude() -> str:
    try:
        from . import config   # misma lectura que la app; necesita ruamel (extra `app`)
        return config.modo_claude(rutas.home())
    except ImportError:
        pass
    f = rutas.home() / "app.yaml"
    try:
        import yaml
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        return str((d.get("claude") or {}).get("modo") or "ninguno")
    except Exception:  # noqa: BLE001
        return "ninguno"


def estado() -> list[tuple[str, str, str, bool, bool]]:
    """[(herramienta, ruta, versión, ok, obligatoria)] de todo lo que Clipero usa."""
    filas = []
    for n, patron in (("ffmpeg", r"version (\S+)"), ("ffprobe", r"version (\S+)"),
                      ("deno", r"deno (\S+)"), ("TwitchDownloaderCLI", r"(\d+\.\d+\.\d+\S*)")):
        r = ruta(n)
        v, motivo = _version([r, "-version" if n.startswith("ff") else "--version"], patron) if r else ("", "no está")
        filas.append((n, r or "", v or motivo, bool(v), True))
    try:
        import yt_dlp.version as yv
        filas.append(("yt-dlp", f"{sys.executable} -m yt_dlp", yv.__version__, True, True))
    except ImportError:
        filas.append(("yt-dlp", "", "", False, True))
    w = whisper_listo()
    filas.append((f"whisper {WHISPER_MODELO}", str(modelos_whisper()) if w else "", WHISPER_MODELO if w else "", w, True))
    y = rutas.modelo_yunet()
    filas.append(("YuNet", str(y) if y.is_file() else "", "2023mar" if y.is_file() else "", y.is_file(), True))
    c = shutil.which("claude")
    v, motivo = _version([c, "--version"], r"(\d+\.\d+\.\d+\S*)") if c else ("", "")
    filas.append(("claude", c or "", v or motivo, bool(v), False))
    return filas


def doctor(salida=print) -> int:
    """Tabla herramienta · ruta · versión · ✓/✗ y el modo de Claude. 1 si falta algo obligatorio."""
    filas = estado()
    salida(f"{'herramienta':<22} {'ruta':<60} versión  ok")
    for n, r, v, ok, obl in filas:
        marca = "✓" if ok else ("✗" if obl else "–")   # – = opcional y ausente
        salida(f"{n:<22} {r or '-':<60} {v or '-'}  {marca}")
    salida(f"modo de Claude: {_modo_claude()}")
    faltan = [n for n, _, _, ok, obl in filas if obl and not ok]
    if faltan:
        salida("faltan: " + ", ".join(faltan) + " → ejecuta `clipero setup`")
        return 1
    return 0
