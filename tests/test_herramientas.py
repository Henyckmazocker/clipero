"""herramientas: resolución bin → PATH, tabla por (system, machine), descarga con sha256 y doctor. Sin red."""
import hashlib
import io
import subprocess
import tarfile
import zipfile

import pytest

from clipero import herramientas, rutas
from clipero.herramientas import Paquete


def zip_bytes(ficheros):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, c in ficheros.items():
            z.writestr(n, c)
    return b.getvalue()


def tar_bytes(ficheros):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:xz") as t:
        for n, c in ficheros.items():
            i = tarfile.TarInfo(n)
            i.size = len(c)
            t.addfile(i, io.BytesIO(c))
    return b.getvalue()


@pytest.fixture
def red(monkeypatch):
    """urlopen falso: {url: bytes}. Devuelve la lista de urls pedidas."""
    class Red(dict):
        pedidas: list

    contenido = Red()
    contenido.pedidas = pedidas = []

    def urlopen(req, timeout=None):
        pedidas.append(req.full_url)
        return io.BytesIO(contenido[req.full_url])
    monkeypatch.setattr(herramientas.urllib.request, "urlopen", urlopen)
    return contenido


@pytest.fixture
def bin_dir(home_tmp, monkeypatch):
    monkeypatch.setattr(herramientas.shutil, "which", lambda n: None)
    return rutas.binario("x").parent


# --- resolución ---------------------------------------------------------------------

def test_ruta_prefiere_bin_y_luego_path(home_tmp, monkeypatch):
    monkeypatch.setattr(herramientas.shutil, "which", lambda n: f"/usr/bin/{n}")
    assert herramientas.ruta("deno") == "/usr/bin/deno"
    b = rutas.binario("deno")
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text("x")
    assert herramientas.ruta("deno") == str(b)


def test_ruta_none_si_no_esta(home_tmp, monkeypatch):
    monkeypatch.setattr(herramientas.shutil, "which", lambda n: None)
    assert herramientas.ruta("deno") is None


def test_ytdlp_con_y_sin_deno(home_tmp, monkeypatch):
    monkeypatch.setattr(herramientas.shutil, "which", lambda n: None)
    assert herramientas.ytdlp() == [herramientas.sys.executable, "-m", "yt_dlp"]
    monkeypatch.setattr(herramientas.shutil, "which", lambda n: "/x/deno")
    assert herramientas.ytdlp()[-2:] == ["--js-runtimes", "deno:/x/deno"]


# --- plataforma ---------------------------------------------------------------------

@pytest.mark.parametrize("machine,esperado", [("x86_64", "x64"), ("amd64", "x64"), ("aarch64", "arm64"), ("arm64", "arm64")])
def test_objetivo_linux(monkeypatch, machine, esperado):
    monkeypatch.setattr(herramientas.platform, "system", lambda: "Linux")
    monkeypatch.setattr(herramientas.platform, "machine", lambda: machine)
    assert herramientas.objetivo() == esperado


@pytest.mark.parametrize("system,machine", [("Darwin", "arm64"), ("Windows", "AMD64"), ("FreeBSD", "x86_64"),
                                            ("Linux", "riscv64")])
def test_sistema_no_compatible_falla_claro(monkeypatch, system, machine):
    monkeypatch.setattr(herramientas.platform, "system", lambda: system)
    monkeypatch.setattr(herramientas.platform, "machine", lambda: machine)
    with pytest.raises(RuntimeError, match="Clipero solo es compatible con Linux x64/arm64"):
        herramientas.objetivo()


@pytest.mark.parametrize("arq", ["x64", "arm64"])
def test_tabla_completa_para_cada_arquitectura(arq):
    for h in herramientas.TABLAS:
        ps = herramientas.paquetes(h, arq)
        assert ps
        for p in ps:
            assert p.url.startswith("https://") and "linux" in p.url.lower() and len(p.sha256) == 64 and int(p.sha256, 16) >= 0
    assert {m for p in herramientas.paquetes("ffmpeg", arq) for m in p.miembros} == {"ffmpeg", "ffprobe"}
    assert herramientas.TDL_VERSION in herramientas.TDL[arq].url


# --- descarga -----------------------------------------------------------------------

