import asyncio
import threading
from datetime import date

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from clipero import stats  # noqa: E402
from clipero.app import rendimiento  # noqa: E402
from clipero.app.medidor import Medidor  # noqa: E402
from clipero.app.server import create_app  # noqa: E402

PUB = "fecha,slug,fuente,formato,tono,vod_id,start,end,url\n"
PIL = "fecha_medida,slug,vistas,likes,comentarios,suscriptores_canal,claim\n"


def montar(tmp_path, pub, pil):
    (tmp_path / "publicados.csv").write_text(PUB + pub)
    (tmp_path / "piloto.csv").write_text(PIL + pil)
    return tmp_path


def test_series_con_dias_ausentes_y_dow(tmp_path):
    # 2026-11-02 es lunes y 2026-11-04 miércoles
    root = montar(tmp_path,
                  "2026-11-02,a,ibai,arco,critica,1,0,1,https://youtube.com/shorts/a\n"
                  "2026-11-04,b,elxokas,momento,,1,0,1,https://youtube.com/shorts/b#claim\n",
                  "2026-11-02,a,10,1,0,,0\n"
                  "2026-11-05,a,50,2,1,,0\n"          # día 3; los días 1 y 2 no existen
                  "2026-11-05,b,7,,,,1\n")
    r = rendimiento.rendimiento(root, hoy="2026-11-06")
    assert r["series"]["a"] == [{"dia": 0, "vistas": 10}, {"dia": 3, "vistas": 50}]
    assert r["series"]["b"] == [{"dia": 1, "vistas": 7}]
    assert set(r["agregados"]["dow"]) == {"lun", "mié"}
    assert r["agregados"]["dow"]["lun"] == {"shorts": 1, "media": 50, "mediana": 50}
    assert r["agregados"]["tono"]["(sin tono)"]["shorts"] == 1
    assert r["canal"]["vistas_total"] == 57
    assert r["ultima_medida"] == "2026-11-05"
    b = next(p for p in r["publicados"] if p["slug"] == "b")
    assert b["claim"] is True and b["url"] == "https://youtube.com/shorts/b" and b["dias"] == 2
    assert [s["semana"] for s in r["canal"]["por_semana"]] == ["2026-W45"]
    assert r["canal"]["por_semana"][0] == {"semana": "2026-W45", "n": 2, "objetivo": 21}


def test_suscriptores_vacios_se_saltan(tmp_path):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,u\n",
                  "2026-11-02,a,10,1,0,,0\n2026-11-03,a,20,1,0,1500,0\n2026-11-04,a,30,1,0,,0\n")
    assert rendimiento.rendimiento(root)["canal"]["suscriptores"] == [{"fecha": "2026-11-03", "n": 1500}]


def test_slug_publicado_sin_medidas(tmp_path):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,u\n2026-11-02,b,ibai,arco,critica,1,0,1,u\n",
                  "2026-11-02,a,10,1,0,,0\n")
    r = rendimiento.rendimiento(root, hoy="2026-11-02")
    b = next(p for p in r["publicados"] if p["slug"] == "b")
    assert b["vistas"] is None and b["likes"] is None and "b" not in r["series"]
    assert r["agregados"]["tono"]["critica"]["shorts"] == 1
    assert r["canal"]["vistas_total"] == 10


def test_sin_datos(tmp_path):
    r = rendimiento.rendimiento(tmp_path)
    assert r["publicados"] == [] and r["ultima_medida"] is None and r["canal"]["vistas_total"] == 0
    assert r["series"] == {} and r["agregados"]["tono"] == {}


def test_thumb_busca_el_mp4_en_cualquier_carpeta(tmp_path):
    root = montar(tmp_path, "2026-11-05,a,ibai,arco,critica,1,0,1,u\n2026-11-05,b,ibai,arco,critica,1,0,1,u\n", "")
    (root / "out" / "2026-11-02").mkdir(parents=True)
    (root / "out" / "2026-11-02" / "a.mp4").write_bytes(b"x")
    r = rendimiento.rendimiento(root)
    assert {p["slug"]: p["thumb"] for p in r["publicados"]} == {"a": "/api/thumbs/2026-11-02/a.jpg", "b": None}


