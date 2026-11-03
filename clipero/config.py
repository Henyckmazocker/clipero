"""Lectura/escritura de sources.yaml y branding.yaml conservando comentarios (solo la app).

ruamel.yaml solo lo importa la app y los tests; `render` y `vods` siguen con PyYAML.
La reserva de sources.yaml (desde la línea «# Reserva») se trata como texto: ruamel la
cuelga del último ítem y se perdería al borrarlo.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
from pathlib import Path

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

RESERVA_RE = re.compile(r"^# Reserva", re.M)


def make_yaml() -> YAML:
    y = YAML()  # round-trip
    y.preserve_quotes = True
    y.width = 4096
    return y


def split_sources(text: str) -> tuple[str, str]:
    """(cabeza, cola); la cola empieza en la primera línea «# Reserva» y es "" si no hay."""
    m = RESERVA_RE.search(text)
    if not m:
        return text, ""
    return text[: m.start()], text[m.start():]


def write_atomic(path, text: str) -> None:
    """Escribe `<fichero>.tmp` en el mismo directorio y hace `os.replace`."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --- errores y ficheros ---------------------------------------------------------

class Invalido(ValueError):
    """Resultado no válido: `detalle` lleva un mensaje en español por error (→ 422 en la app)."""

    def __init__(self, detalle):
        self.detalle = list(detalle)
        super().__init__("; ".join(self.detalle))


SOURCES = "sources.yaml"
BRANDING = "branding.yaml"
APP = "app.yaml"
RESERVA_CAB = "# Reserva (sustituyen a un canal que no responda):"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TWITCH_RE = re.compile(r"^[a-z0-9_]{3,25}$")
YOUTUBE_RE = re.compile(r"^https://www\.youtube\.com/@[^/\s]+(/streams)?$")
COLOR_RE = re.compile(r"^0x[0-9A-F]{6}$")
BLOQUE_RE = re.compile(r"^# - id: (\S+)")
CLAVE_RE = re.compile(r"^#   (\w+): (.*)$")
CAMPOS_MARCA = ("nombre", "handle", "lema", "color", "marca_agua", "linea_descripcion", "hashtag")


def _dump(data) -> str:
    buf = io.StringIO()
    make_yaml().dump(data, buf)
    return buf.getvalue()


# --- sources.yaml ---------------------------------------------------------------

def load_sources_rt(root):
    """(CommentedSeq de la cabeza, cola en texto). Las líneas en blanco finales de la cabeza se
    descartan: `save_sources` pone siempre una antes de la cola."""
    text = (Path(root) / SOURCES).read_text(encoding="utf-8")
    cabeza, cola = split_sources(text)
    cabeza = cabeza.rstrip("\n") + "\n" if cabeza.strip() else ""
    seq = make_yaml().load(cabeza) if cabeza else None
    if seq is None:
        seq = make_yaml().load("[]\n")
        seq.fa.set_block_style()
    return seq, cola


def save_sources(root, seq, cola) -> None:
    """Valida el resultado completo y escribe dump(cabeza) + línea en blanco + cola, atómico."""
    errores = []
    ids_reserva = {c["id"] for c in parse_reserva(cola)}
    vistos = set()
    for c in seq:
        cid = c.get("id") if hasattr(c, "get") else None
        errores += validate_canal(c, (vistos | ids_reserva))
        if isinstance(cid, str):
            vistos.add(cid)
    if errores:
        raise Invalido(errores)
    out = _dump(seq) if len(seq) else ""
    if cola:
        if out and not out.endswith("\n\n"):
            out += "\n"
        out += cola
    write_atomic(Path(root) / SOURCES, out)


def nuevo_canal(c: dict):
    """CommentedMap listo para añadir a la cabeza (youtube y credito entre comillas dobles).
    Si `credito` llega vacío se rellena."""
    c = dict(c)
    if not str(c.get("credito") or "").strip():
        c["credito"] = credito_por_defecto(c)
    from ruamel.yaml.comments import CommentedMap
    m = CommentedMap()
    for k in ("id", "nombre", "tamaño", "youtube", "twitch", "credito"):
        v = c.get(k)
        if v in (None, ""):
            continue
        m[k] = DoubleQuotedScalarString(v) if k in ("youtube", "credito") else v
    return m


def credito_por_defecto(c: dict) -> str:
    nombre = str(c.get("nombre") or "").strip()
    if c.get("twitch"):
        return f"{nombre} (twitch.tv/{c['twitch']})"
    return str(c.get("youtube") or "").replace("https://www.", "", 1)


def actualizar_canal(item, datos: dict) -> None:
    """Edita `item` (un CommentedMap de la lista) con `datos`; el `id` no cambia. Los campos
    opcionales (`youtube`, `twitch`) que no vengan se quitan."""
    for k in ("nombre", "tamaño", "youtube", "twitch", "credito"):
        v = datos.get(k)
        if v in (None, ""):
            if k in ("youtube", "twitch") and k in item:
                del item[k]
            continue
        if k in item and item[k] == v:
            continue
        item[k] = DoubleQuotedScalarString(v) if k in ("youtube", "credito") else v


# --- reserva (texto) ------------------------------------------------------------

def _sin_comentario(v: str) -> str:
    """Quita el comentario final `  #…` de un valor, salvo dentro de comillas."""
    q = None
    for i, ch in enumerate(v):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and i > 0 and v[i - 1].isspace():
            return v[:i].rstrip()
    return v.strip()


def parse_reserva(cola: str) -> list[dict]:
    out, cur = [], None
    for ln in cola.splitlines():
        m = BLOQUE_RE.match(ln)
        if m:
            cur = {"id": m.group(1)}
            out.append(cur)
            continue
        m = CLAVE_RE.match(ln)
        if m and cur is not None:
            cur[m.group(1)] = yaml.safe_load(_sin_comentario(m.group(2)))
        else:
            cur = None
    return out


def _valor_yaml(k, v) -> str:
    if isinstance(v, str):
        v = str(v)  # subclases de ruamel (DoubleQuotedScalarString…) → str nativo
    elif isinstance(v, bool):
        v = bool(v)
    elif isinstance(v, int):
        v = int(v)
    if isinstance(v, str) and k in ("youtube", "credito"):
        return json.dumps(v, ensure_ascii=False)
    s = yaml.safe_dump(v, default_flow_style=True, allow_unicode=True, width=4096)
    return s.replace("\n...\n", "").strip()


def a_reserva(cola: str, canal: dict, nota: str) -> str:
    """Inserta el bloque comentado del canal justo tras la línea «# Reserva…» (la crea si falta)."""
    cid = canal["id"]
    cab = f"# - id: {cid}        # {nota}" if nota else f"# - id: {cid}"
    lineas = [cab] + [f"#   {k}: {_valor_yaml(k, v)}" for k, v in canal.items()
                      if k != "id" and v not in (None, "")]
    bloque = "\n".join(lineas) + "\n"
    if not cola.strip():
        return RESERVA_CAB + "\n" + bloque
    if not cola.endswith("\n"):
        cola += "\n"
    i = cola.index("\n") + 1
    return cola[:i] + bloque + cola[i:]


