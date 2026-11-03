import time

import pytest

from clipero import sources

NOW = 1_800_000_000


def _fuentes():
    return [{"id": "ibai", "twitch": "ibai"}, {"id": "elxokas", "twitch": "elxokas"}]


def _flat(url, *a, **k):
    canal = url.split("twitch.tv/")[1].split("/")[0]
    return [{"url": f"https://twitch.tv/videos/{canal}1", "view_count": 100}]


def _info(url):
    canal = url.rsplit("/", 1)[1][:-1]
    return {"timestamp": NOW - 3600, "view_count": 100, "duration": 3600,
            "webpage_url": url, "title": canal, "id": url.rsplit("/", 1)[1], "extractor_key": "TwitchVod"}


def test_filtra_por_ids():
    filas = sources.recent_vods(_fuentes(), 3, now=NOW, ingeridos=set(), flat=_flat, info=_info, fuentes=["ibai"])
    assert filas and {f["fuente"] for f in filas} == {"ibai"}


def test_sin_fuentes_rastrea_todas():
    filas = sources.recent_vods(_fuentes(), 3, now=NOW, ingeridos=set(), flat=_flat, info=_info)
    assert {f["fuente"] for f in filas} == {"ibai", "elxokas"}


def test_fuente_desconocida():
    with pytest.raises(RuntimeError, match="fuente desconocida: nadie"):
        sources.recent_vods(_fuentes(), 3, now=NOW, ingeridos=set(), flat=_flat, info=_info, fuentes=["ibai", "nadie"])
