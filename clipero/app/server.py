"""FastAPI: /api/*, /media/out/* y los estáticos de web/dist. Solo escucha en 127.0.0.1."""
import asyncio
import concurrent.futures
import contextlib
import re
import subprocess
import threading
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, TypeAdapter, ValidationError

from .. import config, render, rutas, sistema, sources
from . import clips, layouts, publicar, rendimiento, sesiones as ses
from .medidor import Medidor
from .sesiones import Sesiones

FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")   # el de render.validate


class PublicarIn(BaseModel):
    url: str = ""
    tono: str | None = None
    fuente: str | None = None
    formato: str | None = None


class TandaIn(BaseModel):
    fuentes: list[str] = []          # vacío = todas; excluyente con vod_url
    vod_url: str | None = None       # http(s); con él se ignoran fuentes y dias
    clips: int                       # 1..10
    editorial: Literal["mixta", "positiva", "critica"]
    dias: int = 7                    # 1..30
    modelo: str                      # tiene que estar en `modelos`
    nota: str = ""                   # ≤ 1000 caracteres


class RetoqueIn(BaseModel):
    peticion: str
    modelo: str | None = None


# Valores de fábrica; app.yaml (si existe) manda: ver `tanda_cfg` en create_app.
TANDA_DEFAULTS = {"clips": 5, "dias": 7, "editorial": "mixta", "modelo": "claude-opus-5-5",
                  "modelos": ["claude-opus-5-5", "sonnet", "haiku"]}
VOD_PLAZO = 30   # s


def _leer_yaml(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text()) or None


def _css_color(valor) -> str | None:
    """«0x2A6FDB» (ffmpeg) → «#2A6FDB» (CSS)."""
    m = re.fullmatch(r"(?:0x|#)([0-9a-fA-F]{6})", str(valor or "").strip())
    return f"#{m.group(1).upper()}" if m else None


CAMPOS_CANAL = ("id", "nombre", "tamaño", "twitch", "youtube", "credito")
PRUEBA_TIMEOUT = 30   # s


def _canal_json(c) -> dict:
    """Canal como dict plano de str (sin tipos de ruamel); omite twitch/youtube ausentes."""
    return {k: str(c[k]) for k in CAMPOS_CANAL if c.get(k) not in (None, "")}


def _canal_in(cuerpo: dict) -> dict:
    """Cuerpo JSON → dict de canal: cadenas recortadas y sin vacíos."""
    out = {}
    for k in CAMPOS_CANAL:
        v = cuerpo.get(k)
        if isinstance(v, str):
            v = v.strip()
        if v not in (None, ""):
            out[k] = v
    return out


def _marca_out(b: dict) -> dict:
    out = {k: str(b.get(k) or "") for k in config.CAMPOS_MARCA}
    out["color"] = _css_color(b.get("color")) or ""
    return out