def quitar_de_reserva(cola: str, id: str) -> tuple[str, dict]:
    """Quita el bloque de `id` y devuelve (cola nueva, dict). KeyError si no está."""
    lineas = cola.splitlines(keepends=True)
    for i, ln in enumerate(lineas):
        m = BLOQUE_RE.match(ln)
        if m and m.group(1) == id:
            j = i + 1
            while j < len(lineas) and CLAVE_RE.match(lineas[j].rstrip("\n")):
                j += 1
            canal = next(c for c in parse_reserva("".join(lineas[i:j])))
            return "".join(lineas[:i] + lineas[j:]), canal
    raise KeyError(id)


def validate_canal(c: dict, ids_existentes) -> list[str]:
    e = []
    cid = c.get("id")
    if not isinstance(cid, str) or not ID_RE.match(cid):
        e.append("id: solo minúsculas, números y guiones, empezando por letra o número")
    elif cid in ids_existentes:
        e.append(f"id: «{cid}» ya existe (activos o reserva)")
    for k, nombre in (("nombre", "nombre"), ("credito", "crédito")):
        v = c.get(k)
        if not isinstance(v, str) or not v.strip():
            e.append(f"{k}: no puede estar vacío" + (" (el render lo exige)" if k == "credito" else ""))
    if c.get("tamaño") not in ("grande", "mediano"):
        e.append("tamaño: tiene que ser «grande» o «mediano»")
    tw, yt = c.get("twitch"), c.get("youtube")
    if not tw and not yt:
        e.append("twitch/youtube: hace falta al menos uno de los dos")
    if tw and (not isinstance(tw, str) or not TWITCH_RE.match(tw)):
        e.append("twitch: de 3 a 25 caracteres, minúsculas, números o «_»")
    if yt and (not isinstance(yt, str) or not YOUTUBE_RE.match(yt)):
        e.append("youtube: tiene que ser https://www.youtube.com/@canal (opcional /streams)")
    return e


