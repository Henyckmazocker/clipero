import json
import shutil
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("ruamel.yaml")
from fastapi.testclient import TestClient  # noqa: E402

from clipero.app.server import create_app  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "config"
NUEVO = {"id": "prueba", "nombre": "Prueba", "tamaño": "mediano", "twitch": "prueba_x", "credito": ""}


@pytest.fixture
def root(tmp_path):
    shutil.copy(FIX / "sources.yaml", tmp_path / "sources.yaml")
    shutil.copy(FIX / "branding.yaml", tmp_path / "branding.yaml")
    return tmp_path


def cliente(root, flat=None):
    return TestClient(create_app(root, periodico=False, flat_playlist=flat))


def cola(root):
    t = (root / "sources.yaml").read_text()
    return t[t.index("# Reserva"):]


def ids(root):
    return [c["id"] for c in yaml.safe_load((root / "sources.yaml").read_text())]


def test_get_canales(root):
    d = cliente(root).get("/api/config/canales").json()
    assert d["activos"][0]["id"] == "ibai" and len(d["activos"]) == 10
    assert d["reserva"] == [{"id": "ampeterby7", "nombre": "Ampeterby7", "tamaño": "mediano",
                             "twitch": "ampeterby7", "credito": "Ampeterby7 (twitch.tv/ampeterby7)"}]


def test_alta_al_final_con_la_cola_intacta_y_yaml_valido(root):
    antes = cola(root)
    previos = ids(root)
    r = cliente(root).post("/api/config/canales", json=NUEVO)
    assert r.status_code == 201
    assert r.json()["credito"] == "Prueba (twitch.tv/prueba_x)"
    assert ids(root) == previos + ["prueba"]
    assert cola(root) == antes
    assert yaml.safe_load((root / "sources.yaml").read_text())[-1]["twitch"] == "prueba_x"


def test_reserva_y_reactivar(root):
    c = cliente(root)
    c.post("/api/config/canales", json=NUEVO)
    antes = cola(root)
    r = c.post("/api/config/canales/prueba/reserva")
    assert r.status_code == 200
    assert "prueba" not in ids(root)
    assert [x["id"] for x in r.json()["reserva"]] == ["prueba", "ampeterby7"]
    assert "# - id: prueba" in cola(root) and "#   twitch: prueba_x" in cola(root)
    assert cola(root).endswith(antes.split("\n", 1)[1])   # lo que había sigue debajo
    r = c.post("/api/config/canales/prueba/reactivar")
    assert r.status_code == 200 and r.json()["activos"][-1]["twitch"] == "prueba_x"
    assert ids(root)[-1] == "prueba" and cola(root) == antes
    assert c.post("/api/config/canales/prueba/reactivar").status_code == 404


def test_reserva_y_reactivar_del_ultimo_conserva_las_notas(root):
    c = cliente(root)
    antes = cola(root)
    assert c.post("/api/config/canales/gerardromero/reserva").status_code == 200
    assert "# Sustituidos el 2026-11-02" in cola(root)
    c.post("/api/config/canales/ampeterby7/reactivar")
    assert "ampeterby7" in ids(root)
    assert "# zeling se queda" in cola(root) and antes.splitlines()[-1] in cola(root)


def test_409_id_repetido_en_activos_y_en_reserva(root):
    c = cliente(root)
    for i in ("ibai", "ampeterby7"):
        r = c.post("/api/config/canales", json={**NUEVO, "id": i})
        assert r.status_code == 409 and r.json() == {"error": "id_repetido"}
    assert "prueba" not in ids(root)


def test_422_invalido_con_detalle_y_fichero_intacto(root):
    antes = (root / "sources.yaml").read_text()
    r = cliente(root).post("/api/config/canales", json={**NUEVO, "twitch": "X", "nombre": " "})
    assert r.status_code == 422 and r.json()["error"] == "invalido"
    assert any(d.startswith("twitch:") for d in r.json()["detalle"])
    assert any(d.startswith("nombre:") for d in r.json()["detalle"])
    assert (root / "sources.yaml").read_text() == antes


def test_put_ignora_el_id_del_cuerpo_y_404(root):
    c = cliente(root)
    r = c.put("/api/config/canales/elxokas", json={"id": "otro", "nombre": "El Xokas", "tamaño": "grande",
                                                    "twitch": "elxokas", "credito": "El Xokas (twitch.tv/elxokas)"})
    assert r.status_code == 200 and r.json()["id"] == "elxokas" and r.json()["nombre"] == "El Xokas"
    assert "otro" not in ids(root) and "elxokas" in ids(root)
    assert c.put("/api/config/canales/nadie", json=NUEVO).status_code == 404
    r = c.put("/api/config/canales/elxokas", json={"nombre": "X", "tamaño": "enorme", "twitch": "elxokas"})
    assert r.status_code == 422


def test_reserva_404(root):
    assert cliente(root).post("/api/config/canales/nadie/reserva").status_code == 404


