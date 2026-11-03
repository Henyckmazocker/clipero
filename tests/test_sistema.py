from clipero import sistema


def test_sin_binarios_no_hace_nada_ni_lanza(monkeypatch):
    monkeypatch.setattr(sistema.shutil, "which", lambda n: None)
    sistema.notificar("t", "c")
    sistema.abrir("/tmp")


def test_con_binarios_los_llama(monkeypatch):
    run, popen = [], []
    monkeypatch.setattr(sistema.shutil, "which", lambda n: f"/bin/{n}")
    monkeypatch.setattr(sistema.subprocess, "run", lambda cmd, **k: run.append(cmd))
    monkeypatch.setattr(sistema.subprocess, "Popen", lambda cmd, **k: popen.append(cmd))
    sistema.notificar("T", "hola")
    sistema.abrir("/tmp/x")
    assert run == [["/bin/notify-send", "-a", "Clipero", "T", "hola"]]
    assert popen == [["/bin/xdg-open", "/tmp/x"]]


def test_fallo_al_lanzar_no_propaga(monkeypatch):
    def roto(*a, **k):
        raise OSError("boom")
    monkeypatch.setattr(sistema.shutil, "which", lambda n: f"/bin/{n}")
    monkeypatch.setattr(sistema.subprocess, "run", roto)
    monkeypatch.setattr(sistema.subprocess, "Popen", roto)
    sistema.notificar("t", "c")
    sistema.abrir("/tmp")