# --- app.yaml -------------------------------------------------------------------

# Si app.yaml no existe se parte de esto (las constantes del M2); el primer guardado lo crea.
APP_DEFAULT_TEXT = """\
# Valores por defecto del formulario de Tanda (los edita la app en Configuración › Tanda).
claude:
  modo: ninguno     # ninguno | api_key | suscripcion (Configuración › Claude)
tanda:
  clips: 5          # 1-10, máximo por tanda
  dias: 7           # 1-30, ventana de `vods`
  editorial: mixta  # mixta | positiva | critica
  modelo: claude-opus-5-5
modelos:            # opciones del selector de modelo
  - claude-opus-5-5
  - sonnet
  - haiku
"""
EDITORIALES = ("mixta", "positiva", "critica")
MODOS_CLAUDE = ("ninguno", "api_key", "suscripcion")


def _yaml_app() -> YAML:
    y = make_yaml()
    y.indent(mapping=2, sequence=4, offset=2)   # «  - modelo» bajo `modelos:`, como en el fichero
    return y


def load_app_rt(root):
    p = Path(root) / APP
    return _yaml_app().load(p.read_text(encoding="utf-8") if p.exists() else APP_DEFAULT_TEXT)


def app_values(rt) -> dict:
    """app.yaml (cargado) → {clips, dias, editorial, modelo, modelos} con tipos planos."""
    t = rt.get("tanda") or {}
    return {"clips": t.get("clips"), "dias": t.get("dias"), "editorial": t.get("editorial"),
            "modelo": t.get("modelo"), "modelos": [str(m) for m in (rt.get("modelos") or [])]}


def load_app(root) -> dict:
    return app_values(load_app_rt(root))


def modo_claude(root) -> str:
    """`app.yaml › claude.modo`; sin la clave (app.yaml viejo), sin fichero o con un valor raro → «ninguno»."""
    try:
        modo = (load_app_rt(root).get("claude") or {}).get("modo")
    except Exception:  # noqa: BLE001 — un app.yaml roto no debe tumbar la app
        return "ninguno"
    return modo if modo in MODOS_CLAUDE else "ninguno"


