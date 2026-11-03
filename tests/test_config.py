import io
import re
from pathlib import Path

import pytest

pytest.importorskip("ruamel.yaml")
from clipero import config  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "config"


def _dump(data) -> str:
    buf = io.StringIO()
    config.make_yaml().dump(data, buf)
    return buf.getvalue()


def _load(text):
    return config.make_yaml().load(text)


def _fixture(nombre):
    return (FIX / nombre).read_text(encoding="utf-8")


def test_sources_cabeza_identica():
    cabeza, cola = config.split_sources(_fixture("sources.yaml"))
    assert cola.startswith("# Reserva")
    assert _dump(_load(cabeza)) == cabeza


def test_branding_identico():
    texto = _fixture("branding.yaml")
    assert _dump(_load(texto)) == texto


def test_ibai_igual_salvo_juego():
    texto = _fixture("ibai.yaml")
    salida = _dump(_load(texto))
    assert salida != texto
    # solo cambia la alineación de la línea `juego:` (espacios tras `juego:` y antes del comentario)
    norm = lambda t: "\n".join(  # noqa: E731
        re.sub(r" +", " ", ln) if ln.lstrip().startswith("juego:") else ln
        for ln in t.splitlines())
    assert norm(salida) == norm(texto)
    a, b = texto.splitlines(), salida.splitlines()
    difieren = [x for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(difieren) == 1 and "juego:" in difieren[0]


def test_split_sin_reserva():
    assert config.split_sources("- id: a\n") == ("- id: a\n", "")


def _cola_fixture():
    return config.split_sources(_fixture("sources.yaml"))[1]


def _recomponer(seq, cola):
    return _dump(seq) + cola


def test_quitar_ultimo_deja_cola_intacta():
    cabeza, cola = config.split_sources(_fixture("sources.yaml"))
    seq = _load(cabeza)
    assert seq[-1]["id"] == "gerardromero"
    del seq[-1]
    nuevo = _recomponer(seq, cola)
    c2, cola2 = config.split_sources(nuevo)
    assert "gerardromero" not in c2
    assert cola2 == cola
    assert len(cola2.splitlines()) == len(_cola_fixture().splitlines())
    assert cola2.splitlines() == _cola_fixture().splitlines()


def test_quitar_primero_deja_cola_y_comentarios():
    cabeza, cola = config.split_sources(_fixture("sources.yaml"))
    seq = _load(cabeza)
    assert seq[0]["id"] == "ibai"
    del seq[0]
    nuevo = _recomponer(seq, cola)
    c2, cola2 = config.split_sources(nuevo)
    assert cola2 == cola
    assert [c["id"] for c in _load(c2)][0] == "elxokas"
    # los comentarios en línea del primero (# slug, …) se van con él
    assert "# slug, también nombre" not in c2


def test_insertar_en_medio_deja_cola_intacta():
    cabeza, cola = config.split_sources(_fixture("sources.yaml"))
    seq = _load(cabeza)
    nuevo_canal = {"id": "prueba", "nombre": "Prueba", "tamaño": "mediano",
                   "twitch": "prueba", "credito": "Prueba (twitch.tv/prueba)"}
    seq.insert(5, nuevo_canal)
    nuevo = _recomponer(seq, cola)
    c2, cola2 = config.split_sources(nuevo)
    assert cola2 == cola
    ids = [c["id"] for c in _load(c2)]
    assert ids[5] == "prueba" and len(ids) == 11
    assert [i for i in ids if i != "prueba"] == [c["id"] for c in _load(cabeza)]


def test_write_atomic(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("viejo")
    config.write_atomic(f, "nuevo")
    assert f.read_text() == "nuevo"
    assert not (tmp_path / "x.yaml.tmp").exists()


# --- M1: alta, edición, reserva, validaciones -------------------------------------

import shutil  # noqa: E402


@pytest.fixture
def root(tmp_path):
    shutil.copy(FIX / "sources.yaml", tmp_path / "sources.yaml")
    shutil.copy(FIX / "branding.yaml", tmp_path / "branding.yaml")
    return tmp_path


CANAL = {"id": "prueba", "nombre": "Prueba", "tamaño": "mediano", "twitch": "prueba", "credito": ""}


def test_alta_al_final_con_cola_intacta(root):
    seq, cola = config.load_sources_rt(root)
    seq.append(config.nuevo_canal(CANAL))
    config.save_sources(root, seq, cola)
    texto = (root / "sources.yaml").read_text()
    c2, cola2 = config.split_sources(texto)
    assert cola2 == cola
    assert c2.endswith("\n\n")
    ids = [c["id"] for c in _load(c2)]
    assert ids[-1] == "prueba" and len(ids) == 11
    nuevo = _load(c2)[-1]
    assert nuevo["credito"] == "Prueba (twitch.tv/prueba)"
    assert 'credito: "Prueba (twitch.tv/prueba)"' in c2
    import yaml
    assert yaml.safe_load(texto)[-1]["twitch"] == "prueba"
    # el resto del fichero no cambia
    original = _fixture("sources.yaml")
    assert texto.startswith(original.split("# Reserva")[0].rstrip("\n"))


def test_edicion_no_cambia_el_id(root):
    seq, cola = config.load_sources_rt(root)
    antes = (root / "sources.yaml").read_text()
    config.actualizar_canal(seq[1], {"id": "otro", "nombre": "Xokas", "tamaño": "grande",
                                     "twitch": "elxokas", "credito": "elxokas (twitch.tv/elxokas)"})
    config.save_sources(root, seq, cola)
    despues = (root / "sources.yaml").read_text()
    assert seq[1]["id"] == "elxokas"
    dif = [(a, b) for a, b in zip(antes.splitlines(), despues.splitlines()) if a != b]
    assert len(dif) == 1 and "nombre: Xokas" in dif[0][1]
    assert len(antes.splitlines()) == len(despues.splitlines())


def test_quitar_ultimo_deja_una_linea_en_blanco_antes_de_reserva(root):
    seq, cola = config.load_sources_rt(root)
    del seq[-1]
    config.save_sources(root, seq, cola)
    texto = (root / "sources.yaml").read_text()
    i = texto.index("# Reserva")
    assert texto[:i].endswith("\n\n") and not texto[:i].endswith("\n\n\n")
    assert texto[i:] == cola
    # y sigue siendo estable al guardar otra vez
    seq, cola = config.load_sources_rt(root)
    config.save_sources(root, seq, cola)
    assert (root / "sources.yaml").read_text() == texto


def test_guardar_sin_cambios_es_identico(root):
    antes = (root / "sources.yaml").read_text()
    seq, cola = config.load_sources_rt(root)
    config.save_sources(root, seq, cola)
    assert (root / "sources.yaml").read_text() == antes


def test_save_valida_y_no_toca_el_fichero(root):
    antes = (root / "sources.yaml").read_text()
    seq, cola = config.load_sources_rt(root)
    seq.append(config.nuevo_canal({**CANAL, "id": "ibai"}))  # repetido
    with pytest.raises(config.Invalido) as ei:
        config.save_sources(root, seq, cola)
    assert any("ya existe" in m for m in ei.value.detalle)
    seq.pop()
    seq.append(config.nuevo_canal({**CANAL, "id": "ampeterby7"}))  # está en la reserva
    with pytest.raises(config.Invalido):
        config.save_sources(root, seq, cola)
    assert (root / "sources.yaml").read_text() == antes


def test_parse_reserva_fixture():
    r = config.parse_reserva(_cola_fixture())
    assert len(r) == 1
    assert r[0] == {"id": "ampeterby7", "nombre": "Ampeterby7", "tamaño": "mediano",
                    "twitch": "ampeterby7", "credito": "Ampeterby7 (twitch.tv/ampeterby7)"}
    assert len(r[0]) == 5


def test_a_reserva_parse_y_quitar_ida_y_vuelta():
    cola = _cola_fixture()
    canal = {"id": "knekro", "nombre": "Knekro", "tamaño": "mediano", "twitch": "knekro",
             "credito": "Knekro (twitch.tv/knekro)"}
    nueva = config.a_reserva(cola, canal, "a reserva el 2026-11-05")
    lineas = nueva.splitlines()
    assert lineas[0] == cola.splitlines()[0]
    assert lineas[1] == "# - id: knekro        # a reserva el 2026-11-05"
    assert lineas[2] == "#   nombre: Knekro"
    assert '#   credito: "Knekro (twitch.tv/knekro)"' in lineas
    assert [c["id"] for c in config.parse_reserva(nueva)] == ["knekro", "ampeterby7"]
    assert config.parse_reserva(nueva)[0] == canal
    sin, q = config.quitar_de_reserva(nueva, "knekro")
    assert q == canal and sin == cola
    sin2, q2 = config.quitar_de_reserva(nueva, "ampeterby7")
    assert q2["twitch"] == "ampeterby7"
    assert "ampeterby7" not in sin2 and "Sustituidos el 2026-11-02" in sin2
    with pytest.raises(KeyError):
        config.quitar_de_reserva(cola, "nadie")


def test_reserva_con_youtube_y_comentario_en_comillas():
    canal = {"id": "z", "nombre": "Z # raro", "tamaño": "grande",
             "youtube": "https://www.youtube.com/@Z/streams", "credito": "Z (youtube.com/@Z)"}
    cola = config.a_reserva("", canal, "")
    assert cola.startswith("# Reserva (sustituyen a un canal que no responda):\n# - id: z\n")
    assert config.parse_reserva(cola) == [canal]


def test_baja_y_reactivacion_de_extremo_a_extremo(root):
    original = (root / "sources.yaml").read_text()
    seq, cola = config.load_sources_rt(root)
    canal = dict(seq[5])
    del seq[5]
    cola = config.a_reserva(cola, canal, "a reserva el 2026-11-05")
    config.save_sources(root, seq, cola)
    import yaml
    assert "knekro" not in [c["id"] for c in yaml.safe_load((root / "sources.yaml").read_text())]
    seq, cola = config.load_sources_rt(root)
    cola, c = config.quitar_de_reserva(cola, "knekro")
    seq.append(config.nuevo_canal(c))
    config.save_sources(root, seq, cola)
    ids = [x["id"] for x in yaml.safe_load((root / "sources.yaml").read_text())]
    assert ids[-1] == "knekro" and len(ids) == 10


def test_sin_cola_la_primera_baja_crea_reserva(tmp_path):
    (tmp_path / "sources.yaml").write_text("- id: a\n  nombre: A\n  tamaño: grande\n  twitch: aaa\n"
                                           "  credito: \"A\"\n- id: b\n  nombre: B\n  tamaño: grande\n"
                                           "  twitch: bbb\n  credito: \"B\"\n")
    seq, cola = config.load_sources_rt(tmp_path)
    assert cola == ""
    canal = dict(seq[1])
    del seq[1]
    config.save_sources(tmp_path, seq, config.a_reserva(cola, canal, "baja"))
    texto = (tmp_path / "sources.yaml").read_text()
    assert texto.endswith('\n\n# Reserva (sustituyen a un canal que no responda):\n# - id: b        # baja\n'
                          '#   nombre: B\n#   tamaño: grande\n#   twitch: bbb\n#   credito: "B"\n')


@pytest.mark.parametrize("cambio,frag", [
    ({"id": "Mal Id"}, "id:"),
    ({"id": "-x"}, "id:"),
    ({"id": "ibai"}, "ya existe"),
    ({"nombre": " "}, "nombre:"),
    ({"credito": ""}, "credito:"),
    ({"tamaño": "enorme"}, "tamaño:"),
    ({"twitch": "", "youtube": ""}, "al menos uno"),
    ({"twitch": "AB"}, "twitch:"),
    ({"twitch": "Mayus"}, "twitch:"),
    ({"youtube": "https://youtube.com/@x"}, "youtube:"),
    ({"youtube": "https://www.youtube.com/@x/videos"}, "youtube:"),
])
def test_validate_canal_cada_regla(cambio, frag):
    base = {"id": "nuevo", "nombre": "N", "tamaño": "grande", "twitch": "nuevo", "credito": "N"}
    assert config.validate_canal(base, {"ibai"}) == []
    errs = config.validate_canal({**base, **cambio}, {"ibai"})
    assert errs and any(frag in e for e in errs)


def test_validate_canal_youtube_valido_sin_twitch():
    c = {"id": "y", "nombre": "Y", "tamaño": "mediano", "credito": "Y",
         "youtube": "https://www.youtube.com/@Y/streams"}
    assert config.validate_canal(c, set()) == []
    assert config.validate_canal({**c, "youtube": "https://www.youtube.com/@Y"}, set()) == []


def test_credito_por_defecto():
    assert config.nuevo_canal({**CANAL})["credito"] == "Prueba (twitch.tv/prueba)"
    c = config.nuevo_canal({"id": "y", "nombre": "Y", "tamaño": "grande",
                            "youtube": "https://www.youtube.com/@Y"})
    assert c["credito"] == "youtube.com/@Y"


BRAND = {"nombre": "N", "color": "0x2A6FDB", "hashtag": "#n", "handle": "@n"}


@pytest.mark.parametrize("cambio,frag", [
    ({"nombre": ""}, "nombre:"),
    ({"color": "#2A6FDB"}, "color:"),
    ({"color": "0xe0201b"}, "color:"),
    ({"color": "0xE0201"}, "color:"),
    ({"hashtag": "n"}, "hashtag:"),
    ({"hashtag": "#a b"}, "hashtag:"),
    ({"lema": 5}, "lema:"),
    ({"marca_agua": ["x"]}, "marca_agua:"),
])
def test_validate_branding_cada_regla(cambio, frag):
    assert config.validate_branding(BRAND) == []
    errs = config.validate_branding({**BRAND, **cambio})
    assert errs and any(frag in e for e in errs)


def test_save_branding_conserva_comentarios(root):
    b = dict(config.load_branding_rt(root))
    b["color"] = "0x112233"
    config.save_branding(root, b)
    antes, despues = _fixture("branding.yaml").splitlines(), (root / "branding.yaml").read_text().splitlines()
    dif = [(x, y) for x, y in zip(antes, despues) if x != y]
    assert len(antes) == len(despues) and len(dif) == 1
    assert '"0x112233"' in dif[0][1] and "# azul de la marca" in dif[0][1]


def test_save_branding_invalido_no_escribe(root):
    antes = (root / "branding.yaml").read_text()
    with pytest.raises(config.Invalido):
        config.save_branding(root, {"nombre": "", "color": "rojo"})
    assert (root / "branding.yaml").read_text() == antes


def test_a_reserva_con_valores_entre_comillas_de_ruamel(root):
    texto = (root / "sources.yaml").read_text().replace(
        "nombre: Knekro", 'nombre: "A"').replace("twitch: knekro", 'twitch: "abc"')
    (root / "sources.yaml").write_text(texto)
    seq, cola = config.load_sources_rt(root)
    assert type(seq[5]["nombre"]).__name__ == "DoubleQuotedScalarString"
    canal = dict(seq[5])
    nueva = config.a_reserva(cola, canal, "")
    assert config.parse_reserva(nueva)[0] == {k: str(v) for k, v in canal.items()}
    assert config.parse_reserva(nueva)[0]["nombre"] == "A"


# --- M5: app.yaml -----------------------------------------------------------------

APP_TXT = """\
# Valores por defecto del formulario de Tanda (los edita la app en Configuración › Tanda).
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
APP = {"clips": 5, "dias": 7, "editorial": "mixta", "modelo": "claude-opus-5-5",
       "modelos": ["claude-opus-5-5", "sonnet", "haiku"]}


def test_app_sin_fichero_usa_las_constantes(tmp_path):
    assert config.load_app(tmp_path) == APP


@pytest.mark.parametrize("cambio,frag", [
    ({"clips": 0}, "clips:"), ({"clips": 11}, "clips:"), ({"clips": True}, "clips:"),
    ({"dias": 0}, "dias:"), ({"dias": 31}, "dias:"), ({"dias": "7"}, "dias:"),
    ({"editorial": "rara"}, "editorial:"),
    ({"modelo": "gpt"}, "modelo:"),
    ({"modelos": []}, "modelos:"),
    ({"modelos": ["a", "a"], "modelo": "a"}, "modelos:"),
])
def test_validate_app_cada_regla(cambio, frag):
    assert config.validate_app(APP) == []
    errs = config.validate_app({**APP, **cambio})
    assert errs and any(frag in e for e in errs)


def test_save_app_conserva_comentarios(tmp_path):
    (tmp_path / "app.yaml").write_text(APP_TXT)
    config.save_app(tmp_path, {**APP, "clips": 3, "modelo": "sonnet"})
    antes, despues = APP_TXT.splitlines(), (tmp_path / "app.yaml").read_text().splitlines()
    dif = [(x, y) for x, y in zip(antes, despues) if x != y]
    assert len(antes) == len(despues) and len(dif) == 2
    assert dif[0][1].startswith("  clips: 3") and "# 1-10, máximo por tanda" in dif[0][1]
    assert dif[1][1] == "  modelo: sonnet"
    assert config.load_app(tmp_path)["clips"] == 3


def test_save_app_cambia_modelos_y_conserva_su_comentario(tmp_path):
    (tmp_path / "app.yaml").write_text(APP_TXT)
    config.save_app(tmp_path, {**APP, "modelos": ["claude-opus-5-5", "haiku", "nuevo"]})
    t = (tmp_path / "app.yaml").read_text()
    assert "modelos:            # opciones del selector de modelo" in t
    assert config.load_app(tmp_path)["modelos"] == ["claude-opus-5-5", "haiku", "nuevo"]


def test_save_app_restaurar_deja_el_fichero_identico(tmp_path):
    (tmp_path / "app.yaml").write_text(APP_TXT)
    config.save_app(tmp_path, {**APP, "clips": 3, "modelo": "sonnet"})
    config.save_app(tmp_path, APP)
    assert (tmp_path / "app.yaml").read_text() == APP_TXT


def test_save_app_sin_fichero_lo_crea_con_comentarios(tmp_path):
    config.save_app(tmp_path, {**APP, "dias": 3})
    t = (tmp_path / "app.yaml").read_text()
    assert t.startswith("# Valores por defecto") and "dias: 3 " in t


def test_save_app_invalido_no_escribe(tmp_path):
    (tmp_path / "app.yaml").write_text(APP_TXT)
    with pytest.raises(config.Invalido) as e:
        config.save_app(tmp_path, {**APP, "clips": 50, "modelo": "gpt"})
    assert len(e.value.detalle) == 2
    assert (tmp_path / "app.yaml").read_text() == APP_TXT
