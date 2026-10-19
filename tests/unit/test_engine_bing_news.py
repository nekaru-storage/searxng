# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring

from unittest.mock import Mock

from searx.engines import bing_news
from tests import SearxTestCase

# Markup of one ``newsitem`` card as returned by
# https://www.bing.com/news/infinitescrollajax
CARD_HTML = """
<div class="news-card newsitem cardcommon" url="https://example.com/article"
     data-author="Example News">
  <a class="imagelink" href="https://example.com/article"><img src="/th?id=ONUT.xyz"></a>
  <div class="news-card-body">
    <a class="title" href="https://example.com/article" data-author="Example News">Example headline</a>
    <div class="snippet">Short summary of the article.</div>
    <div class="source"><span aria-label="Example News">Example News</span></div>
  </div>
</div>
"""

IMG_SRC = 'src="/th?id=ONUT.xyz"'
CARD_ABSOLUTE_IMG = CARD_HTML.replace(IMG_SRC, 'src="https://cdn.example.com/pic.jpg"')
CARD_WITHOUT_IMG_SRC = CARD_HTML.replace(" " + IMG_SRC, "")


def _resp(text):
    """A response whose ``html()`` fails loudly if it is called on an empty body."""
    response = Mock()
    response.text = text
    if text.strip():

        def _parse():
            from lxml import html

            return html.fromstring(text)

        response.html.side_effect = _parse
    else:
        # ``html.fromstring("")`` raises, so calling it here must be a failure.
        response.html.side_effect = AssertionError("html() called on an empty body")
    return response


class BingNewsEmptyResponseTests(SearxTestCase):
    """Bing answers HTTP 200 with an empty body when the query has no results."""

    def test_empty_body(self):
        self.assertEqual([], bing_news.response(_resp("")))

    def test_whitespace_only_body(self):
        self.assertEqual([], bing_news.response(_resp("  \r\n\t ")))


class BingNewsResponseTests(SearxTestCase):
    def test_newsitem_card(self):
        results = bing_news.response(_resp(CARD_HTML))
        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("https://example.com/article", result["url"])
        self.assertEqual("Example headline", result["title"])
        self.assertEqual("Short summary of the article.", result["content"])
        self.assertEqual("https://www.bing.com/th?id=ONUT.xyz", result["thumbnail"])
        self.assertIn("Example News", result["metadata"])

    def test_absolute_thumbnail_is_not_prefixed(self):
        results = bing_news.response(_resp(CARD_ABSOLUTE_IMG))
        self.assertEqual(1, len(results))
        self.assertEqual("https://cdn.example.com/pic.jpg", results[0]["thumbnail"])

    def test_card_without_thumbnail_source(self):
        results = bing_news.response(_resp(CARD_WITHOUT_IMG_SRC))
        self.assertEqual(1, len(results))
        self.assertIsNone(results[0]["thumbnail"])
