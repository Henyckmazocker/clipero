import csv
import os
import time

from clipero import stats as st
from clipero.sources import clean_seg, mediana_canal, puntua, recent_vods

CSV = ("fecha,slug,fuente,formato,vod_id,start,end,url\n"
       "2026-11-02,a,ibai,arco,x,1,2,\n"
       "2026-11-02,b,ibai,arco,x,1,2,https://www.youtube.com/watch?v=AAA\n"
       "2026-11-02,c,ibai,arco,x,1,2,https://www.youtube.com/watch?v=BBB#claim\n")


def test_load_publicados(tmp_path):
    p = tmp_path / "pub.csv"
    p.write_text(CSV)
    assert st.load_publicados(p) == [("b", "https://www.youtube.com/watch?v=AAA", False),
                                     ("c", "https://www.youtube.com/watch?v=BBB", True)]


def test_stats_escribe_y_no_duplica(tmp_path):
    pub, pil = tmp_path / "pub.csv", tmp_path / "pil.csv"
    pub.write_text(CSV)
    pedidas = []

    def fake(url):
        pedidas.append(url)
        if "BBB" in url and len(pedidas) > 5:
            raise RuntimeError("no debería")
        return {"vistas": 10, "likes": "", "comentarios": 2, "suscriptores_canal": 99}

    st.stats(pub, pil, hoy="2026-11-03", fetch=fake)
    assert pedidas == ["https://www.youtube.com/watch?v=AAA", "https://www.youtube.com/watch?v=BBB"]
    rows = list(csv.DictReader(open(pil)))
    assert list(rows[0]) == st.PILOTO_COLS
    assert [(r["slug"], r["claim"], r["vistas"], r["likes"]) for r in rows] == [
        ("b", "0", "10", ""), ("c", "1", "10", "")]
    st.stats(pub, pil, hoy="2026-11-03", fetch=fake)  # mismo día: nada nuevo, ni se pide
    assert len(pedidas) == 2 and len(list(csv.DictReader(open(pil)))) == 2
    st.stats(pub, pil, hoy="2026-11-04", fetch=fake)  # otro día: filas nuevas, una sola cabecera
    assert len(list(csv.DictReader(open(pil)))) == 4
    assert open(pil).read().count("fecha_medida") == 1


def test_stats_url_que_falla_no_tumba(tmp_path):
    pub, pil = tmp_path / "pub.csv", tmp_path / "pil.csv"
    pub.write_text(CSV)

    def fake(url):
        if "AAA" in url:
            raise RuntimeError("privado")
        return {"vistas": 1, "likes": 1, "comentarios": 1, "suscriptores_canal": 1}

    nuevas = st.stats(pub, pil, hoy="2026-11-03", fetch=fake)
    assert [r["slug"] for r in nuevas] == ["c"]


def test_vods_filtra_fecha_e_ingeridos():
    now = 1_800_000_000
    d = 86400
    fechas = {  # url → (id, timestamp)
        "t1": ("v1", now - 1 * d), "t2": ("v2", now - 3 * d), "t3": ("v3", now - 9 * d),
        "y1": ("Y1", now - 2 * d), "y2": ("Y2", now - 20 * d), "y3": ("Y3", now - 30 * d),
    }
    listas = {"https://www.twitch.tv/ibai/videos?filter=archives&sort=time": ["t1", "t2", "t3"],
              "https://yt/streams": ["y1", "y2", "y3"]}
    vistas = {"t1": 100, "t2": 100, "t3": 100, "y1": 300, "y2": 100, "y3": 100}  # y1: 3× su mediana (100)
    llamadas = []

    def flat(url):
        return [{"url": u, "view_count": vistas[u]} for u in listas[url]]

    def info(u):
        llamadas.append(u)
        i, ts = fechas[u]
        return {"id": i, "timestamp": ts, "duration": 3600, "webpage_url": u, "title": "t"}

    src = [{"id": "ibai", "twitch": "ibai", "youtube": "https://yt/streams"}]
    res = recent_vods(src, 7, now=now, ingeridos={"2"}, flat=flat, info=info)
    # v2 ya ingerido; v3/Y2 fuera de fecha. Y1: 3× de hace 2 días (1,5) gana a v1: 1× de hace 1 día (0,707)
    assert [r["vod_id"] for r in res] == ["Y1", "1"]
    assert [(r["score"], r["rel"], r["vistas"]) for r in res] == [(1.5, 3.0, 300), (0.707, 1.0, 100)]
    assert "t3" in llamadas and len(llamadas) == 5  # y3 no se pide: el break corta en Y2


