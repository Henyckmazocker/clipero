import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from clipero import config  # noqa: E402
from clipero.app import sesiones as ses  # noqa: E402
from clipero.app.publicar import Fallo  # noqa: E402
from clipero.app.server import create_app  # noqa: E402


class LanzadorFalso:
    """Emite eventos guionizados; `espera` deja el run en curso hasta que `detener()` o `soltar()`."""
    guion: list = []
    espera = False
    resultado = {"estado": "ok", "coste_usd": 0.5, "error": None, "session_id": "s1"}
    ultimo = None

    def __init__(self, root):
        self.root = root
        self._ev = asyncio.Event()
        LanzadorFalso.ultimo = self

    async def correr(self, prompt, modelo, al_evento):
        self.prompt, self.modelo = prompt, modelo
        al_evento({"tipo": "init", "session_id": "s1"})
        for ev in self.guion:
            al_evento(dict(ev))
        if self.espera:
            await self._ev.wait()
        return dict(self.resultado)

    async def detener(self):
        self._ev.set()

    def soltar(self):
        self._ev.set()


def bash(cmd):
    return {"tipo": "herramienta", "nombre": "Bash", "resumen": cmd}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    LanzadorFalso.guion, LanzadorFalso.espera = [], False
    # los tests de gestor no dependen del app.yaml: modo api_key con clave de prueba
    monkeypatch.setattr(config, "modo_claude", lambda root: "api_key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    yield


@pytest.fixture
def notas():
    return []


@pytest.fixture
def S(tmp_path, notas):
    return ses.Sesiones(tmp_path, LanzadorFalso, notas.append)


PARAMS = {"fuentes": ["ibai"], "vod_url": None, "clips": 2, "editorial": "mixta", "dias": 3,
          "modelo": "sonnet", "nota": ""}


async def acabar(S):
    await asyncio.wait_for(S._tarea, 5)


def tipos(S, id):
    return [e["tipo"] for e in S.leer(id, 0)["eventos"]]


def test_fases_en_orden_y_solo_avanzan(S, notas):
    async def go():
        LanzadorFalso.guion = [
            bash("clipero stats"), bash("clipero vods --dias 3"),
            bash("cd ~/Clipero && clipero ingest https://x/1"), bash(".venv/bin/clipero candidates 1"),
            bash("clipero transcribe 1"),
            {"tipo": "herramienta", "nombre": "Write", "resumen": "/r/out/2026-11-02/a.short.yaml"},
            bash(".venv/bin/clipero render out/2026-11-02/a.short.yaml"),
            bash(".venv/bin/clipero transcribe 1 2"),   # alterna: manda la última vista
            bash(".venv/bin/clipero vods"),             # retrocede fuera del trío: se ignora
            bash(".venv/bin/clipero clean"),
        ]
        id = S.lanzar_tanda(dict(PARAMS))
        await acabar(S)
        return id
    id = asyncio.run(go())
    r = S.leer(id, 0)
    fases = [e["fase"] for e in r["eventos"] if e["tipo"] == "fase"]
    assert fases == ["metricas", "vods", "ingesta", "transcripcion", "guion", "render", "transcripcion", "limpieza"]
    assert [e["i"] for e in r["eventos"]] == list(range(len(r["eventos"])))
    assert r["eventos"][-1] == {**r["eventos"][-1], "tipo": "fin", "estado": "ok"}
    assert r["run"]["estado"] == "ok" and r["run"]["session_id"] == "s1"
    assert r["run"]["eventos"] == r["siguiente"] == len(r["eventos"])
    assert r["run"]["resultado"]["coste_usd"] == 0.5
    assert notas == ["Tanda terminada: 0 shorts"]
    assert S.leer(id, 3)["eventos"][0]["i"] == 3


def test_409_con_sesion_en_curso_y_detener(S, notas):
    async def go():
        LanzadorFalso.espera = True
        id = S.lanzar_tanda(dict(PARAMS))
        assert S.ocupado() and S.actual()["id"] == id
        with pytest.raises(Fallo) as e:
            S.lanzar_tanda(dict(PARAMS))
        assert (e.value.status, e.value.codigo) == (409, "ocupado")
        await S.detener(id)
        await acabar(S)
        with pytest.raises(Fallo) as e:
            await S.detener(id)
        assert e.value.status == 409 and e.value.codigo == "no_en_curso"
        with pytest.raises(Fallo) as e:
            await S.detener("20200101-000000-tanda")
        assert e.value.status == 404
        return id
    id = asyncio.run(go())
    r = S.leer(id, 0)
    assert r["run"]["estado"] == "detenida" and r["eventos"][-1]["tipo"] == "fin"
    assert r["eventos"][-1]["estado"] == "detenida" and not S.ocupado() and notas == []


def test_detenida_aunque_el_resultado_sea_error(S):
    async def go():
        LanzadorFalso.espera = True
        LanzadorFalso.resultado = {"estado": "error", "error": "error_during_execution"}
        try:
            id = S.lanzar_tanda(dict(PARAMS))
            await S.detener(id)
            await acabar(S)
        finally:
            LanzadorFalso.resultado = {"estado": "ok", "coste_usd": 0.5, "error": None, "session_id": "s1"}
        return id
    assert S.leer(asyncio.run(go()), 0)["run"]["estado"] == "detenida"


def test_error_y_excepcion(S, notas):
    S.gracia = 0

    async def go():
        LanzadorFalso.resultado = {"estado": "error", "error": "boom"}
        try:
            id = S.lanzar_tanda(dict(PARAMS))
            await acabar(S)
        finally:
            LanzadorFalso.resultado = {"estado": "ok", "coste_usd": 0.5, "error": None, "session_id": "s1"}
        return id
    r = S.leer(asyncio.run(go()), 0)["run"]
    assert r["estado"] == "error" and r["resultado"]["error"] == "boom"
    assert notas == ["Tanda con error: boom"]


def test_marcar_interrumpidas(tmp_path):
    d = tmp_path / "data" / "runs" / "20261101-100000-tanda"
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"id": d.name, "tipo": "tanda", "estado": "en_curso",
                                            "creado": "2026-11-01T10:00:00", "terminado": None, "eventos": 1}))
    (d / "eventos.jsonl").write_text(json.dumps({"i": 0, "t": "10:00:01", "tipo": "texto", "texto": "x"}) + "\n")
    otro = tmp_path / "data" / "runs" / "20261031-100000-tanda"
    otro.mkdir()
    (otro / "run.json").write_text(json.dumps({"id": otro.name, "estado": "ok", "creado": "2026-10-31T10:00:00"}))
    S = ses.Sesiones(tmp_path, LanzadorFalso, lambda t: None)
    assert S.marcar_interrumpidas() == 1 and S.marcar_interrumpidas() == 0
    r = S.leer(d.name, 0)
    assert r["run"]["estado"] == "interrumpida" and r["run"]["terminado"]
    assert r["eventos"][-1]["tipo"] == "fin" and r["eventos"][-1]["i"] == 1
    assert S.leer(otro.name, 0)["run"]["estado"] == "ok"
    assert [x["id"] for x in S.listar()] == [d.name, otro.name]


