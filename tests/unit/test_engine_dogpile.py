# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring

import datetime
import typing as t
from unittest.mock import Mock, patch

from parameterized import parameterized

from searx.engines import dogpile
from searx.exceptions import SearxEngineAPIException
from searx.search.processors import OnlineParams
from tests import SearxTestCase


def _params(safesearch: int = 0, pageno: int = 1) -> OnlineParams:
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
            },
        ),
    )


def _response(payload):
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    return response


class DogpileRequestTests(SearxTestCase):
    """Dogpile's edge (CloudFront) only serves the API when the request carries
    the TLS fingerprint of a Firefox browser and a matching ``Referer``."""

    def setUp(self):
        super().setUp()
        cache = Mock()
        cache.get.return_value = "cached-token"
        patcher = patch.object(dogpile, "CACHE", cache, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.setattr4test(dogpile, "dogpile_categ", "search")

    @parameterized.expand(
        [
            ("search", "https://www.dogpile.com/"),
            ("images", "https://www.dogpile.com/images"),
            ("videos", "https://www.dogpile.com/videos"),
            ("news", "https://www.dogpile.com/news"),
        ]
    )
    def test_referer(self, category, expected):
        self.setattr4test(dogpile, "dogpile_categ", category)
        params = _params()
        dogpile.request("searxng", params)
        self.assertEqual(expected, params["headers"]["Referer"])
        self.assertEqual(f"https://www.dogpile.com/api/{category}", params["url"])

    def test_impersonate(self):
        params = _params()
        dogpile.request("searxng", params)
        # the default ``chrome`` fingerprint gets a 403 from the edge
        self.assertEqual("firefox", params.get("impersonate"))

    def test_request_payload(self):
        params = _params(safesearch=2, pageno=3)
        dogpile.request("searxng", params)
        self.assertEqual("POST", params["method"])
        self.assertEqual({"q": "searxng", "qadf": "heavy", "page": 3}, params["json"])
        self.assertEqual("https://www.dogpile.com", params["headers"]["Origin"])
        self.assertEqual("cors", params["headers"]["Sec-Fetch-Mode"])
        self.assertEqual("cached-token", params["headers"]["x-dogpile-token"])
        self.assertEqual("1", params["cookies"]["dp_api_token"])


class DogpileTokenTests(SearxTestCase):
    def setUp(self):
        super().setUp()
        cache = Mock()
        cache.get.return_value = None
        patcher = patch.object(dogpile, "CACHE", cache, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cache = cache

    def test_token_request(self):
        post = Mock()
        post.return_value = Mock(ok=True, json=Mock(return_value={"token": "new-token"}))
        with patch.object(dogpile, "post", post):
            self.assertEqual("new-token", dogpile._obtain_token())  # pylint: disable=protected-access)
        kwargs = post.call_args.kwargs
        self.assertEqual("firefox", kwargs["impersonate"])
        self.assertEqual("https://www.dogpile.com/", kwargs["headers"]["Referer"])
        self.assertEqual({"dp_api_token": "1"}, kwargs["cookies"])
        self.cache.set.assert_called_once_with("token", "new-token", expire=240)

    def test_cached_token_is_reused(self):
        self.cache.get.return_value = "old-token"
        post = Mock()
        with patch.object(dogpile, "post", post):
            self.assertEqual("old-token", dogpile._obtain_token())  # pylint: disable=protected-access)
        post.assert_not_called()

    def test_token_http_error(self):
        post = Mock(return_value=Mock(ok=False, status_code=403))
        with patch.object(dogpile, "post", post), self.assertRaises(SearxEngineAPIException):
            dogpile._obtain_token()  # pylint: disable=protected-access

    def test_token_without_value(self):
        post = Mock(return_value=Mock(ok=True, json=Mock(return_value={"expiresAt": 1})))
        with patch.object(dogpile, "post", post), self.assertRaises(SearxEngineAPIException):
            dogpile._obtain_token()  # pylint: disable=protected-access


class DogpileSetupTests(SearxTestCase):
    def test_invalid_category(self):
        self.setattr4test(dogpile, "dogpile_categ", "shopping")
        with self.assertRaises(ValueError):
            dogpile.setup({})


class DogpileResponseTests(SearxTestCase):
    def setUp(self):
        super().setUp()
        self.setattr4test(dogpile, "dogpile_categ", "search")

    def test_missing_click_url(self):
        results = dogpile.response(_response({"results": [{"title": "no url"}, {"clickUrl": "https://example.org"}]}))
        self.assertEqual(1, len(results))
        self.assertEqual("https://example.org", results[0]["url"])

    def test_general(self):
        payload = {"results": [{"clickUrl": "https://example.org", "title": "<b>Example</b>", "description": "text"}]}
        results = dogpile.response(_response(payload))
        self.assertEqual("Example", results[0]["title"])
        self.assertEqual("text", results[0]["content"])

    def test_news(self):
        self.setattr4test(dogpile, "dogpile_categ", "news")
        payload = {
            "results": [
                {
                    "clickUrl": "https://example.org/news",
                    "title": "Headline &amp; more",
                    "description": "Summary",
                    "thumbnailUrl": "https://example.org/t.jpg",
                    "date": 1792443600,
                }
            ]
        }
        result = dogpile.response(_response(payload))[0]
        self.assertEqual("Headline & more", result["title"])
        self.assertEqual("https://example.org/t.jpg", result["thumbnail"])
        self.assertEqual(1792443600, result["publishedDate"].timestamp())

    def test_news_escaped_markup(self):
        # real headlines are HTML escaped, see the ``&lt;b&gt;`` in
        # https://www.dogpile.com/api/news
        self.setattr4test(dogpile, "dogpile_categ", "news")
        payload = {
            "results": [
                {
                    "clickUrl": "https://example.org/news",
                    "title": "&lt;b&gt;Indonesia&lt;/b&gt; VP resigns",
                    "description": "&lt;b&gt;Jakarta&lt;/b&gt; - summary",
                }
            ]
        }
        result = dogpile.response(_response(payload))[0]
        self.assertEqual("Indonesia VP resigns", result["title"])
        self.assertEqual("Jakarta - summary", result["content"])

    def test_general_literal_markup(self):
        # the other categories carry markup, not entities: escaped markup is
        # left visible as text instead of being stripped like in news
        payload = {"results": [{"clickUrl": "https://example.org", "title": "&lt;b&gt;Example&lt;/b&gt;"}]}
        self.assertEqual("<b>Example</b>", dogpile.response(_response(payload))[0]["title"])

    def test_videos(self):
        self.setattr4test(dogpile, "dogpile_categ", "videos")
        payload = {
            "results": [
                {
                    "clickUrl": "https://example.org/video",
                    "title": "Video",
                    "description": "About",
                    "thumbnailUrl": "https://example.org/t.jpg",
                    "duration": 90,
                    "viewCount": 1200,
                }
            ]
        }
        result = dogpile.response(_response(payload))[0]
        self.assertEqual(datetime.timedelta(seconds=90), result["length"])
        self.assertEqual("1K", result["views"])

    def test_images(self):
        self.setattr4test(dogpile, "dogpile_categ", "images")
        payload = {
            "results": [
                {
                    "clickUrl": "https://example.org/img.jpg",
                    "altClickUrl": "https://example.org/page",
                    "title": "Image",
                    "format": "jpeg",
                    "width": 1920,
                    "height": 1080,
                    "thumbnailUrl": "https://example.org/thumb.jpg",
                }
            ]
        }
        result = dogpile.response(_response(payload))[0]
        self.assertEqual("https://example.org/page", result["url"])
        self.assertEqual("https://example.org/img.jpg", result["img_src"])
        self.assertEqual("1920x1080", result["resolution"])
        self.assertEqual("jpeg", result["img_format"])

    def test_unexpected_payload(self):
        with self.assertRaises(SearxEngineAPIException):
            dogpile.response(_response(["not", "a", "dict"]))
