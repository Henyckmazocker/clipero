import shutil

import pytest

from clipero import rutas


@pytest.fixture
def home_tmp(tmp_path):
    """Carpeta de trabajo temporal con la plantilla copiada y `rutas.fijar(tmp_path)` hecho."""
    plantilla = rutas.PKG / "plantilla"
    for src, dst in (("sources.yaml", "sources.yaml"), ("branding.yaml", "branding.yaml"),
                     ("app.yaml", "app.yaml"), ("publicados.csv", "publicados.csv"),
                     ("CLAUDE.md", "CLAUDE.md"), ("gitignore", ".gitignore"),
                     ("skills/tanda/SKILL.md", ".claude/skills/tanda/SKILL.md")):
        (tmp_path / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(plantilla / src, tmp_path / dst)
    (tmp_path / ".clipero").mkdir()
    (tmp_path / ".clipero" / "version").write_text("test\n")
    rutas.fijar(tmp_path)
    yield tmp_path
    rutas.fijar(None)