def test_vods_empate_twitch_antes_y_vistas_del_info():
    now = 1_800_000_000
    flat = lambda url: [{"url": "x", "view_count": 10}]
    info = lambda u: {"id": "1" if "tw" in u else "Y", "timestamp": now, "webpage_url": u, "view_count": 10}
    src = [{"id": "a", "twitch": "a", "youtube": "https://yt/s"}]
    res = recent_vods(src, 7, now=now, ingeridos=set(), flat=lambda u: [{"url": "tw" + u, "view_count": 10}], info=info)
    assert [r["plataforma"] for r in res] == ["twitch", "youtube"]
    assert [r["score"] for r in res] == [1.0, 1.0]


def test_mediana_canal_ignora_directos_y_none():
    e = [{"view_count": 10}, {"view_count": 30}, {"view_count": 1000, "live_status": "is_live"},
         {"view_count": 5000, "live_status": "is_upcoming"}, {"view_count": None}, {}, {"view_count": 20}]
    assert mediana_canal(e) == 20
    assert mediana_canal([{"view_count": 10}, {"view_count": 30}]) == 20
    assert mediana_canal([{"view_count": None}, {"view_count": 5, "live_status": "is_live"}]) is None
    assert mediana_canal([{"view_count": 0}]) is None
    assert mediana_canal([]) is None


def test_puntua_rel_y_peso_por_edad():
    now, d = 1_800_000_000, 86400
    assert puntua(300, None, now, now) == (1.0, 1.0)
    assert puntua(None, 100, now, now) == (1.0, 1.0)
    assert puntua(300, 100, now, now) == (3.0, 3.0)
    assert puntua(100, 100, now - 2 * d, now) == (0.5, 1.0)
    assert puntua(100, 100, now - 7 * d, now) == (0.088, 1.0)
    assert puntua(100, 100, now + d, now) == (1.0, 1.0)  # fecha futura: edad 0


def test_puntua_criterio_recencia_vs_repercusion():
    now, d = 1_800_000_000, 86400
    hoy = puntua(100, 100, now, now)[0]
    tres_2d = puntua(300, 100, now - 2 * d, now)[0]
    tres_4d = puntua(300, 100, now - 4 * d, now)[0]
    assert (hoy, tres_2d, tres_4d) == (1.0, 1.5, 0.75)
    assert tres_2d > hoy > tres_4d


def test_clean_seg(tmp_path):
    now = time.time()
    for name, edad in (("viejo", 20), ("nuevo", 2)):
        seg = tmp_path / name / "seg"
        seg.mkdir(parents=True)
        f = seg / "a.mp4"
        f.write_bytes(b"x")
        t = now - edad * 86400
        os.utime(f, (t, t))
        os.utime(seg, (t, t))
    b = clean_seg(14, now=now, root=tmp_path)
    assert [p.parent.name for p in b] == ["viejo"]
    assert not (tmp_path / "viejo" / "seg").exists() and (tmp_path / "nuevo" / "seg").exists()


def test_resumen_tono():
    pub = [{"slug": "a", "tono": "critica"}, {"slug": "b", "tono": ""}, {"slug": "c", "tono": "positivo"},
           {"slug": "d", "tono": "critica"}]
    pil = [{"fecha_medida": "2026-11-03", "slug": "a", "vistas": "900"},
           {"fecha_medida": "2026-11-02", "slug": "a", "vistas": "100"},  # no cuenta: hay una más nueva
           {"fecha_medida": "2026-11-03", "slug": "b", "vistas": "50"},
           {"fecha_medida": "2026-11-03", "slug": "d", "vistas": "300"}]
    r = st.resumen_tono(pub, pil)
    assert r["critica"] == {"shorts": 2, "media": 600, "mediana": 600}
    assert r["(sin tono)"]["shorts"] == 1 and "positivo" not in r  # c: tono sin medidas
