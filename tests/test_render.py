"""Validación de short.yaml (tabla de rótulos mínimos), filtros y música. Sin red."""
import copy

import numpy as np
import pytest

from clipero import render
from clipero.render import REGLAS, validate


def base(fmt):
    if fmt == "arco":
        return {"slug": "a", "formato": "arco", "tono": "neutro", "titulo": "t",
                "tramos": [{"vod": "1", "start": 0, "end": 10}, {"vod": "1", "start": 50, "end": 62},
                           {"vod": "1", "start": 90, "end": 100}],
                "rotulos": [{"t": 0, "dur": 2, "tipo": "gancho", "texto": "G"},
                            {"t": 10, "dur": 1.5, "tipo": "transicion", "texto": "T1"}]}
    if fmt == "momento":
        return {"slug": "m", "formato": "momento", "tono": "neutro", "titulo": "t",
                "tramos": [{"vod": "1", "start": 100, "end": 130}],
                "rotulos": [{"t": 0, "dur": 2.5, "tipo": "gancho", "texto": "G"}],
                "zoom": [{"t": 20, "dur": 2, "factor": 1.25}]}
    return {"slug": "r", "formato": "recopilacion", "tono": "neutro", "titulo": "t",
            "tramos": [{"vod": "1", "start": 0, "end": 8}, {"vod": "2", "start": 0, "end": 8},
                       {"vod": "1", "start": 40, "end": 48}],
            "rotulos": [{"t": 0, "dur": 2, "tipo": "gancho", "texto": "G"}]}


@pytest.mark.parametrize("fmt", list(REGLAS))
def test_ejemplo_base_valido(fmt):
    assert validate(base(fmt)) == []


def sin(spec, tipo):
    s = copy.deepcopy(spec)
    s["rotulos"] = [r for r in s["rotulos"] if r["tipo"] != tipo]
    return s


@pytest.mark.parametrize("fmt", list(REGLAS))
def test_formato_sin_gancho_falla(fmt):
    err = validate(sin(base(fmt), "gancho"))
    assert err and any("gancho" in e for e in err)


@pytest.mark.parametrize("fmt", list(REGLAS))
def test_desenlace_y_transicion_son_opcionales(fmt):
    assert validate(sin(sin(base(fmt), "desenlace"), "transicion")) == []
    s = base(fmt)
    s["rotulos"].append({"t": 5, "dur": 1.5, "tipo": "desenlace", "texto": "D"})
    assert validate(s) == []


@pytest.mark.parametrize("fmt", list(REGLAS))
def test_rotulo_numero_ya_no_existe(fmt):
    s = base(fmt)
    s["rotulos"].append({"t": 5, "dur": 1.5, "tipo": "numero", "texto": "1/3 uno"})
    assert any("numero" in e and "ya no existe" in e for e in validate(s))


def test_arco_gancho_en_cero():
    s = base("arco")
    s["rotulos"][0]["t"] = 3
    assert any("t=0" in e for e in validate(s))


def test_momento_zoom_gancho_largo_y_tope():
    s = base("momento")
    s["zoom"] = []
    assert any("zoom" in e for e in validate(s))
    s = base("momento")
    s["tramos"][0]["end"] = 150   # 50 s
    assert any("45" in e for e in validate(s))


def test_recopilacion_vods():
    s = base("recopilacion")
    for t in s["tramos"]:
        t["vod"] = "1"
    assert any("2 VODs" in e for e in validate(s))


def test_arco_vod_distinto_y_cantidad_de_tramos():
    s = base("arco")
    s["tramos"][1]["vod"] = "2"
    assert any("mismo VOD" in e for e in validate(s))
    s = base("arco")
    s["tramos"] = s["tramos"][:1]
    assert any("2–3 tramos" in e for e in validate(s))


@pytest.mark.parametrize("fmt,fin", [("momento", 105), ("momento", 144), ("arco", None)])
def test_duracion_fuera_de_rango_falla(fmt, fin):
    s = base(fmt)
    if fin:
        s["tramos"][0]["end"] = fin       # 5 s (<20) o 44 s…
        if fin == 144:
            s["tramos"][0]["start"] = 80  # 64 s (>59)
    else:
        s["tramos"] = [{"vod": "1", "start": 0, "end": 40}, {"vod": "1", "start": 50, "end": 70}]  # 60 s
    assert any("fuera de 20–59" in e for e in validate(s))


def test_rotulos_solapados_y_fuera_del_short():
    s = base("arco")
    s["rotulos"][1]["t"] = 1.0
    assert any("se solapan" in e for e in validate(s))
    s = base("arco")
    s["rotulos"][1]["t"] = 40
    assert any("fuera del short" in e for e in validate(s))


def test_formato_desconocido_y_voz():
    assert validate({"formato": "otro"})
    s = base("arco")
    s["voz"] = "x.wav"
    assert any("voz" in e for e in validate(s))


def test_creditos_recopilacion_dos_fuentes():
    src = {"a": {"credito": "A (twitch.tv/a)"}, "b": {"credito": "B (twitch.tv/b)"}}
    s = base("recopilacion")
    s["fuente"] = "a"
    assert render.creditos(s, src, {"1": "a", "2": "b"}) == ["A (twitch.tv/a)", "B (twitch.tv/b)"]
    with pytest.raises(RuntimeError):
        render.creditos(s, {"a": {}}, {"1": "a", "2": "a"})


