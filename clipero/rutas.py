"""Dónde viven el código y los datos. El código está en el paquete (`PKG`); los datos, en la carpeta
de trabajo (`home()`, por defecto ~/Clipero). Nada de esto se evalúa al importar: `cli.main` llama a
`fijar()` antes de despachar y todo lo demás pregunta con funciones."""
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
_fijado: Path | None = None


def fijar(home: Path | str | None) -> None:
    """Fija la carpeta de trabajo (opción global `--home`). None = volver a la resolución normal."""
    global _fijado
    _fijado = Path(home).expanduser().resolve() if home else None


def fichero_home() -> Path:
    """Fichero donde `init` apunta la carpeta de trabajo elegida."""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "clipero" / "home"


def home() -> Path:
    """--home → CLIPERO_HOME → primera línea de fichero_home() → ~/Clipero. No crea nada."""
    if _fijado is not None:
        return _fijado
    env = os.environ.get("CLIPERO_HOME")
    if env:
        return Path(env).expanduser().resolve()
    f = fichero_home()
    try:
        linea = f.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        linea = ""
    if linea:
        return Path(linea).expanduser().resolve()
    return Path.home() / "Clipero"


def vods() -> Path:
    return home() / "data" / "vods"


def binario(nombre: str) -> Path:
    return home() / ".clipero" / "bin" / nombre


def version_file() -> Path:
    return home() / ".clipero" / "version"


def fuentes() -> Path:
    return PKG / "recursos" / "fonts"


def modelo_yunet() -> Path:
    return PKG / "recursos" / "models" / "face_detection_yunet_2023mar.onnx"
