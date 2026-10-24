"""yandex engine: from a Russian IP yandex.com answers with a 302 to yandex.ru."""

import pytest

from searx.engines import yandex


def _params():
    return {
        "pageno": 1,
        "language": "en",
        "searxng_locale": "en",
        "time_range": None,
        "safesearch": 0,
        "url": None,
        "query": "test",
        "engine_data": {},
        "paging": False,
    }


@pytest.mark.parametrize("search_type", ["web", "images"])
def test_follows_the_redirect(monkeypatch, search_type):
    """#6879: online engines do not follow redirects unless asked to."""
    monkeypatch.setattr(yandex, "search_type", search_type)
    params = _params()
    yandex.request("test", params)
    assert params["url"]
    assert params["allow_redirects"] is True
    assert params["soft_max_redirects"] == 1