def test_instalar_sha_bueno_zip_y_tar(bin_dir, red):
    z = zip_bytes({"deno": b"#!deno"})
    t = tar_bytes({"ffmpeg-N/bin/ffmpeg": b"F", "ffmpeg-N/bin/ffprobe": b"P", "ffmpeg-N/bin/ffplay": b"X",
                   "ffmpeg-N/doc/ffmpeg": b"no"})
    red["https://x/deno.zip"], red["https://x/ff.tar.xz"] = z, t
    pz = Paquete("https://x/deno.zip", hashlib.sha256(z).hexdigest(), ("deno",))
    pt = Paquete("https://x/ff.tar.xz", hashlib.sha256(t).hexdigest(), ("ffmpeg", "ffprobe"))
    herramientas.DENO["x64"] = pz
    herramientas.FFMPEG["x64"] = (pt,)
    assert herramientas.instalar("deno", bin_dir) == ["deno"]
    assert herramientas.instalar("ffmpeg", bin_dir) == ["ffmpeg", "ffprobe"]
    assert (bin_dir / "ffmpeg").read_bytes() == b"F" and (bin_dir / "ffprobe").read_bytes() == b"P"
    assert not (bin_dir / "ffplay").exists()
    assert (bin_dir / "deno").stat().st_mode & 0o111           # chmod +x
    assert [p.name for p in bin_dir.iterdir() if p.suffix == ".part" or p.name.startswith("descarga-")] == []


@pytest.fixture(autouse=True)
def _tablas_intactas(monkeypatch):
    monkeypatch.setattr(herramientas.platform, "system", lambda: "Linux")
    monkeypatch.setattr(herramientas.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(herramientas, "DENO", dict(herramientas.DENO))
    monkeypatch.setattr(herramientas, "FFMPEG", dict(herramientas.FFMPEG))
    monkeypatch.setattr(herramientas, "TDL", dict(herramientas.TDL))
    monkeypatch.setattr(herramientas, "TABLAS", {"ffmpeg": herramientas.FFMPEG, "deno": herramientas.DENO,
                                                 "TwitchDownloaderCLI": herramientas.TDL})


def test_instalar_sha_malo_no_deja_nada(bin_dir, red):
    z = zip_bytes({"deno": b"#!deno"})
    red["https://x/deno.zip"] = z
    herramientas.DENO["x64"] = Paquete("https://x/deno.zip", "0" * 64, ("deno",))
    with pytest.raises(RuntimeError, match="sha256 incorrecto"):
        herramientas.instalar("deno", bin_dir)
    assert list(bin_dir.iterdir()) == []


def test_instalar_falta_miembro(bin_dir, red):
    z = zip_bytes({"otra-cosa": b"x"})
    red["https://x/deno.zip"] = z
    herramientas.DENO["x64"] = Paquete("https://x/deno.zip", hashlib.sha256(z).hexdigest(), ("deno",))
    with pytest.raises(RuntimeError, match="no trae"):
        herramientas.instalar("deno", bin_dir)


def test_tdl_extrae_todo_el_zip(bin_dir, red):
    z = zip_bytes({"TwitchDownloaderCLI": b"T", "COPYRIGHT.txt": b"c"})
    red["https://x/t.zip"] = z
    herramientas.TDL["x64"] = Paquete("https://x/t.zip", hashlib.sha256(z).hexdigest())
    assert sorted(herramientas.instalar("TwitchDownloaderCLI", bin_dir)) == ["COPYRIGHT.txt", "TwitchDownloaderCLI"]


def test_setup_baja_solo_lo_que_falta(bin_dir, red, monkeypatch):
    monkeypatch.setattr(herramientas, "whisper_listo", lambda: True)
    for n in ("ffmpeg", "ffprobe", "TwitchDownloaderCLI"):
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / n).write_text("x")
    z = zip_bytes({"deno": b"d"})
    red["https://x/deno.zip"] = z
    herramientas.DENO["x64"] = Paquete("https://x/deno.zip", hashlib.sha256(z).hexdigest(), ("deno",))
    out = []
    herramientas.setup(salida=out.append)
    assert red.pedidas == ["https://x/deno.zip"]
    assert (bin_dir / "deno").is_file()
    red.pedidas.clear()
    herramientas.setup(salida=out.append)
    assert red.pedidas == []                                   # idempotente
    hechas = []
    monkeypatch.setattr(herramientas, "instalar", lambda h, bin_dir=None: hechas.append(h))
    herramientas.setup(forzar=True, salida=out.append)         # --forzar rebaja todo, aunque ya esté
    assert hechas == ["ffmpeg", "deno", "TwitchDownloaderCLI"]


# --- doctor -------------------------------------------------------------------------

