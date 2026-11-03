import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from clipero.app.server import create_app  # noqa: E402


@pytest.fixture
def root(tmp_path):
    (tmp_path / "out" / "2026-11-02").mkdir(parents=True)
    (tmp_path / "out" / "2026-11-02" / "a-b.mp4").write_bytes(bytes(range(256)) * 8)
    (tmp_path / "secreto.mp4").write_bytes(b"no")
    (tmp_path / "sources.yaml").write_text(
        "- id: ibai\n  nombre: Ibai\n  tamaño: grande\n  twitch: ibai\n"
        "- id: elxokas\n  nombre: elxokas\n  twitch: elxokas\n")
    (tmp_path / "branding.yaml").write_text('nombre: "Mi Canal"\ncolor: "0x2A6FDB"\n')
    return tmp_path


@pytest.fixture
def client(root):
    return TestClient(create_app(root))


def test_salud(client):
    r = client.get("/api/salud")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_fuentes(client):
    assert client.get("/api/fuentes").json() == [
        {"id": "ibai", "nombre": "Ibai"}, {"id": "elxokas", "nombre": "elxokas"}]


def test_fuentes_sin_fichero(tmp_path):
    assert TestClient(create_app(tmp_path)).get("/api/fuentes").json() == []


def test_marca(client):
    assert client.get("/api/marca").json() == {"nombre": "Mi Canal", "color": "#2A6FDB"}


def test_media_completo_y_206_con_range(client):
    r = client.get("/media/out/2026-11-02/a-b.mp4")
    assert r.status_code == 200 and len(r.content) == 2048
    r = client.get("/media/out/2026-11-02/a-b.mp4", headers={"Range": "bytes=0-999"})
    assert r.status_code == 206
    assert len(r.content) == 1000
    assert r.headers["content-range"] == "bytes 0-999/2048"


@pytest.mark.parametrize("ruta", [
    "/media/out/2026-11-02/no-existe.mp4",
    "/media/out/2026-11-03/a-b.mp4",
    "/media/out/2026-11-02/..%2F..%2Fsecreto.mp4",
    "/media/out/..%2F/secreto.mp4",
    "/media/out/2026-11-02/A-B.mp4",
    "/media/out/%2e%2e/%2e%2e/secreto.mp4",
    "/media/secreto.mp4",
])
def test_media_fuera_de_out_404(client, ruta):
    assert client.get(ruta).status_code == 404


def test_api_desconocida_es_404_json(client):
    r = client.get("/api/noexiste")
    assert r.status_code == 404 and r.json() == {"error": "no_encontrado"}


def test_sin_dist_arranca(root, monkeypatch):
    from clipero import rutas
    monkeypatch.setattr(rutas, "PKG", root / "pkg")   # sin app/static
    client = TestClient(create_app(root))
    assert client.get("/clips").status_code == 404


def test_estaticos_y_fallback_del_router(root, monkeypatch):
    from clipero import rutas
    monkeypatch.setattr(rutas, "PKG", root / "pkg")   # los estáticos salen de PKG/app/static
    dist = root / "pkg" / "app" / "static"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "x.js").write_text("1")
    c = TestClient(create_app(root))
    assert c.get("/clips").text == "<html>app</html>"
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/assets/x.js").text == "1"
    assert c.get("/api/noexiste").status_code == 404
    assert c.get("/media/otra").status_code == 404
    assert c.get("/..%2F..%2Fsecreto.mp4").text == "<html>app</html>"


# --- tandas, runs y retoque (con Sesiones falsas: no se arranca el SDK ni notify-send) ---

from clipero.app import sesiones as _ses  # noqa: E402


class _Quieto:
    def __init__(self, root):
        pass

    async def correr(self, prompt, modelo, al_evento):
        return {"estado": "ok", "coste_usd": None, "error": None, "session_id": None}

    async def detener(self):
        pass


@pytest.fixture(autouse=True)
def _claude_listo(monkeypatch):
    """Estos tests no miran el modo de Claude: se da por elegido api_key con una clave de prueba."""
    from clipero import config
    monkeypatch.setattr(config, "modo_claude", lambda root: "api_key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")


def _cli(root, **kw):
    s = _ses.Sesiones(root, _Quieto, lambda t: None)
    return TestClient(create_app(root, sesiones=s, periodico=False, **kw)), s


TANDA = {"fuentes": ["ibai"], "clips": 3, "editorial": "positiva", "dias": 5, "modelo": "sonnet"}


