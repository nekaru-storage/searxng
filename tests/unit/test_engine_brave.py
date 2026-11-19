# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,line-too-long

import json
from unittest import mock

from parameterized import parameterized

from searx.engines import brave, brave_web
from searx.result_types import EngineResults, MainResult
from tests import SearxTestCase

TOKEN = "A" * 212
CLOAKED = "/go/v1/" + TOKEN

# ``search_params`` of the response, set by the online processor
SEARCH_PARAMS = {
    "url": "https://search.brave.com/search?q=cheese",
    "cookies": {"safesearch": "off"},
}


class BraveEngineTests(SearxTestCase):
    '''Unit tests specific to the Brave engine'''

    # extract_iife_object
    @parameterized.expand(
        [
            (
                """(function (a, b, c){ return {"a": a, "b": b, "c": c };})("first", 2, {"third": 3})""",  # basic shape, numeric, nested object
                {"a": "first", "b": 2, "c": {"third": 3}},
            ),
            (
                '(function ($,aa,a,a1){return {"first": $, "second": true, "third": [aa,a,a1]};})("actual","x","y","z")',  # non-alpha param, literal, and array
                {"first": "actual", "second": True, "third": ["x", "y", "z"]},
            ),
        ]
    )
    def test_javascript_iife_parser(self, js_code, expected_output):
        iife_match = brave.IIFE_RE.match(js_code)
        self.assertIsNotNone(iife_match)

        iife_object, _ = brave.extract_iife_object(js_code, iife_match)  # pyright: ignore[reportArgumentType]
        parsed = json.loads(iife_object)
        self.assertEqual(parsed, expected_output)


class BraveCloakedUrlTests(SearxTestCase):
    '''Brave cloaks some result links as ``/go/v1/<token>``'''

    # pylint: disable=protected-access

    def test_resolve_redirect(self):
        response = mock.Mock(status_code=302, headers={"location": "https://example.org/"})
        with mock.patch.object(brave, "multi_requests", return_value=[response]) as mock_requests:
            resolved = brave._resolve_cloaked_urls(
                [CLOAKED, "https://example.org/"], mock.Mock(search_params=SEARCH_PARAMS)
            )

        self.assertEqual(resolved, {CLOAKED: "https://example.org/"})
        request = mock_requests.call_args.args[0][0]
        self.assertEqual(request.url, "https://search.brave.com" + CLOAKED)
        self.assertFalse(request.kwargs["allow_redirects"])

        # the requests replay the session of the results page request
        self.assertEqual(request.kwargs["cookies"], SEARCH_PARAMS["cookies"])
        self.assertEqual(request.kwargs["headers"], {"Referer": SEARCH_PARAMS["url"]})

    def test_resolve_confirm_page(self):
        page = (
            '<html><body><a class="destination svelte-x" href="https://example.org/a?b=1&amp;c=2">x</a></body></html>'
        )
        response = mock.Mock(status_code=200, headers={}, text=page)
        with mock.patch.object(brave, "multi_requests", return_value=[response]):
            resolved = brave._resolve_cloaked_urls([CLOAKED], mock.Mock(search_params=SEARCH_PARAMS))

        self.assertEqual(resolved, {CLOAKED: "https://example.org/a?b=1&c=2"})

    def test_resolve_error(self):
        with mock.patch.object(brave, "multi_requests", return_value=[Exception("boom")]):
            self.assertEqual(brave._resolve_cloaked_urls([CLOAKED], mock.Mock(search_params=SEARCH_PARAMS)), {})

    def test_resolve_skips_plain_urls(self):
        with mock.patch.object(brave, "multi_requests") as mock_requests:
            self.assertEqual(brave._resolve_cloaked_urls(["https://example.org/"], mock.Mock(search_params={})), {})
        mock_requests.assert_not_called()

    def test_resolve_result_urls(self):
        fallback = "/go/v1/" + "B" * 212
        results = EngineResults()
        results.add(MainResult(url=CLOAKED, title="resolved"))
        results.add(MainResult(url=fallback, title="fallback"))
        results.add(MainResult(url="https://example.org/", title="plain"))

        response = mock.Mock(status_code=302, headers={"location": "https://example.org/target"})
        with mock.patch.object(brave, "multi_requests", return_value=[response, Exception("boom")]):
            brave.resolve_result_urls(results, mock.Mock(search_params=SEARCH_PARAMS), lookup=True)

        self.assertEqual(results[0].url, "https://example.org/target")
        self.assertEqual(results[1].url, "https://search.brave.com" + fallback)
        self.assertEqual(results[2].url, "https://example.org/")

    def test_resolve_without_lookup(self):
        results = EngineResults()
        results.add(MainResult(url=CLOAKED, title="title"))

        with mock.patch.object(brave, "multi_requests") as mock_requests:
            brave.resolve_result_urls(results, mock.Mock(search_params=SEARCH_PARAMS), lookup=False)

        mock_requests.assert_not_called()
        self.assertEqual(results[0].url, "https://search.brave.com" + CLOAKED)