def test_probar_usa_flat_playlist_inyectado(root):
    llamadas = []

    def flat(url, n=10, timeout=None):
        llamadas.append((url, n))
        if "youtube" in url:
            raise RuntimeError("yt-dlp falló")
        return [{"id": "1"}, {"id": "2"}]

    r = cliente(root, flat).post("/api/config/canales/probar", json={
        **NUEVO, "youtube": "https://www.youtube.com/@x"})
    assert r.status_code == 200
    assert r.json() == {"twitch": {"ok": True, "vods": 2, "error": None},
                        "youtube": {"ok": False, "vods": 0, "error": "yt-dlp falló"}}
    assert sorted(n for _, n in llamadas) == [3, 3]
    r = cliente(root, flat).post("/api/config/canales/probar", json={"id": "x", "nombre": "x"})
    assert r.json() == {"twitch": None, "youtube": None}


def test_marca_get_y_put_color(root):
    c = cliente(root)
    m = c.get("/api/config/marca").json()
    assert m["color"] == "#2A6FDB" and m["nombre"] == "Canal de Ejemplo" and set(m) == {
        "nombre", "handle", "lema", "color", "marca_agua", "linea_descripcion", "hashtag"}
    r = c.put("/api/config/marca", json={**m, "color": "#12ab34"})
    assert r.status_code == 200 and r.json()["color"] == "#12AB34"
    t = (root / "branding.yaml").read_text()
    assert 'color: "0x12AB34"' in t and t.startswith("# Marca del canal.")
    assert yaml.safe_load(t)["color"] == "0x12AB34"
    assert c.get("/api/marca").json()["color"] == "#12AB34"


def test_marca_422(root):
    antes = (root / "branding.yaml").read_text()
    c = cliente(root)
    m = c.get("/api/config/marca").json()
    r = c.put("/api/config/marca", json={**m, "color": "rojo", "hashtag": "sin almohadilla"})
    assert r.status_code == 422 and r.json()["error"] == "invalido" and len(r.json()["detalle"]) == 2
    assert (root / "branding.yaml").read_text() == antes


def test_probar_responde_en_el_timeout_aunque_yt_dlp_tarde(root, monkeypatch):
    from clipero.app import server
    monkeypatch.setattr(server, "PRUEBA_TIMEOUT", 0.3)

    def lento(url, n=10, timeout=None):
        time.sleep(3)
        return [{"id": "1"}]

    t0 = time.monotonic()
    r = cliente(root, lento).post("/api/config/canales/probar", json=NUEVO)
    assert time.monotonic() - t0 < 2
    assert r.json()["twitch"]["ok"] is False and "Sin respuesta" in r.json()["twitch"]["error"]


def test_tanda_config_get_put_y_defaults(root):
    c = cliente(root)
    base = c.get("/api/config/tanda").json()
    assert base["clips"] == 5 and base["modelos"] == ["claude-opus-5-5", "sonnet", "haiku"]
    r = c.put("/api/config/tanda", json={**base, "clips": 3, "modelo": "sonnet"})
    assert r.status_code == 200 and r.json()["clips"] == 3 and r.json()["modelo"] == "sonnet"
    t = (root / "app.yaml").read_text()
    assert t.startswith("# Valores por defecto") and "# 1-10, máximo por tanda" in t
    d = c.get("/api/tandas/defaults").json()
    assert d["clips"] == 3 and d["modelo"] == "sonnet"


def test_tanda_config_422_y_validacion_de_modelo_desde_app_yaml(root):
    c = cliente(root)
    base = c.get("/api/config/tanda").json()
    r = c.put("/api/config/tanda", json={**base, "clips": 50, "modelo": "gpt"})
    assert r.status_code == 422 and r.json()["error"] == "invalido" and len(r.json()["detalle"]) == 2
    assert not (root / "app.yaml").exists()
    c.put("/api/config/tanda", json={**base, "modelos": ["solo"], "modelo": "solo"})
    r = c.post("/api/tandas", json={"clips": 1, "editorial": "mixta", "modelo": "sonnet"})
    assert r.status_code == 422 and any("modelo" in e for e in r.json()["detalle"])


# --- Claude: modos y API key ------------------------------------------------------------

CLAVE = "sk-ant-api03-SECRETA-1234567890"