def _clip(root, fecha, nombre):
    c = root / "out" / fecha
    c.mkdir(parents=True, exist_ok=True)
    (c / f"{nombre}.mp4").write_bytes(b"x")
    (c / f"{nombre}.short.yaml").write_text("slug: x\n")


def test_destino_v2_v3(S, tmp_path):
    _clip(tmp_path, "2026-11-02", "ibai-x")
    assert S.destino("2026-11-02", "ibai-x") == "ibai-x-v2"
    _clip(tmp_path, "2026-11-02", "ibai-x-v2")
    assert S.destino("2026-11-02", "ibai-x") == "ibai-x-v3"
    assert S.destino("2026-11-02", "ibai-x-v2") == "ibai-x-v3"
    _clip(tmp_path, "2026-11-02", "ibai-xy")   # otra base: no cuenta
    assert S.destino("2026-11-02", "ibai-xy") == "ibai-xy-v2"


def test_retoque_validaciones_y_prompt(S, tmp_path):
    async def go():
        with pytest.raises(Fallo) as e:
            S.lanzar_retoque("2026-11-02", "nada", "x", "sonnet")
        assert e.value.status == 404
        _clip(tmp_path, "2026-11-02", "ibai-x")
        with pytest.raises(Fallo) as e:
            S.lanzar_retoque("2026-11-02", "ibai-x", "  ", "sonnet")
        assert (e.value.status, e.value.codigo) == (422, "invalido")
        (tmp_path / "out/2026-11-02/ibai-x.short.yaml").rename(tmp_path / "out/2026-11-02/z.txt")
        with pytest.raises(Fallo) as e:
            S.lanzar_retoque("2026-11-02", "ibai-x", "algo", "sonnet")
        assert e.value.codigo == "sin_yaml"
        (tmp_path / "out/2026-11-02/z.txt").rename(tmp_path / "out/2026-11-02/ibai-x.short.yaml")
        (tmp_path / "publicados.csv").write_text(
            "fecha,slug,fuente,formato,tono,vod_id,start,end,url\n"
            "2026-11-02,ibai-x,ibai,corto,neutro,1,0,10,https://www.youtube.com/shorts/abc\n")
        with pytest.raises(Fallo) as e:
            S.lanzar_retoque("2026-11-02", "ibai-x", "algo", "sonnet")
        assert (e.value.status, e.value.codigo) == (409, "publicado")
        (tmp_path / "publicados.csv").unlink()
        id, destino = S.lanzar_retoque("2026-11-02", "ibai-x", " quita el segundo tramo ", "haiku")
        await acabar(S)
        return id, destino
    id, destino = asyncio.run(go())
    assert destino == "ibai-x-v2"
    assert LanzadorFalso.ultimo.modelo == "haiku"
    assert LanzadorFalso.ultimo.prompt == (
        "Usa la sección «Retoque» de la skill `tanda`. Te lanza la app: no preguntes nada.\n"
        "Origen: out/2026-11-02/ibai-x.short.yaml\n"
        "Destino: out/2026-11-02/ibai-x-v2.short.yaml (slug: ibai-x-v2)\n"
        "Petición del usuario: «quita el segundo tramo»")
    run = S.leer(id, 0)["run"]
    assert run["tipo"] == "retoque" and run["params"]["destino"] == "ibai-x-v2"


