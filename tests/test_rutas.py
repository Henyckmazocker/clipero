from pathlib import Path

import pytest

from clipero import cli, rutas
from clipero.plantilla_init import init


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    """HOME y XDG propios, sin CLIPERO_HOME ni --home."""
    monkeypatch.delenv("CLIPERO_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "h" / ".config"))
    rutas.fijar(None)
    yield tmp_path
    rutas.fijar(None)


def test_orden_de_resolucion(aislado, monkeypatch):
    por_defecto = Path(str(aislado / "h")) / "Clipero"
    assert rutas.home() == por_defecto
    f = rutas.fichero_home()
    f.parent.mkdir(parents=True)
    f.write_text(f"{aislado / 'fichero'}\notra linea\n")
    assert rutas.home() == (aislado / "fichero").resolve()
    monkeypatch.setenv("CLIPERO_HOME", str(aislado / "entorno"))
    assert rutas.home() == (aislado / "entorno").resolve()
    rutas.fijar(aislado / "opcion")
    assert rutas.home() == (aislado / "opcion").resolve()
    assert rutas.vods() == rutas.home() / "data" / "vods"
    assert rutas.binario("x").parent == rutas.home() / ".clipero" / "bin"
    assert not (aislado / "opcion").exists()   # home() no crea nada


def test_init_no_sobrescribe(aislado):
    d = aislado / "c"
    init(d, log=lambda *_: None)
    assert (d / ".clipero" / "version").exists() and (d / ".gitignore").exists()
    assert (d / ".claude" / "skills" / "tanda" / "SKILL.md").exists()
    assert "# Reserva" in (d / "sources.yaml").read_text()
    assert rutas.fichero_home().read_text().strip() == str(d.resolve())
    (d / "sources.yaml").write_text("mio")
    (d / "CLAUDE.md").write_text("mio")
    init(d, log=lambda *_: None)
    assert (d / "sources.yaml").read_text() == "mio" and (d / "CLAUDE.md").read_text() == "mio"


def test_actualizar_solo_toca_skill_y_claude_md(aislado):
    d = aislado / "c"
    init(d, log=lambda *_: None)
    for f in ("sources.yaml", "app.yaml", "branding.yaml", "publicados.csv", ".gitignore"):
        (d / f).write_text("mio")
    (d / "CLAUDE.md").write_text("viejo")
    (d / ".claude" / "skills" / "tanda" / "SKILL.md").write_text("vieja")
    (d / ".clipero" / "version").write_text("0.0.0\n")
    rutas.fichero_home().write_text("otro\n")
    init(d, actualizar=True, log=lambda *_: None)
    assert (d / "CLAUDE.md").read_text() != "viejo"
    assert (d / ".claude" / "skills" / "tanda" / "SKILL.md").read_text() != "vieja"
    assert (d / ".clipero" / "version").read_text() != "0.0.0\n"
    for f in ("sources.yaml", "app.yaml", "branding.yaml", "publicados.csv", ".gitignore"):
        assert (d / f).read_text() == "mio"
    assert rutas.fichero_home().read_text() == "otro\n"


def test_init_crea_linea_editorial_y_actualizar_no_la_toca(aislado):
    d = aislado / "c"
    init(d, log=lambda *_: None)
    le = d / "linea-editorial.md"
    assert le.is_file() and "izquier" not in le.read_text()
    le.write_text("la mía")
    init(d, log=lambda *_: None)                    # init sin --actualizar tampoco la pisa
    assert le.read_text() == "la mía"
    init(d, actualizar=True, log=lambda *_: None)
    assert le.read_text() == "la mía"
    le.unlink()
    init(d, actualizar=True, log=lambda *_: None)   # --actualizar no la recrea
    assert not le.exists()
    skill = (d / ".claude" / "skills" / "tanda" / "SKILL.md").read_text()
    assert "linea-editorial.md" in skill and "izquier" not in skill


def test_sin_version_vods_falla_con_el_mensaje(aislado, capsys):
    assert cli.main(["--home", str(aislado / "vacia"), "vods"]) == 1
    err = capsys.readouterr().err
    assert "no hay carpeta de trabajo en" in err and "clipero init" in err


def test_home_global_antes_de_despachar(aislado, capsys):
    d = aislado / "c"
    assert cli.main(["init", str(d)]) == 0
    assert cli.main(["--home", str(d), "clean", "--dias", "99"]) == 0


def test_branding_de_la_plantilla_es_sin_marca(home_tmp):
    from clipero import render
    assert render.load_branding() is None


def test_reserva_de_la_plantilla_la_entiende_config(home_tmp):
    from clipero import config
    cabeza, cola = config.split_sources((home_tmp / "sources.yaml").read_text())
    assert cola.startswith("# Reserva")


def test_app_abrir_llama_a_webbrowser(aislado, monkeypatch):
    """`clipero app --abrir` lanza webbrowser.open con la URL del puerto (uvicorn y el temporizador, falsos)."""
    import threading
    import uvicorn
    import webbrowser
    init(aislado / "c", log=lambda *_: None)
    abiertas = []
    monkeypatch.setattr(webbrowser, "open", abiertas.append)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(threading.Timer, "start", lambda self: self.function(*self.args))
    assert cli.main(["--home", str(aislado / "c"), "app", "--port", "8123", "--abrir"]) == 0
    assert abiertas == ["http://127.0.0.1:8123"]
