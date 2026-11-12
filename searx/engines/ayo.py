# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ayo (general)"""

import typing as t
from urllib.parse import quote_plus

from searx.exceptions import SearxEngineAPIException
from searx.network import get, post
from searx.result_types import EngineResults
from searx.utils import (
    eval_xpath,
    eval_xpath_list,
    extract_text,
    solve_anubis,
)
from searx.enginelib import EngineCache

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams


about = {
    "website": "https://search.ayo.de",
    "wikidata_id": None,
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": True,
    "results": "HTML",
}

categories = ["general"]

base_url = "https://search.ayo.de"

CACHE: EngineCache
"""Cache for storing the cookies and after solving an Anubis CAPTCHA."""

COOKIE_TTL = 30 * 60
"""Anubis cookies are short lived; refresh them long before the cache expires."""


def setup(engine_settings: dict[str, str]):
    global CACHE  # pylint:disable=global-statement
    CACHE = EngineCache(engine_settings["name"])


def _cookies(force: bool = False):
    """Return the Anubis cookies, solving the challenge when there is none cached.

    ``force`` drops the cached cookie; Anubis rotates its cookies, so a stale
    one must not be reused for the whole :py:obj:`EngineCache` lifetime.
    """
    if not force and (cached := CACHE.get("cookies")):
        return cached

    cookies = solve_anubis(get(base_url))
    CACHE.set("cookies", cookies, expire=COOKIE_TTL)
    return cookies


def _search_page(query: str, cookies):
    resp = get(f"{base_url}/search?q={quote_plus(query)}", cookies=cookies)
    token = extract_text(eval_xpath(resp.html(), "//input[@name='_token']/@value"))
    return token, resp


def request(query: str, params: "OnlineParams"):
    cookies = _cookies()
    csrf_token, search_resp = _search_page(query, cookies)

    if not csrf_token:
        # the cached Anubis cookie expired in the meantime -> repeat once with a new one
        cookies = _cookies(force=True)
        csrf_token, search_resp = _search_page(query, cookies)

    if not csrf_token:
        raise SearxEngineAPIException("csrf token not found")

    # extract the URL of the actual results - base64 encoded JSON + server-side signature,
    # so we can't build the query URL ourselves
    resp = post(
        f"{base_url}/search",
        json={
            "_token": csrf_token,
            "source": "searchbox",
            "q": query,
        },
        cookies=search_resp.cookies,
    )
    url = extract_text(eval_xpath(resp.html(), "//div[@id='organic-results']/@data-url"))
    if not url:
        raise SearxEngineAPIException("failed to extract results URL")

    params["url"] = url
    params["cookies"] = cookies


def response(resp: "SXNG_Response"):
    res = EngineResults()
    doc = resp.html()

    for result in eval_xpath_list(doc, "//div[contains(@class, 'search-result')]"):
        res.add(
            res.types.MainResult(
                url=extract_text(eval_xpath(result, ".//a/@href")) or "",
                title=extract_text(eval_xpath(result, ".//a//h3")) or "",
                content=extract_text(eval_xpath(result, ".//a/p")),
            )
        )

    return res