@pytest.fixture
def sin_entorno(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("clipero.config.shutil.which", lambda n: "/usr/bin/claude" if n == "claude" else None)


def test_claude_get_por_defecto_sin_clave_en_app_yaml(root, sin_entorno):
    r = cliente(root).get("/api/config/claude")   # sin app.yaml: app.yaml viejo/ausente → ninguno
    assert r.status_code == 200
    assert r.json() == {"modo": "ninguno", "disponibles": {"api_key": False, "suscripcion": True},
                        "clave": {"puesta": False, "origen": None}, "claude_cli": "/usr/bin/claude"}


def test_claude_put_errores(root, sin_entorno):
    c = cliente(root)
    assert c.put("/api/config/claude", json={"modo": "gpt"}).status_code == 400
    assert c.put("/api/config/claude", json={"modo": "api_key"}).status_code == 409   # sin clave
    assert not (root / "app.yaml").exists()


def test_claude_put_api_key_no_filtra_la_clave_y_el_fichero_es_0600(root, sin_entorno):
    c = cliente(root)
    r = c.put("/api/config/claude", json={"modo": "api_key", "api_key": CLAVE})
    assert r.status_code == 200
    assert r.json()["modo"] == "api_key" and r.json()["clave"] == {"puesta": True, "origen": "fichero"}
    assert CLAVE not in r.text and CLAVE not in c.get("/api/config/claude").text
    assert CLAVE[:10] not in c.get("/api/config/claude").text
    f = root / ".clipero" / "credenciales"
    assert (f.stat().st_mode & 0o777) == 0o600
    assert json.loads(f.read_text())["anthropic_api_key"] == CLAVE
    assert not list(f.parent.glob("*.tmp"))
    assert "modo: api_key" in (root / "app.yaml").read_text()


def test_claude_entorno_manda_sobre_fichero(root, sin_entorno, monkeypatch):
    c = cliente(root)
    c.put("/api/config/claude", json={"modo": "ninguno", "api_key": CLAVE})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-entorno")
    r = c.get("/api/config/claude")
    assert r.json()["clave"] == {"puesta": True, "origen": "entorno"} and "sk-ant-entorno" not in r.text
    from clipero import config
    assert config.api_key(root) == "sk-ant-entorno"


def test_claude_api_key_vacia_la_borra(root, sin_entorno):
    c = cliente(root)
    c.put("/api/config/claude", json={"modo": "api_key", "api_key": CLAVE})
    r = c.put("/api/config/claude", json={"modo": "ninguno", "api_key": ""})
    assert r.status_code == 200 and r.json()["clave"] == {"puesta": False, "origen": None}
    assert not (root / ".clipero" / "credenciales").exists()


def test_claude_suscripcion_sin_claude_en_el_path_es_409(root, sin_entorno, monkeypatch):
    monkeypatch.setattr("clipero.config.shutil.which", lambda n: None)
    c = cliente(root)
    assert c.get("/api/config/claude").json()["disponibles"]["suscripcion"] is False
    assert c.put("/api/config/claude", json={"modo": "suscripcion"}).status_code == 409


def test_claude_put_conserva_el_bloque_tanda_y_los_comentarios(root, sin_entorno):
    c = cliente(root)
    c.put("/api/config/tanda", json={**c.get("/api/config/tanda").json(), "clips": 4})
    viejo = (root / "app.yaml").read_text().replace(
        "claude:\n  modo: ninguno     # ninguno | api_key | suscripcion (Configuración › Claude)\n", "")
    (root / "app.yaml").write_text(viejo)   # un app.yaml de antes del M3, sin `claude`
    assert "claude:" not in viejo
    r = c.put("/api/config/claude", json={"modo": "suscripcion"})
    assert r.status_code == 200 and r.json()["modo"] == "suscripcion"
    despues = (root / "app.yaml").read_text()
    assert "modo: suscripcion" in despues and "# 1-10, máximo por tanda" in despues
    assert c.get("/api/config/tanda").json()["clips"] == 4
    assert "modo" not in c.get("/api/config/tanda").json()
    assert yaml.safe_load(despues)["claude"] == {"modo": "suscripcion"}
    # y guardar la tanda después no pierde el modo
    c.put("/api/config/tanda", json={**c.get("/api/config/tanda").json(), "clips": 2})
    assert yaml.safe_load((root / "app.yaml").read_text())["claude"] == {"modo": "suscripcion"}


def test_claude_put_409_con_sesion_en_curso(root, sin_entorno):
    from clipero.app import sesiones as ses
    S = ses.Sesiones(root, lambda r: None, lambda t: None)
    S._run = {"id": "x", "estado": "en_curso"}
    c = TestClient(create_app(root, periodico=False, sesiones=S))
    r = c.put("/api/config/claude", json={"modo": "suscripcion"})
    assert r.status_code == 409 and r.json()["error"] == "ocupado"


def test_post_tandas_con_ninguno_da_409(root, sin_entorno):
    r = cliente(root).post("/api/tandas", json={"fuentes": [], "clips": 1, "editorial": "mixta", "modelo": "sonnet"})
    assert r.status_code == 409
    assert r.json() == {"detail": "Claude desactivado: elige un modo en Configuración › Claude"}


def test_modo_claude_de_config_y_de_doctor_coinciden(root, sin_entorno):
    from clipero import config, herramientas, rutas
    cliente(root).put("/api/config/claude", json={"modo": "suscripcion"})
    rutas.fijar(root)
    try:
        assert config.modo_claude(root) == herramientas._modo_claude() == "suscripcion"
    finally:
        rutas.fijar(None)
    (root / "app.yaml").write_text("tanda: {clips: 5}\n")   # app.yaml viejo, sin `claude`
    assert config.modo_claude(root) == "ninguno"
    (root / "app.yaml").write_text("claude: {modo: raro}\n")
    assert config.modo_claude(root) == "ninguno"
