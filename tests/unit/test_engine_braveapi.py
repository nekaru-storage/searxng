# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring

from unittest.mock import Mock

from searx.engines import braveapi
from searx.result_types import MainResult, Video
from tests import SearxTestCase


def _resp(web_results):
    response = Mock()
    response.json.return_value = {"web": {"results": web_results}}
    return response


class BraveAPIResponseTests(SearxTestCase):
    def test_web_results_not_videos(self):
        # web results parsed as Video results never merge with the results of other engines
        payload = [
            {
                "title": "SearXNG - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/SearXNG",
                "description": "SearXNG is an internet metasearch engine.",
            }
        ]
        results = braveapi.response(_resp(payload))
        self.assertEqual(1, len(results))
        self.assertIsInstance(results[0], MainResult)
        self.assertNotIsInstance(results[0], Video)
        self.assertEqual("default.html", results[0].template)
        self.assertEqual(payload[0]["url"], results[0].url)
        self.assertEqual(payload[0]["title"], results[0].title)

    def test_multiple_web_results(self):
        payload = [
            {"title": "Example", "url": "https://example.com/", "description": "An example."},
            {"title": "Other", "url": "https://other.example/", "description": ""},
        ]
        results = braveapi.response(_resp(payload))
        self.assertEqual(2, len(results))
        for result in results:
            self.assertIsInstance(result, MainResult)
            self.assertNotIsInstance(result, Video)