def _entero(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_app(d: dict) -> list[str]:
    e = []
    if not _entero(d.get("clips")) or not 1 <= d["clips"] <= 10:
        e.append("clips: de 1 a 10")
    if not _entero(d.get("dias")) or not 1 <= d["dias"] <= 30:
        e.append("dias: de 1 a 30")
    if d.get("editorial") not in EDITORIALES:
        e.append("editorial: mixta, positiva o critica")
    modelos = d.get("modelos")
    ok = isinstance(modelos, list) and modelos and all(isinstance(m, str) and m.strip() for m in modelos)
    if not ok:
        e.append("modelos: tiene que haber al menos un modelo (texto no vacío)")
    elif len(set(modelos)) != len(modelos):
        e.append("modelos: sin repetidos")
    if not isinstance(d.get("modelo"), str) or (ok and d["modelo"] not in modelos):
        e.append("modelo: tiene que estar en la lista de modelos")
    if "modo" in d and d["modo"] not in MODOS_CLAUDE:
        e.append("modo: ninguno, api_key o suscripcion")
    return e


def save_app(root, data) -> None:
    """Valida `data` ({clips,dias,editorial,modelo,modelos[,modo]}) y lo fusiona en app.yaml (conserva comentarios).
    `modo` (claude.modo) es opcional: sin él, el bloque `claude` se deja como esté."""
    errores = validate_app(data)
    if errores:
        raise Invalido(errores)
    rt = load_app_rt(root)
    if "modo" in data:
        if rt.get("claude") is None:
            rt.insert(0, "claude", {})
        if rt["claude"].get("modo") != data["modo"]:
            rt["claude"]["modo"] = data["modo"]
    t = rt["tanda"]
    for k in ("clips", "dias", "editorial", "modelo"):
        if t.get(k) != data[k]:
            t[k] = data[k]
    if [str(m) for m in rt["modelos"]] != data["modelos"]:
        rt["modelos"][:] = data["modelos"]
    buf = io.StringIO()
    _yaml_app().dump(rt, buf)
    write_atomic(Path(root) / APP, buf.getvalue())


# --- credenciales de Claude -------------------------------------------------------

CREDENCIALES = Path(".clipero") / "credenciales"


def _leer_credenciales(root) -> dict:
    try:
        d = json.loads((Path(root) / CREDENCIALES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def api_key_origen(root) -> tuple[str | None, str | None]:
    """(clave, origen): la variable ANTHROPIC_API_KEY manda sobre el fichero de credenciales."""
    env = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if env:
        return env, "entorno"
    f = _leer_credenciales(root).get("anthropic_api_key")
    if isinstance(f, str) and f.strip():
        return f.strip(), "fichero"
    return None, None


def api_key(root) -> str | None:
    return api_key_origen(root)[0]


def guardar_api_key(root, clave: str | None) -> None:
    """Guarda la clave en `<root>/.clipero/credenciales` (JSON, 0600); None o «» la borra."""
    ruta = Path(root) / CREDENCIALES
    datos = _leer_credenciales(root)
    clave = (clave or "").strip()
    if clave:
        datos["anthropic_api_key"] = clave
    else:
        datos.pop("anthropic_api_key", None)
    if not datos:
        ruta.unlink(missing_ok=True)
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.unlink(missing_ok=True)   # un .tmp que ya existiera conservaría su modo: la clave nace siempre con 0600
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(datos))
    os.replace(tmp, ruta)


def claude_estado(root) -> dict:
    """Cuerpo de GET /api/config/claude. La clave nunca sale: solo si está puesta y de dónde."""
    cli = shutil.which("claude")
    clave, origen = api_key_origen(root)
    return {"modo": modo_claude(root),
            "disponibles": {"api_key": clave is not None, "suscripcion": cli is not None},
            "clave": {"puesta": clave is not None, "origen": origen},
            "claude_cli": cli}


# --- branding.yaml --------------------------------------------------------------

def load_branding_rt(root):
    return make_yaml().load((Path(root) / BRANDING).read_text(encoding="utf-8"))


def validate_branding(b: dict) -> list[str]:
    e = []
    if not isinstance(b.get("nombre"), str) or not b["nombre"].strip():
        e.append("nombre: no puede estar vacío")
    if not isinstance(b.get("color"), str) or not COLOR_RE.match(b["color"]):
        e.append("color: tiene que ser 0xRRGGBB en mayúsculas")
    for k in CAMPOS_MARCA:
        if k not in ("nombre", "color") and b.get(k) is not None and not isinstance(b[k], str):
            e.append(f"{k}: tiene que ser texto")
    h = b.get("hashtag")
    if isinstance(h, str) and h and (not h.startswith("#") or len(h.split()) != 1):
        e.append("hashtag: tiene que empezar por # y no llevar espacios")
    return e


def save_branding(root, data) -> None:
    """Valida `data` y lo fusiona en el branding.yaml cargado (conserva comentarios)."""
    errores = validate_branding(data)
    if errores:
        raise Invalido(errores)
    rt = load_branding_rt(root)
    for k in list(rt.keys()):
        if k not in data:
            del rt[k]
    for k, v in data.items():
        if k in rt and rt[k] == v:
            continue
        rt[k] = DoubleQuotedScalarString(v) if isinstance(v, str) else v
    write_atomic(Path(root) / BRANDING, _dump(rt))
