"""subs.py: los tiempos del ASS casan con words.json desplazado, sin solapes ni palabras cruzando el borde."""
from clipero import subs


def mk(texts, t0, step=0.4, dur=0.3):
    return [{"w": w, "s": round(t0 + i * step, 2), "e": round(t0 + i * step + dur, 2)} for i, w in enumerate(texts)]


WORDS = mk(["Hola,", "esto", "es", "una", "prueba.", "Segunda", "frase", "corta", "de", "verdad", "ahora"], 100.0)


def test_grupos_de_2_a_3_palabras_en_mayusculas():
    g = subs.group_words(subs.tramo_words(WORDS, 99.9, 110))
    assert [len(x) for x in g] == [3, 2, 3, 3]
    assert g[0][0]["w"] == "HOLA" and "ES" in [w["w"] for w in g[0]]


def test_tiempos_casan_con_words_desplazado_y_no_hay_solapes():
    a, b, t0 = 100.0, 104.5, 12.0
    ev = subs.tramo_events(WORDS, a, b, t0, 1344)
    ass = subs.build_ass(ev)
    d = subs.parse_dialogues(ass)
    ws = subs.tramo_words(WORDS, a, b)
    amarillas = {}
    for s, e, words, cur in d:
        amarillas.setdefault(cur, s)
        assert e > s
    for w in ws:
        # el inicio del evento de esa palabra = su inicio en words.json + (t0 - a)
        assert abs(amarillas[w["w"]] - (w["s"] + t0 - a)) <= 0.011, w
    for (s1, e1, *_), (s2, e2, *_) in zip(d, d[1:]):
        assert e1 <= s2 + 1e-9
    assert all(e <= t0 + (b - a) + 0.011 for _, e, *_ in d)
    assert "\\pos(540,1344)" in ass and "&H00FFFF&" in ass and "Montserrat ExtraBold,78" in ass
    assert ",1,6,0,5," in ass   # borde 6 px, alineación 5


def test_palabras_que_cruzan_el_borde_se_quitan():
    # "frase" va de 101.6 a 101.9; el tramo acaba en 101.7: cruza → fuera
    ws = subs.tramo_words(WORDS, 100.0, 101.7)
    assert [w["w"] for w in ws] == ["HOLA", "ESTO", "ES", "UNA", "PRUEBA"][:len(ws)]
    assert all(w["e"] <= 101.72 for w in ws)
    ws2 = subs.tramo_words(WORDS, 100.5, 104)
    assert ws2[0]["w"] == "ES"   # "Hola," y "esto" empiezan antes del tramo


def test_varios_tramos_sin_solape_y_posicion_por_tramo():
    ev = subs.tramo_events(WORDS, 100.0, 102.0, 0.0, subs.Y_LAYOUT) + \
        subs.tramo_events(WORDS, 102.0, 104.4, 2.0, subs.Y_SIN_LAYOUT)
    d = subs.parse_dialogues(subs.build_ass(ev))
    assert all(e1 <= s2 + 1e-9 for (s1, e1, *_), (s2, e2, *_) in zip(d, d[1:]))
    ass = subs.build_ass(ev)
    assert "pos(540,960)" in ass and "pos(540,1344)" in ass


def test_palabra_larga_no_agrupa_de_mas():
    ws = subs.tramo_words(mk(["constitucionalmente", "si", "no"], 0), 0, 5)
    assert [len(g) for g in subs.group_words(ws)] == [1, 2]
