"""sistema: lo que hace Clipero con el escritorio de Linux (notificaciones y abrir carpetas). Solo Linux:
si falta `notify-send` o `xdg-open` no hace nada y nunca lanza excepción."""
import shutil
import subprocess
from pathlib import Path


def notificar(titulo: str, cuerpo: str) -> None:
    """`notify-send` si existe."""
    exe = shutil.which("notify-send")
    if not exe:
        return
    try:
        subprocess.run([exe, "-a", "Clipero", titulo, cuerpo], timeout=5, capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def abrir(carpeta) -> None:
    """`xdg-open <carpeta>` si existe."""
    exe = shutil.which("xdg-open")
    if not exe:
        return
    try:
        subprocess.Popen([exe, str(Path(carpeta))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:  # noqa: BLE001
        pass
