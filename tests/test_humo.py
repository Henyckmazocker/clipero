"""Prueba de humo: ffmpeg de verdad + `render` de un short `momento` con el fetch simulado.

No corre en `pytest -q` (addopts = -m 'not humo'); se pide con `pytest -q -m humo`. Es lo que valida la
cadena de filtros y el códec en la CI (ubuntu).
"""
import json
import shutil
import subprocess

import pytest
import yaml

from clipero import herramientas, render

pytestmark = pytest.mark.humo

VOD = "humo0000001"
INICIO, FIN = 100.0, 122.0   # 22 s: el mínimo del formato son 20 s, así que el vídeo de prueba dura 25


@pytest.fixture
def binarios(monkeypatch):
    """ffmpeg/ffprobe resueltos con la carpeta de trabajo REAL (la de `clipero setup`), antes de que `home_tmp`
    la cambie; luego `herramientas.ruta` devuelve esos aunque la carpeta de la prueba esté vacía."""
    ff, fp = herramientas.ruta("ffmpeg"), herramientas.ruta("ffprobe")
    if not ff or not fp:
        pytest.skip("sin ffmpeg/ffprobe (clipero setup)")
    original = herramientas.ruta
    monkeypatch.setattr(herramientas, "ruta",
                        lambda n: {"ffmpeg": ff, "ffprobe": fp}.get(n) or original(n))
    return ff, fp


def test_render_momento_de_extremo_a_extremo(binarios, home_tmp, monkeypatch, tmp_path):
    ff, fp = binarios
    fuente = tmp_path / "fuente.mp4"
    r = subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=25",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=25", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(fuente)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    (home_tmp / "sources.yaml").write_text(yaml.safe_dump(
        [{"id": "pruebas", "nombre": "Pruebas", "tamaño": "mediano", "youtube": "https://www.youtube.com/@pruebas/streams",
          "credito": "Pruebas (youtube.com/@pruebas)"}], allow_unicode=True))
    d = home_tmp / "data" / "vods" / VOD
    (d / "win").mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"id": VOD, "extractor": "youtube", "uploader_id": "@pruebas"}))
    (d / "candidatos.json").write_text(json.dumps([{"n": 1, "start": INICIO - 5, "end": FIN + 5}]))
    palabras = [{"w": w, "s": INICIO + 1 + i * 0.5, "e": INICIO + 1.4 + i * 0.5}
                for i, w in enumerate("esto es una prueba de humo del render".split())]
    (d / "win" / "1.words.json").write_text(json.dumps(palabras))

    def fetch_falso(vod_id, plataforma, start, end, out, audio_only=True, fmt=None):
        shutil.copyfile(fuente, out)
        return out, start   # el fichero empieza en `start`

    monkeypatch.setattr(render, "fetch_section", fetch_falso)

    spec = home_tmp / "short.yaml"
    spec.write_text(yaml.safe_dump({
        "slug": "prueba-humo", "formato": "momento", "tono": "neutro", "fuente": "pruebas",
        "titulo": "Prueba de humo", "descripcion": "Short sintético",
        "tramos": [{"vod": VOD, "start": INICIO, "end": FIN}],
        "rotulos": [{"t": 0.0, "dur": 2.5, "tipo": "gancho", "texto": "ESTO ES\nUNA PRUEBA: ¿FUNCIONA?"}],
        "zoom": [{"t": 15.0, "dur": 2.0, "factor": 1.25}], "voz": None}, allow_unicode=True))

    final = render.render(spec, log=lambda *_: None)

    assert final.is_file() and final.parent.parent == home_tmp / "out"
    p = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-show_entries", "format=duration", "-of", "json", str(final)],
                       capture_output=True, text=True, check=True)
    info = json.loads(p.stdout)
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (1080, 1920)
    assert render.DUR_MIN <= float(info["format"]["duration"]) <= render.DUR_MAX
    assert (final.with_suffix(".meta.md")).is_file()
