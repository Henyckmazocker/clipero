from clipero.fetch import parse_hls, select_segments, youtube_offset
from clipero.transcribe import paragraphs, render_md, top_chat, words_to_vod

PL = '#EXTM3U\n#EXT-X-MAP:URI="init-0.mp4"\n' + "".join(f"#EXTINF:10.000,\n{i}.mp4\n" for i in range(30)) + "#EXT-X-ENDLIST\n"


def test_parse_hls():
    init, segs = parse_hls(PL)
    assert init == "init-0.mp4" and len(segs) == 30
    assert segs[3] == ("3.mp4", 30.0, 10.0)


def test_select_segments_offset():
    _, segs = parse_hls(PL)
    sel, off = select_segments(segs, 55.0, 125.0)
    assert off == 50.0 and [s[0] for s in sel] == [f"{i}.mp4" for i in range(5, 13)]
    sel, off = select_segments(segs, 60.0, 80.0)  # borde exacto: el segmento 6 empieza en 60
    assert off == 60.0 and [s[0] for s in sel] == ["6.mp4", "7.mp4"]


def test_offset_timestamps():
    ws = words_to_vod([(" hola", 1.2, 1.5), ("  ", 2, 3), ("mundo", 2.0, 2.4)], 4770.0)
    assert ws == [{"w": "hola", "s": 4771.2, "e": 4771.5}, {"w": "mundo", "s": 4772.0, "e": 4772.4}]


def test_render_md():
    chat = [{"t": 105, "user": "a", "msg": "KEKW"}, {"t": 106, "user": "b", "msg": "kekw"},
            {"t": 107, "user": "c", "msg": "yo"}, {"t": 900, "user": "d", "msg": "fuera"}]
    cands = [{"n": 1, "start": 100.0, "end": 220.0, "peak": 190.0, "score": 0.87, "heatmap": None, "chat_z": 3.4}]
    words = {1: [{"w": "hola", "s": 101.0, "e": 101.3}, {"w": "que", "s": 102.0, "e": 102.2},
                 {"w": "tal", "s": 113.0, "e": 113.4}]}
    md = render_md("v1", "T", cands, words, chat)
    assert "## #1 · 01:40–03:40 · score 0.87" in md
    assert "KEKW (×2)" in md and "fuera" not in md
    assert "[01:40] hola que" in md and "[01:50] tal" in md


def test_top_chat_y_parrafos():
    assert top_chat([{"t": 1, "msg": "a"}, {"t": 2, "msg": "A"}, {"t": 3, "msg": "b"}], 0, 10, 1) == [("a", 2)]
    assert paragraphs([], 0, 10) == []


def test_youtube_offset(capsys):
    assert youtube_offset(6210.0, 6330.0, 125.986) == 6204.014
    assert capsys.readouterr().err == ""
    assert youtube_offset(100.0, 220.0, 120.0) == 100.0
    youtube_offset(100.0, 220.0, 140.0)  # demasiado larga → aviso
    assert "AVISO" in capsys.readouterr().err