def create_app(root: Path | None = None, medidor: Medidor | None = None, periodico: bool = True,
               flat_playlist=None, sesiones: Sesiones | None = None, vod_info=None) -> FastAPI:
    """`medidor`, `flat_playlist`, `sesiones` y `vod_info` inyectables (para no tocar la red ni el SDK
    en los tests); `periodico=False` no arranca la tarea de 6 h en el lifespan."""
    root = Path(root) if root is not None else rutas.home()
    sesiones = sesiones or Sesiones(root)
    medidor = medidor or Medidor(root, ocupado=sesiones.ocupado)
    flat_playlist = flat_playlist or sources.flat_playlist
    vod_info = vod_info or sources.vod_info
    lock_config = threading.Lock()

    def tanda_cfg() -> dict:
        """Defaults de la tanda leídos de app.yaml en cada llamada (las constantes si no existe o no se lee)."""
        with lock_config:
            try:
                return config.load_app(root)
            except Exception:
                return dict(TANDA_DEFAULTS)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        layouts.purgar_frames(root)
        sesiones.marcar_interrumpidas()
        tarea = asyncio.create_task(medidor.bucle()) if periodico else None
        try:
            yield
        finally:
            if tarea:
                tarea.cancel()
            await sesiones.cerrar()

    app = FastAPI(title="Clipero", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/api/salud")
    def salud():
        return {"ok": True}

    @app.get("/api/fuentes")
    def fuentes():
        lista = _leer_yaml(root / "sources.yaml") or []
        return [{"id": s["id"], "nombre": s.get("nombre", s["id"])} for s in lista]

    @app.get("/api/marca")
    def marca():
        b = _leer_yaml(root / "branding.yaml") or {}
        return {"nombre": b.get("nombre", "Clipero"), "color": _css_color(b.get("color"))}

    @app.get("/media/out/{fecha}/{slug}.mp4")
    def media(fecha: str, slug: str):
        if not FECHA_RE.fullmatch(fecha) or not SLUG_RE.fullmatch(slug):
            return JSONResponse({"error": "no_encontrado"}, status_code=404)
        f = root / "out" / fecha / f"{slug}.mp4"
        if not f.is_file():
            return JSONResponse({"error": "no_encontrado"}, status_code=404)
        return FileResponse(f, media_type="video/mp4")   # 206 con Range

    def _no_encontrado():
        return JSONResponse({"error": "no_encontrado"}, status_code=404)

    def _valido(fecha, slug):
        return bool(FECHA_RE.fullmatch(fecha) and SLUG_RE.fullmatch(slug))

    @app.exception_handler(publicar.Fallo)
    def _fallo(_req, e: publicar.Fallo):
        cuerpo = {"error": e.codigo}
        if e.detalle is not None:
            cuerpo["detalle"] = e.detalle
        return JSONResponse(cuerpo, status_code=e.status)

    @app.exception_handler(ses.ClaudeNoDisponible)
    def _sin_claude(_req, e: ses.ClaudeNoDisponible):
        return JSONResponse({"detail": str(e) or ses.MENSAJE_NINGUNO}, status_code=409)

    @app.exception_handler(RequestValidationError)
    def _invalido(_req, e: RequestValidationError):
        detalle = [f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}" for err in e.errors()]
        return JSONResponse({"error": "invalido", "detalle": detalle}, status_code=422)

    # --- configuración: canales y marca ---

    def _listas(seq, cola):
        return {"activos": [_canal_json(c) for c in seq],
                "reserva": [_canal_json(c) for c in config.parse_reserva(cola)]}

    def _buscar(seq, id):
        for i, c in enumerate(seq):
            if c.get("id") == id:
                return i
        raise publicar.Fallo(404, "no_encontrado")

    def _guardar(fn):
        """Ejecuta `fn()` traduciendo config.Invalido a 422."""
        try:
            return fn()
        except config.Invalido as e:
            raise publicar.Fallo(422, "invalido", e.detalle)

    @app.get("/api/config/canales")
    def get_canales():
        with lock_config:
            seq, cola = config.load_sources_rt(root)
            return _listas(seq, cola)

    @app.post("/api/config/canales/probar")
    def probar_canal(cuerpo: dict):
        c = _canal_in(cuerpo)
        urls = {"twitch": sources.twitch_url(c["twitch"]) if c.get("twitch") else None,
                "youtube": c.get("youtube")}
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        futuros = {p: ex.submit(flat_playlist, u, 3, timeout=PRUEBA_TIMEOUT) for p, u in urls.items() if u}
        fin = concurrent.futures.wait(futuros.values(), timeout=PRUEBA_TIMEOUT).done
        ex.shutdown(wait=False, cancel_futures=True)   # sin `with`: la respuesta no espera a los hilos
        out = {}
        for p in ("twitch", "youtube"):
            f = futuros.get(p)
            if f is None:
                out[p] = None
            elif f not in fin or isinstance(f.exception(), subprocess.TimeoutExpired):
                out[p] = {"ok": False, "vods": 0, "error": f"Sin respuesta en {PRUEBA_TIMEOUT} s"}
            elif f.exception():
                out[p] = {"ok": False, "vods": 0, "error": str(f.exception())}
            else:
                n = len(f.result())
                out[p] = {"ok": n > 0, "vods": n, "error": None if n else "Sin VODs"}
        return out

    @app.post("/api/config/canales", status_code=201)
    def alta_canal(cuerpo: dict):
        c = _canal_in(cuerpo)
        with lock_config:
            seq, cola = config.load_sources_rt(root)
            usados = {x.get("id") for x in seq} | {x["id"] for x in config.parse_reserva(cola)}
            if isinstance(c.get("id"), str) and c["id"] in usados:
                raise publicar.Fallo(409, "id_repetido")
            if not c.get("credito") and c.get("nombre"):
                c["credito"] = config.credito_por_defecto(c)
            seq.append(config.nuevo_canal(c))
            _guardar(lambda: config.save_sources(root, seq, cola))
            return _canal_json(seq[-1])

    @app.put("/api/config/canales/{id}")
    def edita_canal(id: str, cuerpo: dict):
        datos = _canal_in(cuerpo)
        with lock_config:
            seq, cola = config.load_sources_rt(root)
            item = seq[_buscar(seq, id)]
            config.actualizar_canal(item, datos)
            _guardar(lambda: config.save_sources(root, seq, cola))
            return _canal_json(item)

    @app.post("/api/config/canales/{id}/reserva")
    def a_reserva(id: str):
        with lock_config:
            seq, cola = config.load_sources_rt(root)
            i = _buscar(seq, id)
            canal = {k: v for k, v in _canal_json(seq[i]).items()}
            del seq[i]
            cola = config.a_reserva(cola, canal, f"a reserva el {date.today().isoformat()}")
            _guardar(lambda: config.save_sources(root, seq, cola))
            return _listas(seq, cola)

    @app.post("/api/config/canales/{id}/reactivar")
    def reactivar(id: str):
        with lock_config:
            seq, cola = config.load_sources_rt(root)
            try:
                cola, canal = config.quitar_de_reserva(cola, id)
            except KeyError:
                raise publicar.Fallo(404, "no_encontrado")
            seq.append(config.nuevo_canal(canal))
            _guardar(lambda: config.save_sources(root, seq, cola))
            return _listas(seq, cola)

    @app.get("/api/config/marca")
    def get_marca():
        with lock_config:
            return _marca_out(config.load_branding_rt(root))

    @app.put("/api/config/marca")
    def put_marca(cuerpo: dict):
        data = {}
        for k in config.CAMPOS_MARCA:
            v = cuerpo.get(k)
            if isinstance(v, str):
                v = v.strip()
            if k == "color":
                m = re.fullmatch(r"(?:#|0x)([0-9a-fA-F]{6})", v or "") if isinstance(v, str) else None
                v = f"0x{m.group(1).upper()}" if m else v
            if v not in (None, "") or k in ("nombre", "color"):
                data[k] = v
        with lock_config:
            _guardar(lambda: config.save_branding(root, data))
            return _marca_out(config.load_branding_rt(root))

    @app.get("/api/config/tanda")
    def get_tanda():
        with lock_config:
            return config.load_app(root)

    @app.put("/api/config/tanda")
    def put_tanda(cuerpo: dict):
        data = {k: cuerpo.get(k) for k in ("clips", "dias", "editorial", "modelo", "modelos")}
        if isinstance(data["modelo"], str):
            data["modelo"] = data["modelo"].strip()
        if isinstance(data["modelos"], list):
            data["modelos"] = [m.strip() if isinstance(m, str) else m for m in data["modelos"]]
        with lock_config:
            _guardar(lambda: config.save_app(root, data))
            return config.load_app(root)

    # --- configuración: modos de Claude (la clave nunca sale en una respuesta) ---

    @app.get("/api/config/claude")
    def get_claude():
        with lock_config:
            return config.claude_estado(root)

    @app.put("/api/config/claude")
    def put_claude(cuerpo: dict):
        modo = cuerpo.get("modo")
        if modo not in config.MODOS_CLAUDE:
            return JSONResponse({"error": "modo_desconocido",
                                 "detalle": ["modo: ninguno, api_key o suscripcion"]}, status_code=400)
        clave = cuerpo.get("api_key")
        if clave is not None and not isinstance(clave, str):
            raise publicar.Fallo(422, "invalido", ["api_key: tiene que ser texto"])
        if sesiones.ocupado():
            return _ocupado()
        with lock_config:
            if clave is not None:
                config.guardar_api_key(root, clave)   # "" la borra
            estado = config.claude_estado(root)
            if modo != "ninguno" and not estado["disponibles"][modo]:
                motivo = ("falta la API key" if modo == "api_key" else "no hay `claude` en el PATH")
                return JSONResponse({"error": "modo_no_disponible", "detalle": [f"{modo}: {motivo}"]},
                                    status_code=409)
            _guardar(lambda: config.save_app(root, {**config.load_app(root), "modo": modo}))
            return config.claude_estado(root)

    # --- layouts: fotogramas, CRUD y detección (vods y probar antes que las rutas con {vod}) ---

    @app.get("/api/layouts")
    def get_layouts():
        with lock_config:
            seq, _ = config.load_sources_rt(root)
            return layouts.listar(root, [(str(c["id"]), str(c.get("nombre", c["id"]))) for c in seq])

    @app.post("/api/layouts/probar")
    def probar_layout(cuerpo: dict):
        layout, vod, seg, t = (cuerpo.get(k) for k in ("layout", "vod", "seg", "t"))
        if not (isinstance(vod, str) and isinstance(seg, str)):
            raise publicar.Fallo(404, "no_encontrado")
        return layouts.probar(root, layout, vod, seg, t)

    @app.get("/api/layouts/{fuente}/vods")
    def get_layout_vods(fuente: str):
        layouts.check_fuente(fuente)
        return layouts.vods_de(root, fuente)

    @app.get("/api/frame/{vod}/{seg}.jpg")
    def get_frame(vod: str, seg: str, t: float):
        return FileResponse(layouts.fotograma(root, vod, seg, t), media_type="image/jpeg")

    @app.get("/api/layouts/{fuente}")
    def get_layout(fuente: str):
        layouts.check_fuente(fuente)
        return layouts.leer(root, fuente)

    @app.get("/api/layouts/{fuente}/{vod}")
    def get_layout_vod(fuente: str, vod: str):
        layouts.check_fuente(fuente)
        layouts.check_vod(vod)
        return layouts.leer(root, fuente, vod)

    @app.put("/api/layouts/{fuente}")
    def put_layout(fuente: str, cuerpo: dict):
        layouts.check_fuente(fuente)
        with lock_config:
            return layouts.guardar(root, fuente, None, cuerpo)

    @app.put("/api/layouts/{fuente}/{vod}")
    def put_layout_vod(fuente: str, vod: str, cuerpo: dict):
        layouts.check_fuente(fuente)
        layouts.check_vod(vod)
        with lock_config:
            return layouts.guardar(root, fuente, vod, cuerpo)

    @app.delete("/api/layouts/{fuente}", status_code=204)
    def del_layout(fuente: str):
        layouts.check_fuente(fuente)
        with lock_config:
            layouts.borrar(root, fuente)
        return Response(status_code=204)

    @app.delete("/api/layouts/{fuente}/{vod}", status_code=204)
    def del_layout_vod(fuente: str, vod: str):
        layouts.check_fuente(fuente)
        layouts.check_vod(vod)
        with lock_config:
            layouts.borrar(root, fuente, vod)
        return Response(status_code=204)

    @app.get("/api/clips")
    def lista_clips(fuente: str | None = None, tono: str | None = None, formato: str | None = None,
                    desde: str | None = None, hasta: str | None = None, publicado: str | None = None):
        return clips.filtrar(clips.escanear(root), fuente, tono, formato, desde, hasta, publicado)

    @app.get("/api/thumbs/{fecha}/{slug}.jpg")
    def thumb(fecha: str, slug: str):
        if not _valido(fecha, slug):
            return _no_encontrado()
        try:
            return FileResponse(clips.miniatura(root, fecha, slug), media_type="image/jpeg")
        except FileNotFoundError:
            return _no_encontrado()
        except RuntimeError:
            return JSONResponse({"error": "miniatura"}, status_code=500)

    @app.delete("/api/clips/{fecha}/{slug}")
    def borrar_clip(fecha: str, slug: str):
        if not _valido(fecha, slug):
            return _no_encontrado()
        clips.borrar(root, fecha, slug)
        return Response(status_code=204)

    @app.post("/api/clips/{fecha}/{slug}/abrir-carpeta")
    def abrir_carpeta(fecha: str, slug: str):
        if not _valido(fecha, slug) or not (root / "out" / fecha / f"{slug}.mp4").is_file():
            return _no_encontrado()
        sistema.abrir(root / "out" / fecha)
        return Response(status_code=204)

    @app.post("/api/clips/{fecha}/{slug}/publicar", status_code=201)
    def publicar_clip(fecha: str, slug: str, cuerpo: PublicarIn):
        if not _valido(fecha, slug):
            return _no_encontrado()
        fila = publicar.publicar(root, fecha, slug, cuerpo.url,
                                 {"tono": cuerpo.tono, "fuente": cuerpo.fuente, "formato": cuerpo.formato})
        return {"fila": fila}

    @app.post("/api/clips/{fecha}/{slug}/claim")
    def claim_clip(fecha: str, slug: str):
        if not _valido(fecha, slug) or not (root / "out" / fecha / f"{slug}.mp4").is_file():
            return _no_encontrado()
        publicar.marcar_claim(root, slug)
        return Response(status_code=204)

    # --- tandas, retoques y runs ---

    def _ocupado():
        a = sesiones.actual()
        return JSONResponse({"error": "ocupado", "run": a["id"] if a else None}, status_code=409)

    def _errores_tanda(d: dict) -> tuple[list[str], TandaIn | None]:
        """Errores de pydantic (tipos, Literal, campos que faltan) y de negocio, juntos en una lista."""
        err, malos = [], set()
        try:
            t = TandaIn.model_validate(d)
        except ValidationError as e:
            t = None
            for x in e.errors():
                campo = ".".join(str(c) for c in x["loc"])
                malos.add(str(x["loc"][0]) if x["loc"] else "")
                err.append(f"{campo}: {x['msg']}")

        # valores ya coercionados por pydantic (modo lax: «50» → 50, 50.0 → 50) de los campos que no fallaron
        v = {}
        for k, campo in TandaIn.model_fields.items():
            if k in d and k not in malos:
                v[k] = getattr(t, k) if t else TypeAdapter(campo.annotation).validate_python(d[k])

        activos = {s["id"] for s in (_leer_yaml(root / "sources.yaml") or [])}
        fuentes, vod = v.get("fuentes") or [], v.get("vod_url")
        if fuentes and vod:
            err.append("fuentes y vod_url son excluyentes")
        for f in fuentes:
            if f not in activos:
                err.append(f"fuentes: «{f}» no es un canal activo")
        if vod is not None and not re.match(r"https?://\S+$", vod.strip()):
            err.append("vod_url: tiene que ser una URL http(s)")
        if "clips" in v and not 1 <= v["clips"] <= 10:
            err.append("clips: de 1 a 10")
        if "dias" in v and not 1 <= v["dias"] <= 30:
            err.append("dias: de 1 a 30")
        if "modelo" in v and v["modelo"] not in tanda_cfg()["modelos"]:
            err.append(f"modelo: «{v['modelo']}» no está en la lista de modelos")
        if "nota" in v and len(v["nota"]) > 1000:
            err.append("nota: máximo 1000 caracteres")
        return err, t

    async def _info_vod(url: str) -> dict:
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            return await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(ex, vod_info, url),
                                          VOD_PLAZO)
        except asyncio.TimeoutError:
            raise publicar.Fallo(422, "vod_invalido", f"Sin respuesta en {VOD_PLAZO} s")
        except RuntimeError as e:
            raise publicar.Fallo(422, "vod_invalido", str(e))
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    def _alta_canal_vod(info: dict) -> dict | None:
        """Da de alta (activo) el canal del VOD si no está en sources.yaml. → {id,nombre,credito} o None."""
        with lock_config:
            if render.source_of_info(info, render.load_sources(root / "sources.yaml")):
                return None
            seq, cola = config.load_sources_rt(root)
            usados = {x.get("id") for x in seq} | {x["id"] for x in config.parse_reserva(cola)}
            canal = config.nuevo_canal(ses.canal_desde_info(info, usados))
            seq.append(canal)
            try:
                config.save_sources(root, seq, cola)
            except config.Invalido as e:
                raise publicar.Fallo(422, "canal_no_creable", e.detalle)
            return {k: str(canal[k]) for k in ("id", "nombre", "credito")}

    @app.get("/api/tandas/defaults")
    def tanda_defaults():
        return tanda_cfg()

    @app.post("/api/tandas", status_code=202)
    async def lanzar_tanda(cuerpo: dict):
        err, t = _errores_tanda(cuerpo)
        if err or t is None:
            raise publicar.Fallo(422, "invalido", err)
        if sesiones.ocupado():
            return _ocupado()
        ses.comprobar_claude(root)   # antes de dar de alta ningún canal
        canal = None
        url = (t.vod_url or "").strip() or None
        if url:
            canal = await asyncio.to_thread(_alta_canal_vod, await _info_vod(url))
            if sesiones.ocupado():
                return _ocupado()
        params = {"fuentes": [] if url else t.fuentes, "vod_url": url, "clips": t.clips,
                  "editorial": t.editorial, "dias": t.dias, "modelo": t.modelo, "nota": t.nota}
        try:
            id = sesiones.lanzar_tanda(params, canal)
        except publicar.Fallo as e:
            if e.codigo == "ocupado":
                return _ocupado()
            raise
        return {"id": id, "canal_creado": canal}

    @app.post("/api/clips/{fecha}/{slug}/retoque", status_code=202)
    async def retoque(fecha: str, slug: str, cuerpo: RetoqueIn):
        if not _valido(fecha, slug):
            return _no_encontrado()
        cfg = tanda_cfg()
        modelo = cuerpo.modelo or cfg["modelo"]
        if modelo not in cfg["modelos"]:
            raise publicar.Fallo(422, "invalido", [f"modelo: «{modelo}» no está en la lista de modelos"])
        try:
            id, destino = sesiones.lanzar_retoque(fecha, slug, cuerpo.peticion, modelo)
        except publicar.Fallo as e:
            if e.codigo == "ocupado":
                return _ocupado()
            raise
        return {"id": id, "destino": destino}

    @app.get("/api/runs")
    async def lista_runs():
        return sesiones.listar(30)

    @app.get("/api/runs/actual")
    async def run_actual():
        return sesiones.actual()

    @app.get("/api/runs/{id}")
    async def run(id: str, desde: int = 0):
        return sesiones.leer(id, desde)

    @app.post("/api/runs/{id}/detener", status_code=202)
    async def detener_run(id: str):
        try:
            await sesiones.detener(id)
        except publicar.Fallo as e:
            if e.codigo == "no_en_curso":
                return JSONResponse({"error": "no_en_curso"}, status_code=409)
            raise
        return {"estado": "deteniendo"}

    @app.get("/api/rendimiento")
    def get_rendimiento():
        return rendimiento.rendimiento(root)

    @app.post("/api/stats/medir", status_code=202)
    async def medir():
        if sesiones.ocupado():
            return JSONResponse({"error": "tanda_en_curso"}, status_code=409)
        if not medidor.iniciar():
            return JSONResponse({"error": "ya_midiendo"}, status_code=409)
        return {"estado": "midiendo"}

    @app.get("/api/stats/estado")
    def estado_medidor():
        return medidor.estado()

    dist = rutas.PKG / "app" / "static"

    @app.get("/{ruta:path}", include_in_schema=False)
    def estaticos(ruta: str):
        if ruta.startswith(("api/", "media/")) or ruta in ("api", "media"):
            return JSONResponse({"error": "no_encontrado"}, status_code=404)
        if not dist.is_dir():
            return JSONResponse({"error": "sin_frontend"}, status_code=404)
        if ruta:
            f = (dist / ruta).resolve()
            if f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
        return FileResponse(dist / "index.html")

    return app
