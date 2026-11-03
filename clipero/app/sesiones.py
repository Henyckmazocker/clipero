"""Gestor de sesiones del Agent SDK: una sola a la vez (tanda o retoque), con run.json + eventos.jsonl en data/runs/."""
import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .. import config, sistema
from .clips import VERSION_RE
from .publicar import Fallo, leer_publicados

FASES = ["metricas", "vods", "ingesta", "transcripcion", "guion", "render", "limpieza"]
CMD_FASE = {"stats": "metricas", "vods": "vods", "ingest": "ingesta", "candidates": "ingesta",
            "transcribe": "transcripcion", "render": "render", "clean": "limpieza"}
ALTERNAN = {"transcripcion", "guion", "render"}   # se alternan en el plan B de la skill y en los retoques
CMD_RE = re.compile(r"(?:^|[\s;&|(/])clipero\s+(\w+)")   # `clipero <cmd>` del PATH o `<ruta>/bin/clipero <cmd>`
YAML_RE = re.compile(r"(?:^|/)out/.+\.short\.yaml$")
# Bash que escribe un short.yaml (heredoc, redirección o tee): cuenta como «guion»
YAML_BASH_RE = re.compile(r"(?:>|\btee\s+(?:-a\s+)?)\s*['\"]?\S*\.short\.yaml\b")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d+)?-(?:tanda|retoque)$")
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_RESUMEN = 300
MAX_SALIDA = 2000
PLAZO_CIERRE = 5   # s
GRACIA_ERROR = 1.5   # s: un fallo del lanzador espera por si es el SIGTERM del cierre llegando al hijo
MOTIVO_DENEGADO = "Sesión desatendida desde la app: decide sin preguntar y sigue"


class ClaudeNoDisponible(Exception):
    """Claude desactivado (modo «ninguno») o el modo elegido no se puede usar; `str(e)` es el motivo para el usuario."""

MENSAJE_NINGUNO = "Claude desactivado: elige un modo en Configuración › Claude"


def comprobar_claude(root) -> str:
    """Modo de Claude de `root` si se puede lanzar una sesión; si no, ClaudeNoDisponible con el motivo."""
    modo = config.modo_claude(root)
    if modo == "ninguno":
        raise ClaudeNoDisponible(MENSAJE_NINGUNO)
    if modo == "api_key" and config.api_key(root) is None:
        raise ClaudeNoDisponible("Claude no disponible: falta la API key (Configuración › Claude)")
    if modo == "suscripcion" and shutil.which("claude") is None:
        raise ClaudeNoDisponible("Claude no disponible: no hay `claude` en el PATH (instala Claude Code e inicia sesión)")
    return modo


# --- transporte ------------------------------------------------------------------

class Lanzador(Protocol):
    """El transporte; el real usa claude_agent_sdk, los tests un falso."""

    async def correr(self, prompt: str, modelo: str, al_evento) -> dict:
        """Devuelve {"estado": "ok"|"error", "coste_usd", "error", "session_id"}."""

    async def detener(self) -> None: ...


def resumen_herramienta(nombre: str, entrada: dict) -> str:
    entrada = entrada or {}
    clave = {"Bash": "command", "Read": "file_path", "Write": "file_path", "Edit": "file_path",
             "Glob": "pattern", "Grep": "pattern"}.get(nombre)
    return str(entrada.get(clave) or "")[:MAX_RESUMEN] if clave else ""


def _texto_salida(contenido) -> str:
    if isinstance(contenido, list):
        contenido = "\n".join(str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in contenido)
    return str(contenido or "")[-MAX_SALIDA:]


