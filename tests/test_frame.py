"""frame.py: filtro de layout sintético, trayectoria de cara y zoompan. Sin red ni vídeo."""
import cv2
import numpy as np
import pytest
import yaml
from pathlib import Path

from clipero import frame

FIXTURES = Path(__file__).parent / "fixtures"

LAYOUT = {"fuente": "x", "entrada": "1920x1080",
          "facecam": {"x": 1440, "y": 0, "w": 480, "h": 360},
          "juego": {"x": 240, "y": 0, "w": 1440, "h": 1080}}


def test_layout_graph_facecam_arriba_juego_abajo():
    g = frame.layout_graph(LAYOUT, 1920, 1080, "0")
    assert "crop=480:360:1440:0,scale=1080:810" in g
    assert "crop=1440:1080:240:0,scale=1080:810" in g
    assert "vstack=inputs=2" in g and "pad=1080:1920:0:0:black" in g
    assert g.index("[ff0][gg0]") > g.index("[gg0]")   # facecam primero = arriba


def test_layout_graph_escala_si_la_fuente_no_es_1080p():
    g = frame.layout_graph(LAYOUT, 1280, 720, "1")
    assert "crop=320:240:960:0" in g and "crop=960:720:160:0" in g


def test_load_layout(tmp_path):
    assert frame.load_layout("nadie", tmp_path) is None
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(LAYOUT))
    assert frame.load_layout("x", tmp_path)["entrada"] == "1920x1080"


def _escribe(path, layout):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(layout))


def test_load_layout_excepcion_por_vod_manda_sobre_el_canal(tmp_path):
    otro = {**LAYOUT, "facecam": {"x": 0, "y": 0, "w": 480, "h": 360}}
    _escribe(tmp_path / "x.yaml", LAYOUT)
    _escribe(tmp_path / "x" / "123.yaml", otro)
    assert frame.load_layout("x", tmp_path, vod="123")["facecam"]["x"] == 0
    assert frame.load_layout("x", tmp_path, vod="123") == otro
    assert frame.layout_path("x", "123", tmp_path) == tmp_path / "x" / "123.yaml"
    assert frame.layout_path("x", None, tmp_path) == tmp_path / "x.yaml"


def test_load_layout_sin_excepcion_vuelve_al_canal(tmp_path):
    _escribe(tmp_path / "x.yaml", LAYOUT)
    _escribe(tmp_path / "x" / "123.yaml", LAYOUT)
    assert frame.load_layout("x", tmp_path, vod="999")["facecam"]["x"] == 1440
    assert frame.load_layout("x", tmp_path)["facecam"]["x"] == 1440
    assert frame.load_layout("y", tmp_path, vod="123") is None


def test_layout_real_de_ibai_sigue_cargando(home_tmp):
    real = Path(__file__).resolve().parent / "fixtures" / "layouts"   # copia del layout real con escenas
    assert frame.has_escenas(frame.load_layout("ibai", layouts_dir=real))


@pytest.mark.parametrize("rect", [
    {"x": 1500, "y": 0, "w": 480, "h": 360},     # se sale por la derecha
    {"x": 0, "y": 800, "w": 100, "h": 300},      # se sale por abajo
    {"x": -1, "y": 0, "w": 100, "h": 100},
    {"x": 0, "y": 0, "w": 0, "h": 100},
    {"x": 0.0, "y": 0, "w": 100, "h": 100},      # float
    {"x": True, "y": 0, "w": 100, "h": 100},     # bool
    {"x": 0, "y": 0, "w": 100},                  # falta h
])
def test_validate_layout_rectangulo_invalido(rect):
    with pytest.raises(RuntimeError, match="facecam"):
        frame.validate_layout({**LAYOUT, "facecam": rect})


