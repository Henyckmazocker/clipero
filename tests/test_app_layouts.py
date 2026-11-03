import difflib
import json
import shutil
from pathlib import Path

import pytest
import yaml

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("ruamel.yaml")
from fastapi.testclient import TestClient  # noqa: E402

from clipero import frame  # noqa: E402
from clipero.app import layouts  # noqa: E402
from clipero.app.server import create_app  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "config"
SEG = "1148030_1149290"


@pytest.fixture
def root(tmp_path):
    shutil.copy(FIX / "sources.yaml", tmp_path / "sources.yaml")
    shutil.copy(FIX / "branding.yaml", tmp_path / "branding.yaml")
    (tmp_path / "layouts").mkdir()
    shutil.copy(FIX / "ibai.yaml", tmp_path / "layouts" / "ibai.yaml")
    return tmp_path


def cliente(root):
    return TestClient(create_app(root, periodico=False))


def falso_vod(root, vod="2915851966", uploader="ibai"):
    d = root / "data" / "vods" / vod
    (d / "seg").mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"uploader_id": uploader, "title": "Partido",
                                             "upload_date": "20261031", "extractor": "twitch:vod"}))
    (d / "seg" / f"{SEG}.mp4").write_bytes(b"\0" * 10_500)
    (d / "seg" / f"{SEG}.json").write_text(json.dumps({"offset": 11476.983}))
    (d / "seg" / "5_9.mp4").write_bytes(b"\0" * 100)   # demasiado pequeño: se ignora
    return d


def test_get_layouts_una_fila_por_canal(root):
    (root / "layouts" / "ibai").mkdir()
    (root / "layouts" / "ibai" / "123.yaml").write_text("entrada: 1920x1080\nfacecam: {x: 0, y: 0, w: 10, h: 10}\n"
                                                         "juego: {x: 0, y: 0, w: 1920, h: 1080}\n")
    filas = cliente(root).get("/api/layouts").json()
    ibai = next(f for f in filas if f["fuente"] == "ibai")
    assert ibai["canal"] is True and ibai["excepciones"] == ["123"]
    assert len(filas) == len(yaml.safe_load((root / "sources.yaml").read_text()))


def test_put_ibai_facecam_x_solo_cambia_esa_linea(root):
    c = cliente(root)
    antes = (root / "layouts" / "ibai.yaml").read_text()
    lay = c.get("/api/layouts/ibai").json()
    lay["escenas"]["partida"]["facecam"]["x"] = 1450
    assert c.put("/api/layouts/ibai", json=lay).status_code == 200
    despues = (root / "layouts" / "ibai.yaml").read_text()
    cambios = [l for l in difflib.unified_diff(antes.splitlines(), despues.splitlines(), lineterm="", n=0)
               if l[0] in "+-" and l[:3] not in ("+++", "---")]
    quitadas = [l for l in cambios if l[0] == "-"]
    assert len(quitadas) == 2 and len(cambios) == 4          # facecam + la alineación de `juego:`
    assert any("facecam" in l and "1460" in l for l in quitadas)
    assert any("facecam" in l and "1450" in l for l in cambios if l[0] == "+")
    assert all(l.lstrip("-+").lstrip().startswith(("facecam", "juego")) for l in cambios)
    assert "# El marco del recuadro mide" in despues and "→ arriba, 1080" in despues
    assert yaml.safe_load(despues)["escenas"]["partida"]["facecam"]["x"] == 1450


def test_put_invalido_422_y_fichero_intacto(root):
    c = cliente(root)
    antes = (root / "layouts" / "ibai.yaml").read_text()
    lay = c.get("/api/layouts/ibai").json()
    lay["escenas"]["partida"]["facecam"]["x"] = 1460.0      # float → inválido
    r = c.put("/api/layouts/ibai", json=lay)
    assert r.status_code == 422 and r.json()["error"] == "invalido" and r.json()["detalle"]
    lay["escenas"]["partida"]["facecam"] = {"x": 1800, "y": 550, "w": 460, "h": 240}   # fuera de entrada
    assert c.put("/api/layouts/ibai", json=lay).status_code == 422
    assert (root / "layouts" / "ibai.yaml").read_text() == antes
    assert not list((root / "layouts").glob("*.tmp"))


def test_excepcion_put_get_delete(root):
    c = cliente(root)
    lay = {"entrada": "1920x1080", "facecam": {"x": 10, "y": 20, "w": 300, "h": 200},
           "juego": {"x": 0, "y": 0, "w": 1920, "h": 1080}}
    assert c.get("/api/layouts/ibai/2914173138").status_code == 404
    assert c.put("/api/layouts/ibai/2914173138", json=lay).status_code == 200
    f = root / "layouts" / "ibai" / "2914173138.yaml"
    assert "facecam: {x: 10, y: 20, w: 300, h: 200}" in f.read_text()    # rectángulos en flujo
    assert c.get("/api/layouts/ibai/2914173138").json() == lay
    assert c.get("/api/layouts").json()[0]["excepciones"] == ["2914173138"] or any(
        x["excepciones"] == ["2914173138"] for x in c.get("/api/layouts").json())
    assert frame.load_layout("ibai", root / "layouts", vod="2914173138")["facecam"]["x"] == 10
    assert c.delete("/api/layouts/ibai/2914173138").status_code == 204
    assert not f.exists() and not (root / "layouts" / "ibai").exists()
    assert c.delete("/api/layouts/ibai/2914173138").status_code == 404
    assert (root / "layouts" / "ibai.yaml").is_file()


