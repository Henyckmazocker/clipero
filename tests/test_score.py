import random

from clipero.score import build_candidates, load_published, overlap

DUR = 7200.0


def chat_with_spikes(spikes, base=0.3, seed=1):
    rnd = random.Random(seed)
    rows = []
    for t in range(int(DUR)):
        if rnd.random() < base:
            rows.append({"t": float(t), "user": "u", "msg": "hola"})
    for t0, n in spikes:
        rows += [{"t": t0 + i * 10 / n, "user": "u", "msg": "KEKW jajaja"} for i in range(n)]
    return rows


def heatmap(peaks):
    return [{"start": i * 72.0, "end": (i + 1) * 72.0, "value": peaks.get(i, 0.1)} for i in range(100)]


def test_twitch_pico_conocido_primero():
    chat = chat_with_spikes([(4775, 400), (1515, 60), (3000, 30)])
    c, _ = build_candidates("twitch", DUR, chat, [], vod_id="x")
    assert 10 <= len(c) <= 15
    assert abs(c[0]["peak"] - 4780) <= 10
    assert c[0]["start"] == c[0]["peak"] - 90 and c[0]["end"] == c[0]["peak"] + 30
    assert c[0]["chat_top"][0] == "KEKW"


def test_twitch_descarta_ventana_muted():
    chat = chat_with_spikes([(3450, 400), (4775, 60)])
    c, avisos = build_candidates("twitch", DUR, chat, [], muted=[[3420.0, 3500.0]], vod_id="x")
    assert all(overlap(w["start"], w["end"], 3420, 3500) == 0 for w in c)
    assert c[0]["peak"] > 4700
    assert any("silenciado" in a for a in avisos)


def test_publicados_solape_mayor_50_descarta():
    chat = chat_with_spikes([(4775, 400), (1515, 60)])
    c0, _ = build_candidates("twitch", DUR, chat, [], vod_id="x")
    s, e = c0[0]["start"], c0[0]["end"]
    c, avisos = build_candidates("twitch", DUR, chat, [], published=[(s + 10, e + 10)], vod_id="x")
    assert all(overlap(w["start"], w["end"], s, e) == 0 for w in c)
    assert c[0]["peak"] < 2000 and any("publicada" in a for a in avisos)
    # solape <=50 %: no se descarta
    c2, _ = build_candidates("twitch", DUR, chat, [], published=[(e - 30, e + 200)], vod_id="x")
    assert c2[0]["peak"] == c0[0]["peak"]


def test_load_published_filtra_por_vod(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("fecha,slug,fuente,formato,vod_id,start,end,url\n"
                 "2026-11-02,a,x,arco,abc,10,100,u\n2026-11-02,b,x,arco,otro,5,50,u\n")
    assert load_published(p, "abc") == [(10.0, 100.0)]


def test_youtube_sin_heatmap_descartado():
    c, avisos = build_candidates("youtube", DUR, [], [], vod_id="lzoc")
    assert c == [] and any("sin heatmap" in a for a in avisos)


def test_youtube_heatmap_sin_chat_top3_son_los_picos():
    hm = heatmap({10: 1.0, 40: 0.9, 70: 0.8, 25: 0.5})
    c, _ = build_candidates("youtube", DUR, [], hm, vod_id="y")
    assert [round(w["peak"]) for w in c[:3]] == [round(10 * 72 + 36), round(40 * 72 + 36), round(70 * 72 + 36)]
    assert c[0]["score"] == 1.0 and c[0]["chat_z"] == 0.0


def test_youtube_heatmap_y_chat_mezcla_06_04():
    hm = heatmap({10: 1.0, 40: 0.9})
    chat = chat_with_spikes([(40 * 72 + 20, 200)])
    c, _ = build_candidates("youtube", DUR, chat, hm, vod_id="y")
    top = c[0]
    assert abs(top["peak"] - (40 * 72 + 25)) < 72  # el chat arrastra el pico
    assert abs(top["score"] - (0.6 * 0.9 + 0.4)) < 1e-3
