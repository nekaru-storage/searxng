# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring

"""yandex engine: from a Russian IP yandex.com answers with a 302 to yandex.ru."""

from searx.engines import yandex

from tests import SearxTestCase


class TestYandexEngine(SearxTestCase):
    @staticmethod
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

    def test_follows_the_redirect(self):
        """#6879: online engines do not follow redirects unless asked to."""
        for search_type in ("web", "images"):
            self.setattr4test(yandex, "search_type", search_type)
            params = self._params()
            yandex.request("test", params)
            assert params["url"]
            assert params["allow_redirects"] is True
            assert params["soft_max_redirects"] == 1
