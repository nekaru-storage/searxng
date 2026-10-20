# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring

import json
import typing as t
from unittest.mock import Mock, patch
from urllib.parse import parse_qsl, urlsplit

from searx.engines import duckduckgo_extra
from searx.enginelib.traits import EngineTraits
from searx.exceptions import SearxEngineResponseException
from searx.search.processors import OnlineParams
from tests import SearxTestCase


def _params(locale: str = "en-US", pageno: int = 1, safesearch: int = 0) -> OnlineParams:
    return t.cast(
        OnlineParams,
        t.cast(
            object,
            {
                "method": "GET",
                "headers": {},
                "data": {},
                "url": "",
                "cookies": {},
                "pageno": pageno,
                "safesearch": safesearch,
                "searxng_locale": locale,
            },
        ),
    )


def _url(params: OnlineParams) -> str:
    """Return the request URL, asserting that the engine has set one."""
    url = params["url"]
    assert isinstance(url, str)
    return url


def _response(payload, status_code: int = 200):
    response = Mock()
    response.status_code = status_code
    if isinstance(payload, Exception):
        response.json.side_effect = payload
    else:
        response.json.return_value = payload
    return response


class DuckDuckGoExtraRequestTests(SearxTestCase):
    """The XHR endpoints (``i.js``, ``v.js``, ``news.js``) answer with an HTTP
    202 *challenge* payload instead of results when the request lacks the
    client hints / fetch metadata a Chromium based browser sends."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            duckduckgo_extra,
            "traits",
            EngineTraits(
                regions={"en-US": "us-en"},
                all_locale="wt-wt",
                custom={"lang_region": {}},
            ),
            create=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.setattr4test(duckduckgo_extra, "ddg_category", "images")
        patcher = patch.object(duckduckgo_extra, "get_vqd", return_value="4-1234")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_xhr_headers(self):
        params = _params()
        duckduckgo_extra.request("cute cats", params)
        headers = params["headers"]
        self.assertEqual('"Not A;Brand";v="99", "Chromium";v="150", "Google Chrome";v="150"', headers["Sec-CH-UA"])
        self.assertEqual("?0", headers["Sec-CH-UA-Mobile"])
        self.assertEqual('"Windows"', headers["Sec-CH-UA-Platform"])
        self.assertEqual("empty", headers["Sec-Fetch-Dest"])
        self.assertEqual("cors", headers["Sec-Fetch-Mode"])
        self.assertEqual("same-origin", headers["Sec-Fetch-Site"])
        self.assertEqual("https://duckduckgo.com/", headers["Referer"])
        self.assertEqual("duckduckgo.com", headers["Host"])
        self.assertEqual("*/*", headers["Accept"])

    def test_user_agent_is_stable(self):
        # the vqd value is bound to the User-Agent, it must not change between
        # requests, otherwise the cached vqd is useless
        first = _params()
        second = _params()
        duckduckgo_extra.request("cute cats", first)
        duckduckgo_extra.request("cute cats", second)
        self.assertEqual(first["headers"]["User-Agent"], second["headers"]["User-Agent"])

    def test_images_url(self):
        params = _params()
        duckduckgo_extra.request("cute cats", params)
        parsed = urlsplit(_url(params))
        self.assertEqual("duckduckgo.com", parsed.netloc)
        self.assertEqual("/i.js", parsed.path)
        self.assertEqual(
            {
                "o": "json",
                "q": "cute cats",
                "u": "bing",
                "l": "us-en",
                "bpia": "1",
                "vqd": "4-1234",
                "a": "h_",
                "ct": "EN",
                "p": "-2",
            },
            dict(parse_qsl(parsed.query)),
        )

    def test_videos_url(self):
        self.setattr4test(duckduckgo_extra, "ddg_category", "videos")
        params = _params()
        duckduckgo_extra.request("cute cats", params)
        self.assertTrue(_url(params).startswith("https://duckduckgo.com/v.js?"))

    def test_news_url(self):
        self.setattr4test(duckduckgo_extra, "ddg_category", "news")
        params = _params()
        duckduckgo_extra.request("cute cats", params)
        self.assertTrue(_url(params).startswith("https://duckduckgo.com/news.js?"))

    def test_paging_offset(self):
        params = _params(pageno=3)
        duckduckgo_extra.request("cute cats", params)
        self.assertIn("&s=200", _url(params))

    def test_safesearch(self):
        cases: list[tuple[int, str | None]] = [(0, "-2"), (1, None), (2, "1")]
        for safesearch, expected in cases:
            params = _params(safesearch=safesearch)
            duckduckgo_extra.request("cute cats", params)
            if expected is None:
                self.assertNotIn("&p=", _url(params))
                self.assertNotIn("p", params["cookies"])
            else:
                self.assertIn(f"&p={expected}", _url(params))
                self.assertEqual(expected, params["cookies"]["p"])

    def test_too_long_query(self):
        params = _params()
        duckduckgo_extra.request("x" * 500, params)
        self.assertIsNone(params["url"])


class DuckDuckGoExtraResponseTests(SearxTestCase):
    def setUp(self):
        super().setUp()
        self.setattr4test(duckduckgo_extra, "ddg_category", "images")

    def test_images(self):
        payload = {
            "results": [
                {
                    "url": "https://example.org/page.html",
                    "title": "Cute cats",
                    "image": "https://example.org/cat.jpg",
                    "thumbnail": "https://example.org/cat_thumb.jpg",
                    "width": 1920,
                    "height": 1080,
                    "source": "Example",
                }
            ]
        }
        results = duckduckgo_extra.response(_response(payload))
        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("https://example.org/page.html", result["url"])
        self.assertEqual("Cute cats", result["title"])
        self.assertEqual("https://example.org/cat.jpg", result["img_src"])
        self.assertEqual("https://example.org/cat_thumb.jpg", result["thumbnail_src"])
        self.assertEqual("1920 x 1080", result["resolution"])
        self.assertEqual("Example", result["source"])

    def test_videos(self):
        self.setattr4test(duckduckgo_extra, "ddg_category", "videos")
        payload = {
            "results": [
                {
                    "content": "https://example.org/video",
                    "title": "Cute cats",
                    "description": "A video about cats",
                    "images": {"small": "https://example.org/small.jpg"},
                    "duration": "1:17:43",
                    "uploader": "Example Channel",
                }
            ]
        }
        results = duckduckgo_extra.response(_response(payload))
        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("https://example.org/video", result["url"])
        self.assertEqual("Cute cats", result["title"])
        self.assertEqual("A video about cats", result["content"])
        self.assertEqual("https://example.org/small.jpg", result["thumbnail"])
        self.assertEqual("1:17:43", result["length"])
        self.assertEqual("Example Channel", result["metadata"])

    def test_news(self):
        self.setattr4test(duckduckgo_extra, "ddg_category", "news")
        payload = {
            "results": [
                {
                    "url": "https://example.org/news",
                    "title": "Breaking news",
                    "excerpt": "Some <b>html</b> excerpt",
                    "date": 1792443600,
                }
            ]
        }
        results = duckduckgo_extra.response(_response(payload))
        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("https://example.org/news", result["url"])
        self.assertEqual("Some html excerpt", result["content"])
        self.assertEqual(1792443600, result["publishedDate"].timestamp())

    def test_challenge_payload(self):
        # HTTP 202 + challenge JSON is what DDG returns to non-browser requests
        payload = {"challenge": {"cc": "sre", "gk": "d4cd0dabcf4caa22ad92fab40844c786", "i": "3"}}
        with self.assertRaises(SearxEngineResponseException):
            duckduckgo_extra.response(_response(payload, status_code=202))

    def test_invalid_json(self):
        with self.assertRaises(SearxEngineResponseException):
            duckduckgo_extra.response(_response(json.JSONDecodeError("Expecting value", "", 0)))

    def test_unknown_category(self):
        self.setattr4test(duckduckgo_extra, "ddg_category", "unknown")
        with self.assertRaises(ValueError):
            duckduckgo_extra.response(_response({"results": [{}]}))