def test_retoque_solo_enseña_sus_fases(S, tmp_path):
    async def go():
        _clip(tmp_path, "2026-11-02", "ibai-x")
        LanzadorFalso.guion = [bash(".venv/bin/clipero vods"), bash(".venv/bin/clipero transcribe 1 2"),
                               bash(".venv/bin/clipero render out/x")]
        id, _ = S.lanzar_retoque("2026-11-02", "ibai-x", "algo", "sonnet")
        await acabar(S)
        return id
    fases = [e["fase"] for e in S.leer(asyncio.run(go()), 0)["eventos"] if e["tipo"] == "fase"]
    assert fases == ["transcripcion", "render"]


def test_resultado_shorts_por_mtime(S, tmp_path, notas):
    ahora = datetime(2026, 11, 2, 18, 30, 12)
    S.ahora = lambda: ahora
    _clip(tmp_path, "2026-11-02", "viejo")
    _clip(tmp_path, "2026-11-02", "nuevo")
    _clip(tmp_path, "2026-11-01", "otro")
    t0 = ahora.timestamp()
    for f, dt in (("2026-11-02/viejo", -3600), ("2026-11-02/nuevo", 60), ("2026-11-01/otro", 5)):
        os.utime(tmp_path / "out" / f"{f}.mp4", (t0 + dt, t0 + dt))

    async def go():
        id = S.lanzar_tanda(dict(PARAMS))
        assert id == "20261102-183012-tanda"
        await acabar(S)
        return id
    run = S.leer(asyncio.run(go()), 0)["run"]
    assert run["resultado"]["shorts"] == [{"fecha": "2026-11-01", "slug": "otro"},
                                          {"fecha": "2026-11-02", "slug": "nuevo"}]
    assert notas == ["Tanda terminada: 2 shorts"]


def test_listar_quita_nota_y_ordena(S):
    async def go():
        ids = []
        for i in range(3):
            S.ahora = lambda i=i: datetime(2026, 11, 2, 10, 0, i)
            ids.append(S.lanzar_tanda({**PARAMS, "nota": "secreta"}))
            await acabar(S)
        return ids
    ids = asyncio.run(go())
    lista = S.listar()
    assert [r["id"] for r in lista] == ids[::-1]
    assert all("nota" not in r["params"] for r in lista)
    assert len(S.listar(2)) == 2
    assert S.leer(ids[0], 0)["run"]["params"]["nota"] == "secreta"