def test_drawtext_texto_con_dos_puntos_comillas_y_porcentaje(tmp_path):
    spec = {"tramos": [{"vod": "1", "start": 0, "end": 30}],
            "rotulos": [{"t": 1, "dur": 2, "tipo": "gancho", "texto": "AL 100%: it's 5:30, ¿vale?"}]}
    fl = render.rotulo_filters(spec, ["Ibai (twitch.tv/ibai)"], tmp_path, 200)
    assert "AL 100%: it's 5:30" in (tmp_path / "rot0.txt").read_text()
    assert "it's" not in fl[0] and "expansion=none" in fl[0]
    assert "Montserrat-ExtraBold.ttf" in fl[0]
    assert "enable='between(t,28.50,30.00)'" in fl[1]


def test_filtergraph_une_tramos_con_concat_y_ass(tmp_path):
    spec = {"tramos": [{"vod": "1", "start": 100, "end": 110}, {"vod": "1", "start": 200, "end": 215}],
            "rotulos": []}
    g = render.build_filtergraph(spec, [(0, 0, 1920, 1080, 95.0), (0, 0, 1920, 1080, 190.0)],
                                 ["crop=608:1080:x='0':y=0,scale=1080:1920", "crop=608:1080:x='5':y=0,scale=1080:1920"],
                                 ["X"], tmp_path / "s.ass", tmp_path, 200, "")
    assert "trim=start=5.000:end=15.000" in g and "atrim=start=10.000:end=25.000" in g
    assert "concat=n=2:v=1:a=1" in g and "ass=" in g and f"fontsdir={render.esc(render.fontsdir())}" in g


def test_musica_aviso_solo_si_sostenida():
    sr = 22050
    rng = np.random.default_rng(0)
    t = np.arange(sr * 12) / sr
    voz = sum(np.sin(2 * np.pi * f * t) for f in (150, 300, 600, 1200, 2400)).astype(np.float32) * 0.2
    assert render.music_warning(render.music_ratios(voz, sr)) is None
    mus = voz + (rng.standard_normal(len(t)) * 0.5).astype(np.float32)   # ruido de banda ancha
    assert "música" in render.music_warning(render.music_ratios(mus, sr))
    corto = voz.copy()
    corto[:sr * 3] += (rng.standard_normal(sr * 3) * 0.5).astype(np.float32)   # solo 3 s
    assert render.music_warning(render.music_ratios(corto, sr)) is None


# --- marca del canal (branding.yaml) ---------------------------------------------

BRAND = {"nombre": "Canal de Ejemplo", "color": "0x2A6FDB", "marca_agua": "«CANAL DE EJEMPLO»",
         "linea_descripcion": "Canal de Ejemplo: clips con comentario.", "hashtag": "#canalejemplo"}


def test_rotulos_con_marca_gancho_rojo_y_marca_de_agua(tmp_path):
    spec = base("arco")
    fl = render.rotulo_filters(spec, ["Ibai (twitch.tv/ibai)"], tmp_path, 200, BRAND)
    assert "x=40:y=26" in fl[0] and (tmp_path / "marca.txt").read_text() == "«CANAL DE EJEMPLO»"
    gancho = [f for f in fl if "rot0.txt" in f][0]
    trans = [f for f in fl if "rot1.txt" in f][0]
    assert "boxcolor=0x2A6FDB@0.92" in gancho and "boxcolor=black@0.7" in trans


def test_rotulos_sin_marca_como_antes(tmp_path):
    fl = render.rotulo_filters(base("arco"), ["Ibai (twitch.tv/ibai)"], tmp_path, 200)
    assert not any("marca.txt" in f for f in fl)
    assert all("0x2A6FDB" not in f for f in fl)


def test_meta_con_marca(tmp_path):
    spec = base("arco") | {"fuente": "ibai", "hashtags": "#ibai #twitch"}
    infos = {"1": ({"upload_date": "20261031"}, "twitch")}
    p = tmp_path / "m.md"
    render.write_meta(p, spec, ["Ibai (twitch.tv/ibai)"], infos, 32.0, "cara", [], BRAND)
    t = p.read_text()
    assert "\\nCanal de Ejemplo: clips con comentario." in t
    assert "**Hashtags:** #canalejemplo #ibai #twitch" in t
    assert "**Formato:** arco · **Tono:** neutro · **Duración:**" in t


def test_tono_ausente_o_inventado_falla():
    for tono in (None, "", "enfadado"):
        spec = base("arco") | {"tono": tono}
        assert any("`tono` obligatorio: critica | positivo | neutro" in e for e in validate(spec))
    spec = base("arco")
    del spec["tono"]
    assert any("`tono` obligatorio" in e and "None" in e for e in validate(spec))


@pytest.mark.parametrize("tono", render.TONOS)
def test_tonos_validos_pasan(tono):
    assert validate(base("arco") | {"tono": tono}) == []


def test_load_branding(tmp_path):
    assert render.load_branding(tmp_path / "no.yaml") is None
    f = tmp_path / "b.yaml"
    f.write_text("nombre: X\nhashtag: '#x'\n")
    assert render.load_branding(f)["hashtag"] == "#x"