class BraveWebEngineTests(SearxTestCase):
    '''Brave web engine reads the results page HTML'''

    PAGE = f"""
    <html><body>
      <div class="snippet" data-type="web">
        <a href="{CLOAKED}"><div class="title search-snippet-title">Title</div></a>
        <div class="generic-snippet"><div class="content">Content</div></div>
      </div>
    </body></html>
    """

    def test_cloaked_urls_are_resolved(self):
        response = mock.Mock(status_code=302, headers={"location": "https://example.org/"})
        with mock.patch.object(brave, "multi_requests", return_value=[response]):
            results = brave_web.response(mock.Mock(text=self.PAGE, search_params=SEARCH_PARAMS))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://example.org/")
        self.assertEqual(results[0].title, "Title")

    def test_unresolved_url_absolute(self):
        with mock.patch.object(brave, "multi_requests", return_value=[Exception("boom")]):
            results = brave_web.response(mock.Mock(text=self.PAGE, search_params=SEARCH_PARAMS))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://search.brave.com" + CLOAKED)

    def test_lookup_disabled_by_setting(self):
        with (
            mock.patch.object(brave, "multi_requests") as mock_requests,
            mock.patch.object(brave_web, "brave_resolve_cloaked_urls", False),
        ):
            results = brave_web.response(mock.Mock(text=self.PAGE, search_params=SEARCH_PARAMS))

        mock_requests.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://search.brave.com" + CLOAKED)

    def test_parse_results_urls(self):
        # pylint: disable=protected-access
        payload = (
            "kit.start(app, element, { data: ["
            '{type:"data",data:{}},'
            '{type:"data",data:{"body":{"response":{"web":{"results":'
            '[{"title":"Title","url":"' + CLOAKED + '"}]}}}}},'
            "] })"
        )
        response = mock.Mock(status_code=302, headers={"location": "https://example.org/"})
        with mock.patch.object(brave, "multi_requests", return_value=[response]):
            results = brave._parse_results(
                brave.parse_search_result, mock.Mock(text=payload, search_params=SEARCH_PARAMS)
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://example.org/")

    def test_parse_results_no_lookup(self):
        # pylint: disable=protected-access
        payload = (
            "kit.start(app, element, { data: ["
            '{type:"data",data:{}},'
            '{type:"data",data:{"body":{"response":{"web":{"results":'
            '[{"title":"Title","url":"' + CLOAKED + '"}]}}}}},'
            "] })"
        )
        with (
            mock.patch.object(brave, "multi_requests") as mock_requests,
            mock.patch.object(brave, "brave_resolve_cloaked_urls", False),
        ):
            results = brave._parse_results(
                brave.parse_search_result, mock.Mock(text=payload, search_params=SEARCH_PARAMS)
            )

        mock_requests.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://search.brave.com" + CLOAKED)