def test_prompt_tanda():
    p = ses.prompt_tanda({**PARAMS, "fuentes": ["ibai", "elxokas"], "nota": "sin política"})
    assert "fuentes: ibai, elxokas\nvod: —\nclips_max: 2\neditorial: mixta\ndias: 3\nnota: «sin política»" in p
    p = ses.prompt_tanda({**PARAMS, "fuentes": [], "vod_url": "https://t/1"})
    assert "fuentes: todas\nvod: https://t/1\n" in p and "nota: —" in p


def test_resumen_y_salida_recortados():
    assert len(ses.resumen_herramienta("Bash", {"command": "x" * 900})) == 300
    assert ses.resumen_herramienta("Grep", {"pattern": "p"}) == "p"
    assert ses.resumen_herramienta("Otra", {"a": 1}) == ""
    assert ses._texto_salida("a" * 5000) == "a" * 2000
    assert ses._texto_salida([{"type": "text", "text": "hola"}]) == "hola"


def test_canal_desde_info_twitch():
    c = ses.canal_desde_info({"uploader_id": "Nuevo_Streamer", "uploader": "Nuevo Streamer",
                              "extractor_key": "TwitchVod"})
    assert c == {"id": "nuevo-streamer", "nombre": "Nuevo Streamer", "tamaño": "mediano",
                 "twitch": "nuevo_streamer", "youtube": None, "credito": None}


def test_canal_desde_info_youtube_y_repetido():
    info = {"uploader_id": "@Canal.X", "uploader": "Canal X", "extractor_key": "Youtube"}
    c = ses.canal_desde_info(info)
    assert c["id"] == "canal-x" and c["twitch"] is None
    assert c["youtube"] == "https://www.youtube.com/@Canal.X"
    assert ses.canal_desde_info(info, {"canal-x"})["id"] == "canal-x-2"
    assert ses.canal_desde_info(info, {"canal-x", "canal-x-2"})["id"] == "canal-x-3"
    sin = ses.canal_desde_info({"uploader_id": "UCabc", "extractor_key": "Youtube"})
    assert sin["youtube"] is None and sin["nombre"] == "UCabc"


def test_cerrar_detiene_la_sesion(S):
    async def go():
        LanzadorFalso.espera = True
        id = S.lanzar_tanda(dict(PARAMS))
        await S.cerrar()
        return id
    r = S.leer(asyncio.run(go()), 0)
    assert r["run"]["estado"] == "interrumpida" and r["eventos"][-1]["estado"] == "interrumpida"


def test_cerrar_con_lanzador_que_falla_es_interrumpida_sin_notificar(S, notas):
    class Roto(LanzadorFalso):
        async def correr(self, prompt, modelo, al_evento):
            await self._ev.wait()
            raise RuntimeError("ProcessError: claude murió")

        async def detener(self):
            self._ev.set()
            raise RuntimeError("proceso ya muerto")

    async def go():
        S.lanzador_factory = Roto
        id = S.lanzar_tanda(dict(PARAMS))
        await S.cerrar()
        return id
    run = S.leer(asyncio.run(go()), 0)["run"]
    assert run["estado"] == "interrumpida" and notas == []


def test_fallo_antes_del_cierre_espera_la_gracia(S, notas):
    class Roto(LanzadorFalso):
        async def correr(self, prompt, modelo, al_evento):
            raise RuntimeError("ProcessError: SIGTERM")

    async def go():
        S.lanzador_factory = Roto
        S.gracia = 0.3
        id = S.lanzar_tanda(dict(PARAMS))
        await asyncio.sleep(0.05)
        await S.cerrar()    # llega después del fallo, dentro de la gracia
        return id
    run = S.leer(asyncio.run(go()), 0)["run"]
    assert run["estado"] == "interrumpida" and notas == []