class LanzadorSDK:
    def __init__(self, root):
        self.root = Path(root)
        self._client = None
        self._parar = False

    async def correr(self, prompt, modelo, al_evento):
        from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, PermissionResultDeny,
                                      ResultMessage, SystemMessage, TextBlock, ToolResultBlock, ToolUseBlock,
                                      UserMessage)

        async def _deniega(nombre, _entrada, _ctx):
            al_evento({"tipo": "denegado", "nombre": nombre, "motivo": MOTIVO_DENEGADO})
            return PermissionResultDeny(message=MOTIVO_DENEGADO)

        modo = comprobar_claude(self.root)   # «ninguno» no llega aquí: lanzar_* lo corta antes
        base = dict(cwd=str(self.root), setting_sources=["project"], permission_mode="auto",
                    model=modelo, can_use_tool=_deniega)
        if modo == "api_key":
            opciones = ClaudeAgentOptions(**base, env={"ANTHROPIC_API_KEY": config.api_key(self.root)})
        else:   # suscripcion: siempre el `claude` del usuario, nunca el binario que trae el SDK
            opciones = ClaudeAgentOptions(**base, cli_path=shutil.which("claude"),
                                          env={"ANTHROPIC_API_KEY": ""})
        res = {"estado": "error", "coste_usd": None, "error": "la sesión terminó sin resultado", "session_id": None}
        async with ClaudeSDKClient(opciones) as c:
            self._client = c
            await c.query(prompt)
            if self._parar:
                await c.interrupt()
            async for m in c.receive_messages():
                if isinstance(m, SystemMessage):
                    if m.subtype == "init":
                        res["session_id"] = (m.data or {}).get("session_id")
                        al_evento({"tipo": "init", "session_id": res["session_id"]})
                elif isinstance(m, AssistantMessage):
                    for b in m.content:
                        if isinstance(b, TextBlock) and b.text.strip():
                            al_evento({"tipo": "texto", "texto": b.text})
                        elif isinstance(b, ToolUseBlock):
                            # `_cmd` (completo, sin recortar) solo sirve para deducir la fase; no se guarda
                            al_evento({"tipo": "herramienta", "nombre": b.name,
                                       "resumen": resumen_herramienta(b.name, b.input),
                                       "_cmd": str((b.input or {}).get("command") or (b.input or {}).get("file_path") or "")})
                elif isinstance(m, UserMessage) and isinstance(m.content, list):
                    for b in m.content:
                        if isinstance(b, ToolResultBlock):
                            al_evento({"tipo": "salida", "texto": _texto_salida(b.content),
                                       "error": bool(b.is_error)})
                elif isinstance(m, ResultMessage):
                    res["estado"] = "error" if m.is_error else "ok"
                    res["coste_usd"] = m.total_cost_usd
                    res["session_id"] = m.session_id or res["session_id"]
                    res["error"] = ((m.result or "; ".join(m.errors or []) or m.subtype)[:MAX_RESUMEN]
                                    if m.is_error else None)
                    break
        self._client = None
        return res

    async def detener(self):
        self._parar = True
        if self._client is not None:
            await asyncio.wait_for(self._client.interrupt(), PLAZO_CIERRE)


# --- notificación, prompts, canal ---------------------------------------------------

def notify_send(texto: str) -> None:
    """Notificación de escritorio según el SO (clipero.sistema); nunca falla."""
    sistema.notificar("Clipero", texto)


def prompt_tanda(params: dict) -> str:
    fuentes = ", ".join(params.get("fuentes") or []) or "todas"
    nota = (params.get("nota") or "").strip()
    return (
        "Usa la skill `tanda` con estos parámetros. Te lanza la app de clipero: no hay nadie delante, no\n"
        "preguntes nada, y esta tanda cuenta como pedida expresamente aunque ya haya shorts de hoy.\n\n"
        "<parametros_tanda>\n"
        f"fuentes: {fuentes}\n"
        f"vod: {params.get('vod_url') or '—'}\n"
        f"clips_max: {params['clips']}\n"
        f"editorial: {params['editorial']}\n"
        f"dias: {params['dias']}\n"
        f"nota: {'«' + nota + '»' if nota else '—'}\n"
        "</parametros_tanda>")


def prompt_retoque(fecha: str, slug: str, destino: str, peticion: str) -> str:
    return (
        "Usa la sección «Retoque» de la skill `tanda`. Te lanza la app: no preguntes nada.\n"
        f"Origen: out/{fecha}/{slug}.short.yaml\n"
        f"Destino: out/{fecha}/{destino}.short.yaml (slug: {destino})\n"
        f"Petición del usuario: «{peticion.strip()}»")


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def canal_desde_info(info: dict, usados=()) -> dict:
    """Canal por defecto para un VOD de una fuente desconocida. `usados` = ids activos + reserva.
    Puede salir inválido (p. ej. YouTube sin handle): quien lo guarda lo valida."""
    uid = str(info.get("uploader_id") or "")
    twitch = str(info.get("extractor_key") or "").lower().startswith("twitch")
    handle = uid.lstrip("@")
    base = _slug(handle)
    cid, n = base, 2
    while base and cid in usados:
        cid, n = f"{base}-{n}", n + 1
    return {"id": cid,
            "nombre": info.get("uploader") or uid,
            "tamaño": "mediano",
            "twitch": uid.lower() if twitch and uid else None,
            "youtube": f"https://www.youtube.com/@{handle}" if not twitch and uid.startswith("@") else None,
            "credito": None}


