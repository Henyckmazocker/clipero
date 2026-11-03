import json

from clipero.ingest import normalize_twitch_chat, parse_muted_ranges, parse_youtube_livechat, vod_id_from_info


def test_muted_rangos_fusionados():
    pl = "#EXTM3U\n" + "".join(
        f"#EXTINF:10.000,\n{i}{'-muted' if 2 <= i <= 4 or i == 7 else ''}.mp4\n" for i in range(9))
    assert parse_muted_ranges(pl) == [[20.0, 50.0], [70.0, 80.0]]


def test_youtube_livechat(tmp_path):
    line = {"replayChatItemAction": {"videoOffsetTimeMsec": "12500", "actions": [{"addChatItemAction": {"item": {
        "liveChatTextMessageRenderer": {"authorName": {"simpleText": "ana"},
                                        "message": {"runs": [{"text": "JAJA "}, {"text": "kekw"}]}}}}}]}}
    p = tmp_path / "c.live_chat.json"
    p.write_text(json.dumps(line) + "\n{}\nbasura\n")
    assert parse_youtube_livechat(p) == [{"t": 12.5, "user": "ana", "msg": "JAJA kekw"}]


def test_twitch_normaliza(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"comments": [{"content_offset_seconds": 9.2, "commenter": {"name": "bob"},
                                           "message": {"body": "hola"}}]}))
    assert normalize_twitch_chat(p) == [{"t": 9.2, "user": "bob", "msg": "hola"}]


def test_vod_id():
    assert vod_id_from_info({"id": "v2909530977"}) == "2909530977"
    assert vod_id_from_info({"id": "lzoc6kjd7-g"}) == "lzoc6kjd7-g"