def test_servidor_con_falso_de_extremo_a_extremo(tmp_path, notas):
    (tmp_path / "sources.yaml").write_text("- id: ibai\n  nombre: Ibai\n  twitch: ibai\n")
    S = ses.Sesiones(tmp_path, LanzadorFalso, notas.append)
    S.gracia = 0
    LanzadorFalso.espera = True
    LanzadorFalso.guion = [bash(".venv/bin/clipero stats"), bash(".venv/bin/clipero vods --dias 2")]
    body = {"fuentes": ["ibai"], "clips": 1, "editorial": "mixta", "dias": 2, "modelo": "claude-opus-5-5"}
    with TestClient(create_app(tmp_path, sesiones=S, periodico=False)) as c:
        r = c.post("/api/tandas", json=body)
        assert r.status_code == 202 and r.json()["canal_creado"] is None
        id = r.json()["id"]
        r2 = c.post("/api/tandas", json=body)
        assert r2.status_code == 409 and r2.json() == {"error": "ocupado", "run": id}
        assert c.post("/api/stats/medir").json() == {"error": "tanda_en_curso"}
        assert c.get("/api/runs/actual").json()["id"] == id
        fases = [e["fase"] for e in c.get(f"/api/runs/{id}?desde=0").json()["eventos"] if e["tipo"] == "fase"]
        assert fases == ["metricas", "vods"]
        r = c.post(f"/api/runs/{id}/detener")
        assert r.status_code == 202 and r.json() == {"estado": "deteniendo"}
        import time
        for _ in range(50):
            run = c.get(f"/api/runs/{id}").json()
            if run["run"]["estado"] != "en_curso":
                break
            time.sleep(0.05)
        assert run["run"]["estado"] == "detenida" and run["eventos"][-1]["tipo"] == "fin"
        assert c.post(f"/api/runs/{id}/detener").status_code == 409


def test_error_sin_resultado_justo_antes_del_cierre_es_interrumpida(S, notas):
    class SalidaSinResultado(LanzadorFalso):
        async def correr(self, prompt, modelo, al_evento):   # claude sale con 0 al recibir SIGTERM
            return {"estado": "error", "error": "la sesión terminó sin resultado"}

    async def go():
        S.lanzador_factory = SalidaSinResultado
        S.gracia = 0.3
        id = S.lanzar_tanda(dict(PARAMS))
        await asyncio.sleep(0.05)
        await S.cerrar()
        return id
    run = S.leer(asyncio.run(go()), 0)["run"]
    assert run["estado"] == "interrumpida" and notas == []


def test_fase_sale_del_comando_completo_aunque_el_resumen_se_recorte(S, tmp_path):
    """Un Bash largo (heredoc del yaml + render) deja el render más allá de MAX_RESUMEN."""
    largo = ("cd /repo; cat > out/2026-11-02/ibai-x-v2.short.yaml <<'EOF'\n" + "# relleno\n" * 60
             + "EOF\n.venv/bin/clipero render out/2026-11-02/ibai-x-v2.short.yaml")
    async def go():
        _clip(tmp_path, "2026-11-02", "ibai-x")
        LanzadorFalso.guion = [{"tipo": "herramienta", "nombre": "Bash",
                                "resumen": largo[:300], "_cmd": largo}]
        id, _ = S.lanzar_retoque("2026-11-02", "ibai-x", "algo", "sonnet")
        await acabar(S)
        return id
    leido = S.leer(asyncio.run(go()), 0)
    fases = [e["fase"] for e in leido["eventos"] if e["tipo"] == "fase"]
    assert fases == ["guion", "render"]
    assert all("_cmd" not in e for e in leido["eventos"])


def test_yaml_bash_re_reconoce_escrituras_relativas():
    from clipero.app.sesiones import YAML_BASH_RE as R
    assert R.search("cd out/2026-11-03 && cat > perxitaa-x.short.yaml <<'EOF'")
    assert R.search("cat > out/2026-11-02/a-v2.short.yaml <<'EOF'")
    assert not R.search("cat out/a.short.yaml")
    assert not R.search(".venv/bin/clipero render out/a.short.yaml > /tmp/log")


# --- modos de Claude ----------------------------------------------------------------

def test_ninguno_corta_antes_de_iniciar(S, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "modo_claude", lambda root: "ninguno")
    (tmp_path / "out" / "2026-11-02").mkdir(parents=True)
    for ext in (".mp4", ".short.yaml"):
        (tmp_path / "out" / "2026-11-02" / f"ibai-x{ext}").write_text("x")
    (tmp_path / "publicados.csv").write_text("fecha,slug,fuente,formato,tono,vod_id,start,end,url\n")

    async def go():
        with pytest.raises(ses.ClaudeNoDisponible, match="Configuración › Claude"):
            S.lanzar_tanda(PARAMS)
        with pytest.raises(ses.ClaudeNoDisponible):
            S.lanzar_retoque("2026-11-02", "ibai-x", "algo", "sonnet")
    asyncio.run(go())
    assert not S.ocupado() and not (tmp_path / "data" / "runs").exists()