# --- gestor ---------------------------------------------------------------------------

class Sesiones:
    def __init__(self, root, lanzador_factory=LanzadorSDK, notificar=notify_send, ahora=datetime.now):
        self.root = Path(root)
        self.lanzador_factory = lanzador_factory
        self.notificar = notificar
        self.ahora = ahora
        self._run = None
        self._n = 0
        self._detenido = False
        self._lanzador = None
        self._tarea = None
        self._cerrando = False
        self.gracia = GRACIA_ERROR

    # -- disco --
    @property
    def _runs(self) -> Path:
        return self.root / "data" / "runs"

    def _guardar(self, run=None):
        run = run or self._run
        config.write_atomic(self._runs / run["id"] / "run.json", json.dumps(run, ensure_ascii=False, indent=1))

    def _leer_run(self, id: str) -> dict | None:
        if not RUN_ID_RE.fullmatch(id):
            return None
        p = self._runs / id / "run.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _anadir_evento(self, id: str, i: int, ev: dict) -> dict:
        ev = {"i": i, "t": self.ahora().strftime("%H:%M:%S"), **ev}
        with open(self._runs / id / "eventos.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    # -- estado --
    def actual(self) -> dict | None:
        return dict(self._run) if self._run and self._run["estado"] == "en_curso" else None

    def ocupado(self) -> bool:
        return self.actual() is not None

    def leer(self, id: str, desde: int) -> dict:
        run = self._leer_run(id)
        if run is None:
            raise Fallo(404, "no_encontrado")
        eventos = []
        p = self._runs / id / "eventos.jsonl"
        if p.exists():
            for linea in p.read_text(encoding="utf-8").splitlines():
                try:
                    eventos.append(json.loads(linea))
                except ValueError:
                    break   # línea a medio escribir: se lee en el siguiente sondeo
        desde = max(0, desde)
        return {"run": run, "eventos": [e for e in eventos if e["i"] >= desde],
                "siguiente": max(desde, len(eventos))}

    def listar(self, n: int = 30) -> list[dict]:
        if not self._runs.is_dir():
            return []
        out = []
        for d in sorted((d.name for d in self._runs.iterdir() if d.is_dir()), reverse=True):
            run = self._leer_run(d)
            if run:
                run["params"] = {k: v for k, v in (run.get("params") or {}).items() if k != "nota"}
                out.append(run)
            if len(out) >= n:
                break
        return out

    def marcar_interrumpidas(self) -> int:
        """Al arrancar: los run en_curso del disco (de un servicio que murió) pasan a interrumpida."""
        if not self._runs.is_dir():
            return 0
        n = 0
        for d in sorted(self._runs.iterdir()):
            run = self._leer_run(d.name)
            if not run or run.get("estado") != "en_curso":
                continue
            if self._run and self._run["id"] == run["id"]:
                continue
            total = len((d / "eventos.jsonl").read_text(encoding="utf-8").splitlines()) \
                if (d / "eventos.jsonl").exists() else 0
            self._anadir_evento(run["id"], total, {"tipo": "fin", "estado": "interrumpida"})
            run.update(estado="interrumpida", terminado=self.ahora().isoformat(timespec="seconds"),
                       eventos=total + 1)
            run["resultado"] = {"shorts": self._shorts(run["creado"]), "coste_usd": None,
                                "error": "el servicio se reinició"}
            self._guardar(run)
            n += 1
        return n

    # -- lanzar --
    def _shorts(self, creado: str) -> list[dict]:
        t0 = datetime.fromisoformat(creado).timestamp()
        out = []
        base = self.root / "out"
        if base.is_dir():
            for carpeta in sorted(base.iterdir()):
                if not (carpeta.is_dir() and FECHA_RE.fullmatch(carpeta.name)):
                    continue
                for mp4 in sorted(carpeta.glob("*.mp4")):
                    if mp4.stat().st_mtime >= t0:
                        out.append({"fecha": carpeta.name, "slug": mp4.stem})
        return out

    def _iniciar(self, tipo: str, params: dict, modelo: str, prompt: str, canal_creado=None) -> str:
        if self.ocupado():
            raise Fallo(409, "ocupado")
        modo_claude = comprobar_claude(self.root)
        ahora = self.ahora()
        id = f"{ahora:%Y%m%d-%H%M%S}-{tipo}"
        n = 2
        while (self._runs / id).exists():
            id, n = f"{ahora:%Y%m%d-%H%M%S}-{n}-{tipo}", n + 1
        (self._runs / id).mkdir(parents=True)
        run = {"id": id, "tipo": tipo, "estado": "en_curso", "creado": ahora.isoformat(timespec="seconds"),
               "terminado": None, "modelo": modelo, "modo_claude": modo_claude, "params": params, "canal_creado": canal_creado,
               "fase": None, "session_id": None, "eventos": 0,
               "resultado": {"shorts": [], "coste_usd": None, "error": None}}
        self._run, self._n, self._detenido = run, 0, False
        self._guardar()   # síncrono: un segundo POST ve ya el 409
        self._lanzador = self.lanzador_factory(self.root)
        self._tarea = asyncio.create_task(self._correr(run, prompt, self._lanzador))
        return id

    def lanzar_tanda(self, params: dict, canal_creado: dict | None = None) -> str:
        return self._iniciar("tanda", params, params["modelo"], prompt_tanda(params), canal_creado)

    def destino(self, fecha: str, slug: str) -> str:
        m = VERSION_RE.match(slug)
        base = m["base"] if m else slug
        mayor = 1
        for f in (self.root / "out" / fecha).glob("*"):
            nombre = f.name
            for suf in (".short.yaml", ".mp4"):
                if nombre.endswith(suf):
                    mm = VERSION_RE.match(nombre[: -len(suf)])
                    if mm and mm["base"] == base:
                        mayor = max(mayor, int(mm["n"] or 1))
        return f"{base}-v{mayor + 1}"

    def lanzar_retoque(self, fecha: str, slug: str, peticion: str, modelo: str) -> tuple[str, str]:
        carpeta = self.root / "out" / fecha
        if not (carpeta / f"{slug}.mp4").is_file():
            raise Fallo(404, "no_encontrado")
        if not (peticion or "").strip():
            raise Fallo(422, "invalido", ["peticion: no puede estar vacía"])
        if slug in leer_publicados(self.root):
            raise Fallo(409, "publicado")
        if not (carpeta / f"{slug}.short.yaml").is_file():
            raise Fallo(422, "sin_yaml")
        if self.ocupado():
            raise Fallo(409, "ocupado")
        destino = self.destino(fecha, slug)
        params = {"fecha": fecha, "slug": slug, "destino": destino, "peticion": peticion.strip()}
        id = self._iniciar("retoque", params, modelo, prompt_retoque(fecha, slug, destino, peticion))
        return id, destino

    # -- ejecución --
    def _evento(self, ev: dict) -> None:
        """Callback del lanzador: asigna i/t, persiste y deduce la fase."""
        run = self._run
        if run is None:
            return
        if ev.get("tipo") == "init":
            run["session_id"] = ev.get("session_id")
            self._guardar()
            return
        cmd = ev.pop("_cmd", None)
        self._emitir(ev)
        if ev.get("tipo") == "herramienta":
            self._deducir_fase(ev, cmd)

    def _emitir(self, ev: dict) -> None:
        run = self._run
        self._anadir_evento(run["id"], self._n, ev)
        self._n += 1
        run["eventos"] = self._n
        self._guardar()

    def _deducir_fase(self, ev: dict, cmd: str | None = None) -> None:
        """La fase sale del comando completo (`cmd`) si lo hay: el `resumen` va recortado a
        MAX_RESUMEN y un Bash largo (heredoc del yaml + render) dejaría el render fuera."""
        resumen = cmd or ev.get("resumen") or ""
        vistas = []
        if ev.get("nombre") == "Bash":
            hits = [(m.start(), CMD_FASE[m.group(1)]) for m in CMD_RE.finditer(resumen) if m.group(1) in CMD_FASE]
            hits += [(m.start(), "guion") for m in YAML_BASH_RE.finditer(resumen)]
            vistas = [f for _, f in sorted(hits)]
        elif ev.get("nombre") in ("Write", "Edit") and YAML_RE.search(resumen):
            vistas = ["guion"]
        for f in vistas:
            actual = self._run["fase"]
            if self._run["tipo"] == "retoque" and f not in ALTERNAN:
                continue
            if f == actual:
                continue
            if (actual is None or FASES.index(f) > FASES.index(actual)
                    or (f in ALTERNAN and actual in ALTERNAN)):
                self._run["fase"] = f
                self._emitir({"tipo": "fase", "fase": f})

    async def _correr(self, run: dict, prompt: str, lanzador) -> None:
        res: dict = {}
        try:
            try:
                res = await lanzador.correr(prompt, run["modelo"], self._evento) or {}
                estado = "ok" if res.get("estado") == "ok" else "error"
            except Exception as e:  # noqa: BLE001 — se muestra en la UI
                res = {"error": (str(e) or e.__class__.__name__)[:MAX_RESUMEN]}
                estado = "error"
            if estado == "error" and not (self._detenido or self._cerrando):
                # el SIGTERM del cierre mata al hijo antes de que el lifespan lo sepa (excepción, o salida
                # con código 0 sin ResultMessage): se da una gracia para que llegue el cierre
                await asyncio.sleep(self.gracia)
        except asyncio.CancelledError:
            self._terminar("interrumpida", {"error": "el servicio se paró"})
            raise
        if self._cerrando:
            estado = "interrumpida"
        elif self._detenido:
            estado = "detenida"
        self._terminar(estado, res)

    def _terminar(self, estado: str, res: dict) -> None:
        run = self._run
        if run is None or run["estado"] != "en_curso":
            return
        self._emitir({"tipo": "fin", "estado": estado})
        run["estado"] = estado
        run["terminado"] = self.ahora().isoformat(timespec="seconds")
        if res.get("session_id"):
            run["session_id"] = res["session_id"]
        run["resultado"] = {"shorts": self._shorts(run["creado"]), "coste_usd": res.get("coste_usd"),
                            "error": (res.get("error") or None) and str(res["error"])[:MAX_RESUMEN]}
        self._guardar()
        self._notificar(run, estado)

    def _notificar(self, run: dict, estado: str) -> None:
        tanda = run["tipo"] == "tanda"
        if estado == "ok":
            n = len(run["resultado"]["shorts"])
            texto = (f"Tanda terminada: {n} short{'s' if n != 1 else ''}" if tanda
                     else f"Retoque listo: {run['params']['destino']}")
        elif estado == "error":
            texto = f"{'Tanda' if tanda else 'Retoque'} con error: {run['resultado']['error'] or 'sin detalle'}"
        else:
            return
        try:
            self.notificar(texto)
        except Exception:  # noqa: BLE001
            pass

    async def detener(self, id: str) -> None:
        run = self._leer_run(id)
        if run is None:
            raise Fallo(404, "no_encontrado")
        if not (self._run and self._run["id"] == id and self._run["estado"] == "en_curso"):
            raise Fallo(409, "no_en_curso")
        self._detenido = True
        try:
            await self._lanzador.detener()
        except Exception:  # noqa: BLE001 — si el interrupt falla, cerrar() cancela la tarea
            pass

    async def cerrar(self) -> None:
        """Lifespan: el run en curso queda siempre `interrumpida` (la bandera se mira en `_correr`)."""
        self._cerrando = True
        run = self.actual()
        if not run or self._tarea is None:
            return
        try:
            await asyncio.wait_for(self._lanzador.detener(), PLAZO_CIERRE)
        except Exception:  # noqa: BLE001 — el hijo puede estar ya muerto
            pass
        await asyncio.wait({self._tarea}, timeout=PLAZO_CIERRE)
        if not self._tarea.done():
            self._tarea.cancel()
            await asyncio.gather(self._tarea, return_exceptions=True)