def test_resumen_por_tono_igual_que_resumen_tono():
    pub = [{"slug": "a", "tono": "critica"}, {"slug": "b", "tono": ""}]
    pil = [{"fecha_medida": "2026-11-03", "slug": "a", "vistas": "9"}, {"fecha_medida": "2026-11-03", "slug": "b", "vistas": "x"}]
    assert stats.resumen_por("tono", pub, pil) == stats.resumen_tono(pub, pil) == {"critica": {"shorts": 1, "media": 9, "mediana": 9}}


def test_rutas_rendimiento_y_estado(tmp_path):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,u\n", "2026-11-02,a,10,1,0,,0\n")
    c = TestClient(create_app(root, periodico=False))
    assert c.get("/api/rendimiento").json()["canal"]["vistas_total"] == 10
    assert c.get("/api/stats/estado").json() == {"midiendo": False, "ultima": "2026-11-02", "error": None}


# --- medidor ---

def fetch_falso(url):
    return {"vistas": 5, "likes": 1, "comentarios": 0, "suscriptores_canal": ""}


def test_medir_a_demanda_y_409_si_ya_mide(tmp_path):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,https://youtube.com/shorts/a\n", "")
    suelta, dentro = threading.Event(), threading.Event()

    def lento(url):
        dentro.set()
        suelta.wait(5)
        return fetch_falso(url)

    m = Medidor(root, fetch=lento, hoy=lambda: "2026-11-02")
    c = TestClient(create_app(root, medidor=m, periodico=False))
    with c:
        assert c.post("/api/stats/medir").status_code == 202
        assert dentro.wait(5)
        assert c.get("/api/stats/estado").json()["midiendo"] is True
        r = c.post("/api/stats/medir")
        assert r.status_code == 409 and r.json() == {"error": "ya_midiendo"}
        suelta.set()
        for _ in range(100):
            e = c.get("/api/stats/estado").json()
            if not e["midiendo"]:
                break
            threading.Event().wait(0.05)
    assert e == {"midiendo": False, "ultima": "2026-11-02", "error": None}
    assert (root / "piloto.csv").read_text().count("\n") == 2


def test_medidor_no_mide_si_hay_filas_de_hoy(tmp_path, capsys):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,u\n", "2026-11-02,a,10,1,0,,0\n")
    llamadas = []
    m = Medidor(root, fetch=lambda u: llamadas.append(u) or fetch_falso(u), hoy=lambda: "2026-11-02")
    assert asyncio.run(m.medir_si_toca()) is False
    assert llamadas == [] and "no mide: ya hay filas de hoy" in capsys.readouterr().out


def test_medidor_mide_si_no_hay_filas_de_hoy_y_no_duplica(tmp_path):
    root = montar(tmp_path, "2026-11-02,a,ibai,arco,critica,1,0,1,https://youtube.com/shorts/a\n",
                  "2026-11-01,a,3,,,,0\n")

    async def go():
        m = Medidor(root, fetch=fetch_falso, hoy=lambda: "2026-11-02")
        assert m.estado()["ultima"] == "2026-11-01"
        assert await m.medir_si_toca() is True
        await m._tarea
        assert await m.medir_si_toca() is False   # ya hay filas de hoy
        return m.estado()
    assert asyncio.run(go()) == {"midiendo": False, "ultima": "2026-11-02", "error": None}
    assert (root / "piloto.csv").read_text().count("\n") == 3


def test_medidor_error_se_guarda(tmp_path):
    m = Medidor(tmp_path, fetch=fetch_falso, hoy=lambda: "2026-11-02")   # sin publicados.csv

    async def go():
        m.iniciar()
        await m._tarea
    asyncio.run(go())
    assert m.estado()["midiendo"] is False and m.estado()["error"]