def test_validate_layout_rectangulo_fuera_en_escenas_y_load(tmp_path):
    esc = {"entrada": "1920x1080", "escenas": {
        "partida": {"facecam": {"x": 1460, "y": 550, "w": 600, "h": 240},
                    "juego": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
        "plato": {"ancho": True}}}
    with pytest.raises(RuntimeError, match="escenas.partida.facecam"):
        frame.validate_layout(esc)
    _escribe(tmp_path / "x.yaml", esc)
    with pytest.raises(RuntimeError, match="fuera de `entrada`"):
        frame.load_layout("x", tmp_path)


def test_validate_layout_otras_reglas():
    frame.validate_layout(LAYOUT)
    with pytest.raises(RuntimeError, match="falta `entrada`"):
        frame.validate_layout({"facecam": {}, "juego": {}})
    with pytest.raises(RuntimeError, match="falta `juego`"):
        frame.validate_layout({"entrada": "1920x1080", "facecam": LAYOUT["facecam"]})
    with pytest.raises(RuntimeError, match="nombre de escena"):
        frame.validate_layout({"entrada": "1920x1080", "escenas": {"Mala Escena": {"ancho": True}}})


def test_smooth_exponencial_y_huecos():
    s = frame.smooth([None, (1000.0, 100.0), None, (1100.0, 100.0)])
    assert s[0] == s[1] == 1000.0 and s[2] == 1000.0
    assert abs(s[3] - (1000 + 0.15 * 100)) < 1e-9
    assert frame.smooth([None, None]) is None


def test_track_filter_centrado_y_con_trayectoria():
    assert frame.track_filter(None, 1920, 1080).startswith("crop=608:1080:x='656.00':y=0")
    f = frame.track_filter([960.0, 1000.0, 1000.0], 1920, 1080)
    assert "clip((t-0.000)/0.500,0,1)" in f and f.endswith("scale=1080:1920:flags=lanczos")


def test_crop_x_no_se_sale_de_la_imagen():
    e = frame.crop_x_expr([10.0, 1900.0], 0.5, 1920, 608)
    assert e.startswith("0.00") and "+1312.00*" in e   # 1920-608


def test_zoompan_filter():
    assert frame.zoompan_filter([]) == ""
    z = frame.zoompan_filter([{"t": 24.0, "dur": 1.2, "factor": 1.25}])
    assert "zoompan=" in z and "+0.250*clip(" in z and "s=1080x1920" in z


def test_smooth_no_deja_la_cara_fuera_del_recorte():
    # la cara salta 600 px: sin límite el suavizado (α=0,15) iría 510 px por detrás
    muestras = [(1000.0, 200.0), (1600.0, 200.0)]
    assert abs(frame.smooth(muestras)[1] - 1090.0) < 1e-6
    c = frame.smooth(muestras, cw=608)[1]
    assert 1600 - c <= 608 / 2 - 100 - frame.FACE_PAD + 1e-6   # la cara queda a >= pad del borde


# --- escenas ---------------------------------------------------------------------

ESCENAS = {"fuente": "x", "entrada": "1920x1080",
           "escenas": {"partida": {"facecam": {"x": 1460, "y": 550, "w": 460, "h": 240},
                                   "juego": {"x": 0, "y": 0, "w": 1920, "h": 1080}},
                       "plato": {"ancho": True}}}


def test_load_layout_escenas_y_compat(tmp_path):
    (tmp_path / "e.yaml").write_text(yaml.safe_dump(ESCENAS))
    lay = frame.load_layout("e", tmp_path)
    assert frame.has_escenas(lay) and frame.scene_roles(lay) == ("partida", "plato")
    assert not frame.has_escenas(LAYOUT)
    (tmp_path / "m.yaml").write_text(yaml.safe_dump({"entrada": "1920x1080", "escenas": {"a": {"x": 1}}}))
    with pytest.raises(RuntimeError, match="escena `a`"):
        frame.load_layout("m", tmp_path)
    (tmp_path / "n.yaml").write_text(yaml.safe_dump({"entrada": "1920x1080", "juego": LAYOUT["juego"]}))
    with pytest.raises(RuntimeError, match="facecam"):
        frame.load_layout("n", tmp_path)


def test_escenas_graph_corte_limpio_con_enable():
    segs = [(0.0, 3.75, "plato"), (3.75, 8.25, "partida"), (8.25, 12.0, "plato")]
    g = frame.escenas_graph(ESCENAS, 1920, 1080, "0", segs)
    assert "overlay=0:0:enable='between(t,3.750,8.250)'" in g
    assert "crop=460:240:1460:550,scale=1080:574" in g or "crop=460:240:1460:550,scale=1080:56" in g
    assert f"overlay=0:{frame.STRIP_Y}" in g and f"overlay=0:{frame.FACE_Y}" in g
    solo = frame.escenas_graph(ESCENAS, 1920, 1080, "1", [(0.0, 5.0, "plato")])
    assert "enable" not in solo and "crop=460" not in solo and "scale=1080:608" in solo


def test_smooth_scenes_quita_parpadeos():
    P, L = True, False
    assert frame.smooth_scenes([L, L, L, P, L, L, L]) == [L] * 7          # 1 muestra = 0,5 s < 1 s
    assert frame.smooth_scenes([P, L, L, L, L, L]) == [L] * 6             # al principio
    assert frame.smooth_scenes([P, P, P, L, L, L]) == [P, P, P, L, L, L]  # 1,5 s se queda
    assert frame.smooth_scenes([]) == []


def test_scene_segments_cortes_entre_muestras():
    segs = frame.scene_segments([False, False, True, True, True, False], ("partida", "plato"), 3.0)
    assert segs == [(0.0, 0.75, "plato"), (0.75, 2.25, "partida"), (2.25, 3.0, "plato")]
    assert frame.scene_seconds(segs) == {"plato": 1.5, "partida": 1.5}


def _fotograma(partida):
    """Sintético 960×540: fondo con ruido suave; en `partida` un recuadro de marco recto abajo a la derecha."""
    rng = np.random.default_rng(1)
    g = (90 + rng.integers(-2, 3, (540, 960))).astype(np.int16)
    if partida:
        g[255:395, 722:960] = 200 + rng.integers(-2, 3, (140, 238))   # recuadro claro con borde nítido
    return g


def test_edge_score_distingue_partida_de_plato():
    rect = ESCENAS["escenas"]["partida"]["facecam"]
    assert frame.edge_score(_fotograma(True), rect, 0.5, 0.5) >= frame.SCENE_THR
    assert frame.edge_score(_fotograma(False), rect, 0.5, 0.5) < 0.1


def test_edge_score_fotogramas_reales():
    rect = ESCENAS["escenas"]["partida"]["facecam"]
    for nombre, esperado in (("partida_a", True), ("partida_b", True), ("plato", False)):
        # fotograma real reducido a 960×540 y recortado a la esquina (x 640–960, y 200–440), pegado en un lienzo
        # gris: el marco del recuadro cae dentro del recorte y el pegado fuera de la zona de búsqueda
        crop = cv2.imread(str(FIXTURES / f"escena_{nombre}.jpg"), cv2.IMREAD_GRAYSCALE)
        assert crop.shape == (240, 320)
        img = np.full((540, 960), 128, np.int16)
        img[200:440, 640:960] = crop
        assert (frame.edge_score(img, rect, 0.5, 0.5) >= frame.SCENE_THR) is esperado
