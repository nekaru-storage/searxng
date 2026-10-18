# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google Videos: see :py:obj:`searx.engines.google`."""

import typing as t

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import google_request, unwrap_google_url, wml_dom
from searx.result_types import EngineResults
from searx.utils import (
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
    parse_duration_string,
)

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

# about
about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q219885",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "XML",
}

# engine dependent config
categories = ["videos", "web"]
paging = True
max_page = 50
"""Google supports up to 50 pages of results, see the `Google max_page discussion`_.

.. _Google max_page discussion: https://github.com/searxng/searxng/issues/2982
"""
language_support = True
time_range_support = True
safesearch = True


def request(query: str, params: "OnlineParams") -> None:
    google_request(
        query,
        params,
        {"tbm": "vid"},
        eng_traits=traits,
        use_locales=False,
    )


def response(resp: "SXNG_Response") -> EngineResults:
    results = EngineResults()
    seen = set()

    # Google serves the video tab with the same result card as the web tab
    # (``Gx5Zad`` block, ``h3.zBAuLc`` title); the former ``zMzFAb`` /
    # ``CVA68e`` / ``fuLhoc`` markup no longer exists.
    for block in eval_xpath_list(wml_dom(resp), '//div[contains(@class, "Gx5Zad")]'):
        title_tag = eval_xpath_getindex(block, './/h3[contains(@class, "zBAuLc")]', 0, default=None)
        if title_tag is None:
            continue
        title = extract_text(title_tag)

        raw_url = eval_xpath_getindex(
            block,
            './/a[contains(@href, "/url?") and .//h3[contains(@class, "zBAuLc")]]/@href',
            0,
            default=None,
        )
        if raw_url is None:
            continue

        url = unwrap_google_url(raw_url)
        if not url.startswith("http") or url in seen:
            continue

        thumbnail = eval_xpath_getindex(block, './/img[contains(@src, "encrypted-tbn")]/@src', 0, default="") or ""
        if "/default.jpg" in thumbnail:
            thumbnail = thumbnail.split("?")[0].replace("/default.jpg", "/hqdefault.jpg")

        length = None
        for span in eval_xpath_list(block, './/span[contains(@class, "MDvRSc")]'):
            length = parse_duration_string(extract_text(span) or "")
            if length:
                break

        seen.add(url)
        results.add(
            results.types.Video(
                url=url,
                title=title,
                thumbnail=thumbnail,
                length=length,
            )
        )

    return results