def test_modo_no_disponible_da_motivo(S, monkeypatch):
    async def go():
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        with pytest.raises(ses.ClaudeNoDisponible, match="API key"):
            S.lanzar_tanda(PARAMS)
        monkeypatch.setattr(config, "modo_claude", lambda root: "suscripcion")
        monkeypatch.setattr(ses.shutil, "which", lambda n: None)
        with pytest.raises(ses.ClaudeNoDisponible, match="PATH"):
            S.lanzar_tanda(PARAMS)
    asyncio.run(go())


def test_run_json_guarda_el_modo(S):
    async def go():
        id = S.lanzar_tanda(PARAMS)
        await acabar(S)
        return id
    id = asyncio.run(go())
    assert S.leer(id, 0)["run"]["modo_claude"] == "api_key"


def _captura(monkeypatch):
    """Sustituye ClaudeSDKClient por uno que apunta las ClaudeAgentOptions y termina sin gastar nada."""
    import claude_agent_sdk as sdk
    vistas = []

    class Cliente:
        def __init__(self, opciones):
            vistas.append(opciones)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def query(self, prompt):
            pass

        async def receive_messages(self):
            yield sdk.ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                                    num_turns=1, session_id="s", total_cost_usd=0.01, result="ok")

    monkeypatch.setattr(sdk, "ClaudeSDKClient", Cliente)
    return vistas


@pytest.mark.parametrize("modo", ["api_key", "suscripcion"])
def test_opciones_del_sdk_por_modo(tmp_path, monkeypatch, modo):
    pytest.importorskip("claude_agent_sdk")
    vistas = _captura(monkeypatch)
    monkeypatch.setattr(config, "modo_claude", lambda root: modo)
    monkeypatch.setattr(ses.shutil, "which", lambda n: "/usr/local/bin/claude")
    res = asyncio.run(ses.LanzadorSDK(tmp_path).correr("hola", "sonnet", lambda ev: None))
    assert res["estado"] == "ok" and res["coste_usd"] == 0.01
    o = vistas[0]
    assert o.setting_sources == ["project"] and o.cwd == str(tmp_path) and o.model == "sonnet"
    if modo == "api_key":
        assert o.env == {"ANTHROPIC_API_KEY": "sk-ant-prueba"} and not o.cli_path
    else:
        assert o.cli_path == "/usr/local/bin/claude" and o.env == {"ANTHROPIC_API_KEY": ""}


def test_suscripcion_sin_claude_no_cae_al_binario_del_sdk(tmp_path, monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    vistas = _captura(monkeypatch)
    monkeypatch.setattr(config, "modo_claude", lambda root: "suscripcion")
    monkeypatch.setattr(ses.shutil, "which", lambda n: None)
    with pytest.raises(ses.ClaudeNoDisponible):
        asyncio.run(ses.LanzadorSDK(tmp_path).correr("hola", "sonnet", lambda ev: None))
    assert vistas == []


def test_post_tandas_y_retoque_409_con_ninguno(S, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "modo_claude", lambda root: "ninguno")
    body = {"fuentes": [], "clips": 1, "editorial": "mixta", "dias": 3, "modelo": "sonnet"}
    (tmp_path / "app.yaml").write_text("tanda: {clips: 5, dias: 7, editorial: mixta, modelo: sonnet}\n"
                                       "modelos: [sonnet]\n")
    with TestClient(create_app(tmp_path, sesiones=S, periodico=False)) as c:
        r = c.post("/api/tandas", json=body)
        assert r.status_code == 409
        assert r.json() == {"detail": "Claude desactivado: elige un modo en Configuración › Claude"}
        (tmp_path / "out" / "2026-11-02").mkdir(parents=True)
        for ext in (".mp4", ".short.yaml"):
            (tmp_path / "out" / "2026-11-02" / f"a-x{ext}").write_text("x")
        (tmp_path / "publicados.csv").write_text("fecha,slug,fuente,formato,tono,vod_id,start,end,url\n")
        r = c.post("/api/clips/2026-11-02/a-x/retoque", json={"peticion": "algo"})
        assert r.status_code == 409 and "Configuración › Claude" in r.json()["detail"]