def test_doctor_sin_binarios_devuelve_1(bin_dir, monkeypatch):
    monkeypatch.setattr(herramientas, "whisper_listo", lambda: False)
    out = []
    assert herramientas.doctor(out.append) == 1
    txt = "\n".join(out)
    assert "✗" in txt and "faltan: ffmpeg, ffprobe, deno, TwitchDownloaderCLI" in txt
    assert "modo de Claude: ninguno" in txt


def test_doctor_con_binarios_devuelve_0(bin_dir, monkeypatch):
    monkeypatch.setattr(herramientas, "whisper_listo", lambda: True)
    monkeypatch.setattr(herramientas, "_version", lambda cmd, patron: ("9.9", ""))
    bin_dir.mkdir(parents=True, exist_ok=True)
    for n in ("ffmpeg", "ffprobe", "deno", "TwitchDownloaderCLI"):
        (bin_dir / n).write_text("x")
    (rutas.home() / "app.yaml").write_text("claude:\n  modo: api_key\n")
    out = []
    assert herramientas.doctor(out.append) == 0
    txt = "\n".join(out)
    assert "✗" not in txt and "modo de Claude: api_key" in txt


def _doctor_con_binarios_falsos(bin_dir, monkeypatch, rc_tdl):
    """Todos los binarios existen; TwitchDownloaderCLI arranca o no según rc_tdl."""
    monkeypatch.setattr(herramientas, "whisper_listo", lambda: True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for n in ("ffmpeg", "ffprobe", "deno", "TwitchDownloaderCLI"):
        (bin_dir / n).write_text("x")

    def run(cmd, **k):
        n = cmd[0].rsplit("/", 1)[-1]
        if n == "TwitchDownloaderCLI":
            return subprocess.CompletedProcess(cmd, rc_tdl, "", "Couldn't find a valid ICU package" if rc_tdl else "TwitchDownloaderCLI 1.56.5+abc")
        return subprocess.CompletedProcess(cmd, 0, {"deno": "deno 2.9.8"}.get(n, f"{n} version N-1"), "")
    monkeypatch.setattr(herramientas.subprocess, "run", run)
    out = []
    return herramientas.doctor(out.append), "\n".join(out)


def test_doctor_binario_que_no_arranca_sale_x(bin_dir, monkeypatch):
    rc, txt = _doctor_con_binarios_falsos(bin_dir, monkeypatch, rc_tdl=134)
    assert "ICU" in txt
    assert rc == 1
    fila = next(ln for ln in txt.splitlines() if ln.startswith("TwitchDownloaderCLI"))
    assert "ICU" in fila and fila.rstrip().endswith("✗")
    assert "faltan: TwitchDownloaderCLI" in txt


def test_doctor_binario_que_arranca_sale_ok(bin_dir, monkeypatch):
    rc, txt = _doctor_con_binarios_falsos(bin_dir, monkeypatch, rc_tdl=0)
    assert rc == 0
    fila = next(ln for ln in txt.splitlines() if ln.startswith("TwitchDownloaderCLI"))
    assert "1.56.5" in fila and fila.rstrip().endswith("✓")


def test_doctor_version_con_rc_1_cuenta_como_ok(bin_dir, monkeypatch):
    """TwitchDownloaderCLI --version imprime la versión y sale con rc 1."""
    monkeypatch.setattr(herramientas, "whisper_listo", lambda: True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for n in ("ffmpeg", "ffprobe", "deno", "TwitchDownloaderCLI"):
        (bin_dir / n).write_text("x")
    monkeypatch.setattr(herramientas.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, "ffmpeg version 7 deno 2.9.8 TwitchDownloaderCLI 1.56.5+abc", ""))
    assert herramientas.doctor(lambda *_: None) == 0


def test_version_con_error_del_cargador_no_cuenta(tmp_path):
    """Un binario que el cargador no deja arrancar no da ✓ aunque el error contenga algo con forma de versión."""
    v, motivo = herramientas._version(
        ["sh", "-c", "echo \"ffmpeg: /lib/libc.so.6: version \\`GLIBC_2.38' not found\" >&2; exit 1"], r"version (\S+)")
    assert v == "" and "rc 1" in motivo
    v, _ = herramientas._version(["sh", "-c", "echo \"libstdc++.so.6: version GLIBCXX_3.4.30 not found\" >&2; exit 1"],
                                 r"(\d+\.\d+\.\d+\S*)")
    assert v == ""
