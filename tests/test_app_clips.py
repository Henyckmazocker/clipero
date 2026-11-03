import shutil
import subprocess

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from clipero.app import clips  # noqa: E402
from clipero.app.server import create_app  # noqa: E402

CAB = "fecha,slug,fuente,formato,tono,vod_id,start,end,url\n"

META_TONO = (
    "**Título:** Un título #shorts\n"
    "**Descripción:** Linea uno.\\nFuente: elxokas (twitch.tv/elxokas) — directo.\n"
    "**Hashtags:** #a #b\n"
    "**Formato:** arco · **Tono:** positivo · **Duración:** 43,6 s · **Encuadre:** cara\n"
    "**Avisos:** ninguno\n")
META_SIN_TONO = (
    "**Título:** Viejo #shorts\n"
    "**Descripción:** Pesaje.\\nFuente: Ibai (twitch.tv/ibai) — directo.\n"
    "**Hashtags:** #ibai\n"
    "**Formato:** momento · **Duración:** 41,5 s · **Encuadre:** cara\n"
    "**Avisos:** ninguno\n")
SOURCES = ("- id: ibai\n  nombre: Ibai\n  credito: \"Ibai (twitch.tv/ibai)\"\n"
           "- id: elxokas\n  nombre: elxokas\n  credito: \"elxokas (twitch.tv/elxokas)\"\n"
           "- id: djmariio\n  nombre: Djmariio\n  credito: \"Djmariio (twitch.tv/djmariio)\"\n")


def clip(root, fecha, slug, meta=META_TONO, yaml=None):
    d = root / "out" / fecha
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.mp4").write_bytes(b"mp4")
    if meta is not None:
        (d / f"{slug}.meta.md").write_text(meta)
    if yaml is not None:
        (d / f"{slug}.short.yaml").write_text(yaml)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "sources.yaml").write_text(SOURCES)
    (tmp_path / "publicados.csv").write_text(
        CAB + "2026-11-02,x-v2,elxokas,arco,critica,1,1.00,2.00,https://youtube.com/shorts/aaa#claim\n")
    clip(tmp_path, "2026-11-02", "x", yaml="slug: x\nformato: arco\ntono: neutro\nfuente: djmariio\ntramos: []\n")
    clip(tmp_path, "2026-11-02", "x-v2")
    clip(tmp_path, "2026-11-02", "x-v10")
    clip(tmp_path, "2026-11-01", "viejo", meta=META_SIN_TONO)
    return tmp_path


def test_parse_meta_con_tono():
    m = clips.parse_meta(META_TONO)
    assert m["titulo"] == "Un título #shorts"
    assert m["descripcion"].startswith("Linea uno.\nFuente: elxokas")
    assert (m["formato"], m["tono"], m["duracion_s"], m["encuadre"], m["avisos"]) == ("arco", "positivo", 43.6, "cara", [])
    assert m["hashtags"] == "#a #b"


def test_parse_meta_sin_tono_y_avisos():
    m = clips.parse_meta(META_SIN_TONO.replace("ninguno", "uno; dos"))
    assert m["tono"] is None and m["formato"] == "momento" and m["duracion_s"] == 41.5
    assert m["avisos"] == ["uno", "dos"]


def test_parse_meta_tono_interrogante():
    assert clips.parse_meta(META_TONO.replace("positivo", "?"))["tono"] is None


def test_agrupa_versiones(root):
    g = {(x["fecha"], x["base"]): x for x in clips.escanear(root)}
    assert [v["slug"] for v in g[("2026-11-02", "x")]["versiones"]] == ["x", "x-v2", "x-v10"]
    assert [v["n"] for v in g[("2026-11-02", "x")]["versiones"]] == [1, 2, 10]
    assert ("2026-11-01", "viejo") in g
    assert [x["fecha"] for x in clips.escanear(root)] == ["2026-11-02", "2026-11-01"]


def test_fuente_formato_y_editable(root):
    g = {x["base"]: x for x in clips.escanear(root)}
    v1, v2, _ = g["x"]["versiones"]
    assert (v1["fuente"], v1["tono"], v1["editable"]) == ("djmariio", "neutro", True)   # del yaml
    assert (v2["fuente"], v2["tono"], v2["editable"]) == ("elxokas", "positivo", False)  # del crédito y del meta
    assert g["viejo"]["versiones"][0]["fuente"] == "ibai" and g["viejo"]["versiones"][0]["tono"] is None
    assert g["x"]["fuente"] == "djmariio"