def test_nombres_invalidos_404(root):
    c = cliente(root)
    assert c.get("/api/layouts/IBAI").status_code == 404
    assert c.put("/api/layouts/ibai/a.b", json={}).status_code == 404


def test_vods_con_data_falsa(root):
    falso_vod(root)
    falso_vod(root, "999", uploader="otrocanal")
    r = cliente(root).get("/api/layouts/ibai/vods")
    assert r.status_code == 200
    (v,) = r.json()
    assert v["vod"] == "2915851966" and v["plataforma"] == "twitch" and v["fecha"] == "2026-10-31"
    (t,) = v["tramos"]
    assert t["seg"] == SEG and t["start"] == 11480.3 and t["end"] == 11492.9 and t["offset"] == 11476.983


def test_frame_fuera_de_tramo_y_traversal(root):
    falso_vod(root)
    c = cliente(root)
    assert c.get(f"/api/frame/2915851966/{SEG}.jpg?t=5").status_code == 422
    assert c.get("/api/frame/..%2F..%2Fx/1_2.jpg?t=1").status_code == 404
    assert c.get("/api/frame/2915851966/..%2F..%2Fsources.jpg?t=1").status_code == 404
    assert c.get("/api/frame/2915851966/../../x.jpg?t=1").status_code == 404
    assert c.get(f"/api/frame/nada/{SEG}.jpg?t=11485").status_code == 404


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")
def test_frame_con_ffmpeg(root):
    import subprocess
    d = falso_vod(root)
    mp4 = d / "seg" / f"{SEG}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=13",
                    "-c:v", "mpeg4", "-b:v", "2M", str(mp4)], check=True)
    c = cliente(root)
    r = c.get(f"/api/frame/2915851966/{SEG}.jpg?t=11485")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    assert (root / "data/app/frames/2915851966" / f"{SEG}_114850.jpg").is_file()
    (v,) = c.get("/api/layouts/ibai/vods").json()
    assert (v["tramos"][0]["w"], v["tramos"][0]["h"]) == (320, 180)


def _marco(root, con_marco):
    import cv2
    import numpy as np
    falso_vod(root)
    img = np.full((1080, 1920), 20, np.uint8)
    if con_marco:
        img[535:810, 1445:1920] = 200     # marco recto alrededor de facecam {1460,550,460,240}
    jpg = root / "data/app/frames/2915851966" / f"{SEG}_114850.jpg"
    jpg.parent.mkdir(parents=True)
    cv2.imwrite(str(jpg), img)


def test_probar_detecta_marco_sintetico(root):
    _marco(root, True)
    lay = yaml.safe_load((root / "layouts" / "ibai.yaml").read_text())
    r = cliente(root).post("/api/layouts/probar", json={"layout": lay, "vod": "2915851966", "seg": SEG, "t": 11485})
    assert r.status_code == 200
    d = r.json()
    assert d["detecta"] is True and d["umbral"] == frame.SCENE_THR and d["score"] > 0.9


def test_probar_sin_marco_no_detecta_y_plano_422(root):
    _marco(root, False)
    c = cliente(root)
    lay = yaml.safe_load((root / "layouts" / "ibai.yaml").read_text())
    cuerpo = {"layout": lay, "vod": "2915851966", "seg": SEG, "t": 11485}
    assert c.post("/api/layouts/probar", json=cuerpo).json()["detecta"] is False
    plano = {"entrada": "1920x1080", "facecam": {"x": 0, "y": 0, "w": 10, "h": 10},
             "juego": {"x": 0, "y": 0, "w": 1920, "h": 1080}}
    r = c.post("/api/layouts/probar", json={**cuerpo, "layout": plano})
    assert r.status_code == 422 and r.json()["error"] == "sin_escena_detectable"


def test_purgar_frames(root):
    import os
    import time
    viejo = root / "data/app/frames/v/a_1.jpg"
    nuevo = root / "data/app/frames/v/a_2.jpg"
    viejo.parent.mkdir(parents=True)
    viejo.write_bytes(b"x")
    nuevo.write_bytes(b"x")
    os.utime(viejo, (time.time() - 15 * 86400,) * 2)
    assert layouts.purgar_frames(root) == 1
    assert not viejo.exists() and nuevo.exists()


@pytest.mark.parametrize("rect", [{"x": 0, "y": 0, "w": 400, "h": 300}, {"x": 100, "y": 100, "w": 10, "h": 10}])
def test_probar_facecam_degenerada_200_sin_deteccion(root, rect):
    _marco(root, True)
    lay = {"entrada": "1920x1080", "escenas": {"a": {"facecam": rect, "juego": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
                                               "b": {"ancho": True}}}
    r = cliente(root).post("/api/layouts/probar", json={"layout": lay, "vod": "2915851966", "seg": SEG, "t": 11485})
    assert r.status_code == 200
    assert r.json()["detecta"] is False and r.json()["score"] == 0.0 and r.json()["aviso"]