def test_tandas_defaults(root):
    c, _ = _cli(root)
    assert c.get("/api/tandas/defaults").json() == {
        "clips": 5, "dias": 7, "editorial": "mixta", "modelo": "claude-opus-5-5",
        "modelos": ["claude-opus-5-5", "sonnet", "haiku"]}


@pytest.mark.parametrize("cambio", [
    {"clips": 0}, {"clips": 11}, {"dias": 0}, {"dias": 31}, {"modelo": "gpt"}, {"nota": "x" * 1001},
    {"fuentes": ["nadie"]}, {"vod_url": "https://x/1"}, {"vod_url": "ftp://x", "fuentes": []},
    {"editorial": "rara"}, {"clips": "muchos"}])
def test_tandas_422_invalido(root, cambio):
    c, s = _cli(root)
    r = c.post("/api/tandas", json={**TANDA, **cambio})
    assert r.status_code == 422 and r.json()["error"] == "invalido"
    assert r.json()["detalle"] and all(isinstance(d, str) for d in r.json()["detalle"])
    assert not s.ocupado()


def test_tandas_422_junta_todos_los_errores(root):
    c, s = _cli(root)
    r = c.post("/api/tandas", json={"clips": 50, "editorial": "rara", "modelo": "gpt", "fuentes": ["x"]})
    assert r.status_code == 422 and r.json()["error"] == "invalido"
    d = " | ".join(r.json()["detalle"])
    for trozo in ("clips: de 1 a 10", "editorial", "modelo: «gpt»", "«x» no es un canal activo"):
        assert trozo in d, d
    r = c.post("/api/tandas", json={"clips": "mucho", "dias": 99})
    d = " | ".join(r.json()["detalle"])
    assert "clips" in d and "dias: de 1 a 30" in d and "editorial" in d and "modelo" in d
    assert c.post("/api/tandas", json=[1]).status_code == 422
    assert not s.ocupado()


def test_tandas_422_rangos_con_tipos_laxos(root):
    c, s = _cli(root)
    base = {"editorial": "mixta", "modelo": "sonnet"}
    r = c.post("/api/tandas", json={**base, "clips": "50"})
    assert r.status_code == 422 and "clips: de 1 a 10" in r.json()["detalle"]
    r = c.post("/api/tandas", json={**base, "clips": 50.0, "dias": "99"})
    assert r.status_code == 422
    assert {"clips: de 1 a 10", "dias: de 1 a 30"} <= set(r.json()["detalle"])
    r = c.post("/api/tandas", json={"clips": "50", "editorial": "rara", "modelo": "sonnet"})
    assert "clips: de 1 a 10" in r.json()["detalle"] and len(r.json()["detalle"]) == 2
    assert not s.ocupado()


def test_tandas_422_falta_campo(root):
    c, _ = _cli(root)
    r = c.post("/api/tandas", json={"clips": 1})
    assert r.status_code == 422 and r.json()["error"] == "invalido"


def test_tandas_202_normaliza_params(root):
    c, s = _cli(root)
    with c:
        r = c.post("/api/tandas", json=TANDA)
        assert r.status_code == 202 and r.json()["canal_creado"] is None
        run = c.get(f"/api/runs/{r.json()['id']}").json()["run"]
    assert run["params"] == {"fuentes": ["ibai"], "vod_url": None, "clips": 3, "editorial": "positiva",
                             "dias": 5, "modelo": "sonnet", "nota": ""}


def test_tandas_vod_conocido_no_da_de_alta(root):
    info = {"uploader_id": "ibai", "uploader": "Ibai", "extractor_key": "TwitchVod"}
    c, s = _cli(root, vod_info=lambda url: info)
    antes = (root / "sources.yaml").read_text()
    with c:
        r = c.post("/api/tandas", json={"clips": 1, "editorial": "mixta", "modelo": "haiku",
                                        "vod_url": "https://www.twitch.tv/videos/1"})
        assert r.status_code == 202 and r.json()["canal_creado"] is None
        assert c.get(f"/api/runs/{r.json()['id']}").json()["run"]["params"]["vod_url"].endswith("/videos/1")
    assert (root / "sources.yaml").read_text() == antes