def test_publicado_por_slug_exacto(root):
    v1, v2, v10 = clips.escanear(root)[0]["versiones"]
    assert v1["publicado"] is None and v10["publicado"] is None
    assert v2["publicado"] == {"fecha": "2026-11-02", "url": "https://youtube.com/shorts/aaa", "claim": True}


def test_filtros(root):
    g = clips.escanear(root)
    assert [x["base"] for x in clips.filtrar(g, fuente="djmariio")] == ["x"]
    assert len(clips.filtrar(g, fuente="djmariio")[0]["versiones"]) == 3   # el grupo entero
    assert [x["base"] for x in clips.filtrar(g, publicado="si")] == ["x"]
    assert [x["base"] for x in clips.filtrar(g, publicado="no")] == ["x", "viejo"]
    assert [x["base"] for x in clips.filtrar(g, hasta="2026-11-01")] == ["viejo"]
    assert [x["base"] for x in clips.filtrar(g, desde="2026-11-02", tono="positivo")] == ["x"]
    assert clips.filtrar(g, formato="recopilacion") == []


def test_sin_out(tmp_path):
    assert clips.escanear(tmp_path) == []


def test_api_clips_y_validacion(root):
    c = TestClient(create_app(root))
    r = c.get("/api/clips?fuente=ibai")
    assert [x["base"] for x in r.json()] == ["viejo"]
    assert r.json()[0]["versiones"][0]["mp4"] == "/media/out/2026-11-01/viejo.mp4"
    assert c.get("/api/thumbs/..-x/viejo.jpg").status_code == 404
    assert c.get("/api/thumbs/2026-11-01/..%2Fx.jpg").status_code == 404
    assert c.delete("/api/clips/2026-11-01/Viejo").status_code == 404
    assert c.post("/api/clips/2026-1-01/viejo/claim").status_code == 404


def test_borrar(root):
    c = TestClient(create_app(root))
    thumb = root / "data" / "app" / "thumbs" / "2026-11-02" / "x.jpg"
    thumb.parent.mkdir(parents=True)
    thumb.write_bytes(b"j")
    assert c.delete("/api/clips/2026-11-02/x").status_code == 204
    d = root / "out" / "2026-11-02"
    assert not (d / "x.mp4").exists() and not (d / "x.meta.md").exists()
    assert not (d / "x.short.yaml").exists() and not thumb.exists()
    assert (d / "x-v2.mp4").exists()


def test_borrar_publicado_409(root):
    c = TestClient(create_app(root))
    r = c.delete("/api/clips/2026-11-02/x-v2")
    assert r.status_code == 409 and r.json() == {"error": "publicado"}
    assert (root / "out" / "2026-11-02" / "x-v2.mp4").exists()
    assert c.delete("/api/clips/2026-11-02/nada").status_code == 404


def test_abrir_carpeta_mockeado(root, monkeypatch):
    llamadas = []
    monkeypatch.setattr("clipero.sistema.abrir", llamadas.append)
    c = TestClient(create_app(root))
    assert c.post("/api/clips/2026-11-02/x/abrir-carpeta").status_code == 204
    assert llamadas == [root / "out" / "2026-11-02"]
    assert c.post("/api/clips/2026-11-02/nada/abrir-carpeta").status_code == 404
    assert len(llamadas) == 1


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")
def test_miniatura(tmp_path):
    d = tmp_path / "out" / "2026-11-02"
    d.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=108x192:d=2:r=10",
                    "-pix_fmt", "yuv420p", str(d / "a.mp4")], check=True)
    j = clips.miniatura(tmp_path, "2026-11-02", "a")
    assert j == tmp_path / "data" / "app" / "thumbs" / "2026-11-02" / "a.jpg"
    assert j.read_bytes()[:2] == b"\xff\xd8"
    assert not list(d.glob("*.jpg"))   # nunca en out/
    r = TestClient(create_app(tmp_path)).get("/api/thumbs/2026-11-02/a.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert TestClient(create_app(tmp_path)).get("/api/thumbs/2026-11-02/b.jpg").status_code == 404
