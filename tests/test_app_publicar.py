import csv

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from clipero.app import publicar  # noqa: E402
from clipero.app.server import create_app  # noqa: E402
from clipero.score import load_published  # noqa: E402

CAB = "fecha,slug,fuente,formato,tono,vod_id,start,end,url\n"
FILA = "2026-11-01,viejo-a,ibai,arco,critica,111,1.00,2.00,https://youtu.be/zzz\n"
URL = "https://youtube.com/shorts/PRUEBA123"
YAML_RECOP = """slug: recop
formato: recopilacion
tono: neutro
fuente: ibai
titulo: t
tramos:
  - {vod: "900", start: 50.0, end: 60.5}
  - {vod: "800", start: 1.0, end: 5.0}
  - {vod: "900", start: 10.123, end: 20.0}
"""


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "out" / "2026-11-02"
    d.mkdir(parents=True)
    for s in ("recop", "sinyaml", "sintono"):
        (d / f"{s}.mp4").write_bytes(b"x")
    (d / "recop.short.yaml").write_text(YAML_RECOP)
    (d / "sintono.short.yaml").write_text(
        "slug: sintono\nformato: arco\nfuente: ibai\ntitulo: t\ntramos:\n  - {vod: \"7\", start: 1, end: 2}\n")
    (tmp_path / "sources.yaml").write_text("- id: ibai\n  nombre: Ibai\n- id: elxokas\n  nombre: e\n")
    (tmp_path / "publicados.csv").write_text(CAB + FILA)
    return tmp_path


@pytest.fixture
def c(root):
    return TestClient(create_app(root))


def filas(root):
    return list(csv.DictReader(open(root / "publicados.csv", newline="")))


def test_start_end_de_recopilacion_con_dos_vods(c, root):
    r = c.post("/api/clips/2026-11-02/recop/publicar", json={"url": "  " + URL + " "})
    assert r.status_code == 201
    f = r.json()["fila"]
    assert (f["vod_id"], f["start"], f["end"], f["url"]) == ("900", "10.12", "60.50", URL)
    assert filas(root)[-1] == f and list(f) == publicar.COLS
    assert f["fecha"] == __import__("datetime").date.today().isoformat()


def test_cabecera_e_historial_intactos(c, root):
    c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    txt = (root / "publicados.csv").read_text()
    assert txt.startswith(CAB + FILA) and txt.count("\n") == 3


def test_fila_legible_por_score(c, root):
    c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    assert load_published(root / "publicados.csv", "900") == [(10.12, 60.5)]


def test_url_no_youtube_400(c, root):
    for u in ("https://vimeo.com/1", "http://youtube.com/shorts/x", "", "https://youtube.com/@canal"):
        r = c.post("/api/clips/2026-11-02/recop/publicar", json={"url": u})
        assert r.status_code == 400 and r.json() == {"error": "url"}
    assert len(filas(root)) == 1


def test_doble_publicacion_409(c, root):
    assert c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL}).status_code == 201
    r = c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    assert r.status_code == 409 and r.json() == {"error": "ya_publicado"}
    assert len(filas(root)) == 2


def test_borrar_lo_publicado_409(c, root):
    c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    assert c.delete("/api/clips/2026-11-02/recop").status_code == 409
    assert (root / "out" / "2026-11-02" / "recop.mp4").exists()


def test_overrides_cuando_faltan_campos(c, root):
    r = c.post("/api/clips/2026-11-02/sintono/publicar", json={"url": URL})
    assert r.status_code == 400 and r.json() == {"error": "tono"}
    r = c.post("/api/clips/2026-11-02/sintono/publicar", json={"url": URL, "tono": "raro"})
    assert r.json() == {"error": "tono"}
    r = c.post("/api/clips/2026-11-02/sintono/publicar", json={"url": URL, "tono": "critica"})
    assert r.status_code == 201 and r.json()["fila"]["tono"] == "critica"


def test_sin_yaml_campos_vacios(c, root):
    r = c.post("/api/clips/2026-11-02/sinyaml/publicar", json={"url": URL})
    assert r.json() == {"error": "fuente"}
    r = c.post("/api/clips/2026-11-02/sinyaml/publicar",
               json={"url": URL, "fuente": "nadie", "formato": "arco", "tono": "neutro"})
    assert r.json() == {"error": "fuente"}
    r = c.post("/api/clips/2026-11-02/sinyaml/publicar",
               json={"url": URL, "fuente": "elxokas", "formato": "arco", "tono": "neutro"})
    f = r.json()["fila"]
    assert (f["vod_id"], f["start"], f["end"]) == ("", "", "")
    assert load_published(root / "publicados.csv", "") == []


def test_publicar_404_y_ruta_invalida(c):
    assert c.post("/api/clips/2026-11-02/nada/publicar", json={"url": URL}).status_code == 404
    assert c.post("/api/clips/2026-11-02/..x/publicar", json={"url": URL}).status_code == 404


def test_crea_csv_si_no_existe(c, root):
    (root / "publicados.csv").unlink()
    assert c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL}).status_code == 201
    assert (root / "publicados.csv").read_text().startswith(CAB)


def test_cabecera_distinta_500_sin_escribir(c, root):
    (root / "publicados.csv").write_text("a,b\n1,2\n")
    r = c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    assert r.status_code == 500 and (root / "publicados.csv").read_text() == "a,b\n1,2\n"


def test_claim(c, root):
    assert c.post("/api/clips/2026-11-02/recop/claim").status_code == 409
    c.post("/api/clips/2026-11-02/recop/publicar", json={"url": URL})
    antes = (root / "publicados.csv").read_text().splitlines()
    assert c.post("/api/clips/2026-11-02/recop/claim").status_code == 204
    despues = (root / "publicados.csv").read_text().splitlines()
    assert despues[:-1] == antes[:-1] and despues[-1] == antes[-1] + "#claim"
    assert c.post("/api/clips/2026-11-02/recop/claim").status_code == 204   # idempotente
    assert (root / "publicados.csv").read_text().splitlines() == despues
    assert not list(root.glob("*.tmp"))
    g = {x["base"]: x for x in c.get("/api/clips").json()}["recop"]
    assert g["versiones"][0]["publicado"]["claim"] is True
    assert g["versiones"][0]["publicado"]["url"] == URL
    assert load_published(root / "publicados.csv", "900") == [(10.12, 60.5)]


def test_claim_404(c):
    assert c.post("/api/clips/2026-11-02/nada/claim").status_code == 404