def test_tandas_vod_desconocido_da_de_alta_canal(root):
    info = {"uploader_id": "NuevoCanal", "uploader": "Nuevo Canal", "extractor_key": "TwitchVod"}
    (root / "sources.yaml").write_text(
        '- id: ibai\n  nombre: Ibai\n  tamaño: grande\n  twitch: ibai\n  credito: "Ibai (twitch.tv/ibai)"\n')
    c, _ = _cli(root, vod_info=lambda url: info)
    with c:
        r = c.post("/api/tandas", json={"clips": 1, "editorial": "mixta", "modelo": "haiku",
                                        "vod_url": "https://www.twitch.tv/videos/2"})
    assert r.status_code == 202, r.json()
    cc = r.json()["canal_creado"]
    assert cc["id"] == "nuevocanal" and cc["nombre"] == "Nuevo Canal" and cc["credito"]
    texto = (root / "sources.yaml").read_text()
    assert "nuevocanal" in texto and "id: ibai" in texto
    assert [f["id"] for f in c.get("/api/fuentes").json()] == ["ibai", "nuevocanal"]


def test_tandas_vod_invalido_y_canal_no_creable(root):
    def falla(url):
        raise RuntimeError("yt-dlp -j falló: 404")
    c, s = _cli(root, vod_info=falla)
    body = {"clips": 1, "editorial": "mixta", "modelo": "haiku", "vod_url": "https://www.twitch.tv/videos/3"}
    r = c.post("/api/tandas", json=body)
    assert r.status_code == 422 and r.json() == {"error": "vod_invalido", "detalle": "yt-dlp -j falló: 404"}
    c, s = _cli(root, vod_info=lambda u: {"uploader_id": "UCabc", "extractor_key": "Youtube"})
    antes = (root / "sources.yaml").read_text()
    r = c.post("/api/tandas", json=body)
    assert r.status_code == 422 and r.json()["error"] == "canal_no_creable" and r.json()["detalle"]
    assert (root / "sources.yaml").read_text() == antes and not s.ocupado()


def test_runs_vacios_y_404(root):
    c, _ = _cli(root)
    assert c.get("/api/runs").json() == []
    assert c.get("/api/runs/actual").json() is None
    assert c.get("/api/runs/20200101-000000-tanda").status_code == 404
    assert c.get("/api/runs/..%2Fx").status_code == 404
    assert c.post("/api/runs/20200101-000000-tanda/detener").status_code == 404


def test_retoque_endpoint(root):
    (root / "out/2026-11-02/a-b.short.yaml").write_text("slug: a-b\n")
    c, s = _cli(root)
    with c:
        assert c.post("/api/clips/2026-11-02/nada/retoque", json={"peticion": "x"}).status_code == 404
        r = c.post("/api/clips/2026-11-02/a-b/retoque", json={"peticion": " "})
        assert r.status_code == 422 and r.json()["error"] == "invalido"
        r = c.post("/api/clips/2026-11-02/a-b/retoque", json={"peticion": "x", "modelo": "gpt"})
        assert r.status_code == 422
        r = c.post("/api/clips/2026-11-02/a-b/retoque", json={"peticion": "gancho más agresivo"})
        assert r.status_code == 202 and r.json()["destino"] == "a-b-v2"


def test_retoque_sin_yaml_y_publicado(root):
    c, _ = _cli(root)
    r = c.post("/api/clips/2026-11-02/a-b/retoque", json={"peticion": "x"})
    assert r.status_code == 422 and r.json() == {"error": "sin_yaml"}
    (root / "out/2026-11-02/a-b.short.yaml").write_text("slug: a-b\n")
    (root / "publicados.csv").write_text(
        "fecha,slug,fuente,formato,tono,vod_id,start,end,url\n"
        "2026-11-02,a-b,ibai,corto,neutro,1,0,10,https://www.youtube.com/shorts/abc\n")
    r = c.post("/api/clips/2026-11-02/a-b/retoque", json={"peticion": "x"})
    assert r.status_code == 409 and r.json() == {"error": "publicado"}


def test_medir_409_con_tanda_en_curso(root):
    c, s = _cli(root)
    s._run = {"id": "20261102-100000-tanda", "estado": "en_curso"}
    r = c.post("/api/stats/medir")
    assert r.status_code == 409 and r.json() == {"error": "tanda_en_curso"}


def test_medidor_no_mide_con_sesion(root):
    import asyncio

    from clipero.app.medidor import Medidor
    m = Medidor(root, hoy=lambda: "2026-11-02", ocupado=lambda: True)
    assert asyncio.run(m.medir_si_toca()) is False and not m.midiendo


def test_lifespan_marca_interrumpidas(root):
    d = root / "data" / "runs" / "20261101-100000-tanda"
    d.mkdir(parents=True)
    (d / "run.json").write_text('{"id": "20261101-100000-tanda", "estado": "en_curso", "creado": "2026-11-01T10:00:00"}')
    c, _ = _cli(root)
    with c:
        assert c.get("/api/runs").json()[0]["estado"] == "interrumpida"
