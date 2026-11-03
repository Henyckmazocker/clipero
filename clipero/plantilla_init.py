"""`clipero init`: copia la plantilla del paquete a la carpeta de trabajo."""
import shutil
from importlib import metadata
from pathlib import Path

from . import rutas

# (origen dentro de plantilla/, destino dentro de la carpeta de trabajo)
FICHEROS = [
    ("sources.yaml", "sources.yaml"),
    ("branding.yaml", "branding.yaml"),
    ("app.yaml", "app.yaml"),
    ("publicados.csv", "publicados.csv"),
    ("CLAUDE.md", "CLAUDE.md"),
    ("skills/tanda/SKILL.md", ".claude/skills/tanda/SKILL.md"),
    ("gitignore", ".gitignore"),
    ("linea-editorial.md", "linea-editorial.md"),   # del usuario: `init` la crea y `--actualizar` no la toca
] + [(f"examples/{n}.short.yaml", f"examples/{n}.short.yaml")   # referencia de formato de la skill
     for n in ("arco", "momento", "recopilacion", "sin-gancho")]
ACTUALIZABLES = ("CLAUDE.md", ".claude/skills/tanda/SKILL.md") + tuple(d for _, d in FICHEROS if d.startswith("examples/"))
CARPETAS = ("data", "out", "layouts", "brand", ".clipero")


def version() -> str:
    try:
        return metadata.version("clipero")
    except metadata.PackageNotFoundError:
        return "0"


def init(dir_=None, actualizar=False, log=print):
    destino = Path(dir_).expanduser().resolve() if dir_ else rutas.home()
    plantilla = rutas.PKG / "plantilla"
    if actualizar:
        if not (destino / ".clipero").is_dir():
            raise RuntimeError(f"no hay carpeta de trabajo en {destino}: ejecuta `clipero init`")
        for src, dst in FICHEROS:
            if dst in ACTUALIZABLES:
                _copiar(plantilla / src, destino / dst, pisar=True)
                log(f"actualizado {dst}")
    else:
        destino.mkdir(parents=True, exist_ok=True)
        for c in CARPETAS:
            (destino / c).mkdir(exist_ok=True)
        for src, dst in FICHEROS:
            if _copiar(plantilla / src, destino / dst, pisar=False):
                log(f"creado {dst}")
            else:
                log(f"ya existe {dst}: no se toca")
    (destino / ".clipero").mkdir(exist_ok=True)
    v = destino / ".clipero" / "version"
    if actualizar or not v.exists():
        v.write_text(version() + "\n", encoding="utf-8")
    if not actualizar:
        f = rutas.fichero_home()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(str(destino) + "\n", encoding="utf-8")
        log(f"carpeta de trabajo: {destino} (apuntada en {f})")


def _copiar(origen: Path, destino: Path, pisar: bool) -> bool:
    if destino.exists() and not pisar:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return True
