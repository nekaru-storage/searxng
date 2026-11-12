# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dogpile is a metasearch engine by the American advertising company `System1`_.

.. _System1: https://system1.com/
"""

import typing as t
from datetime import datetime, timezone, timedelta
import html

from searx.enginelib import EngineCache
from searx.exceptions import SearxEngineAPIException
from searx.network import post
from searx.utils import html_to_text, humanize_number
from searx.result_types import EngineResults

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": "https://www.dogpile.com",
    "wikidata_id": "Q3595363",
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": "JSON",
}

paging = True
safesearch = True

categories = ["general"]
dogpile_categ = "search"
"""Category to search in. Can be either "search", "images", "videos" or "news"."""


base_url = "https://www.dogpile.com"
safe_search_map = {0: "none", 1: "moderate", 2: "heavy"}

referer_map = {
    "search": "/",
    "images": "/images",
    "videos": "/videos",
    "news": "/news",
}
"""The API answers ``403`` (CloudFront "Request blocked") unless the ``Referer``
matches the page the request would originate from."""

_IMPERSONATE = "firefox"
"""TLS fingerprint used by curl_cffi.

Dogpile's edge (CloudFront) answers ``403 Request blocked`` to the fingerprint
of curl_cffi's ``chrome`` profile -- which is SearXNG's default -- while the
``firefox`` profile is served normally.  The profile also supplies a matching
Firefox ``User-Agent`` and header set.
"""

CACHE: EngineCache
"""Cache for the API token from dogpile"""


def setup(_: dict[str, t.Any]) -> bool | None:
    if dogpile_categ not in referer_map:
        raise ValueError("invalid search type: %s" % dogpile_categ)
    global CACHE  # pylint: disable=global-statement
    CACHE = EngineCache("dogpile")  # one token for images/videos/news
    return True


def _obtain_token() -> str:
    token = CACHE.get("token")
    if token:
        return token
    resp = post(
        f"{base_url}/api/token/refresh",
        headers={"Origin": base_url, "Sec-Fetch-Mode": "cors", "Referer": f"{base_url}{referer_map['search']}"},
        cookies={"dp_api_token": "1"},
        impersonate=_IMPERSONATE,
    )
    if not resp.ok:
        raise SearxEngineAPIException("failed to obtain dogpile token")
    payload = resp.json()
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        raise SearxEngineAPIException("failed to obtain dogpile token")
    CACHE.set("token", token, expire=240)  # the token itself is valid for 300s
    return token


def request(query: str, params: "OnlineParams"):
    params["url"] = f"{base_url}/api/{dogpile_categ}"
    params["headers"]["Origin"] = base_url
    # without a matching Referer the API answers 403 (CloudFront "Request blocked")
    params["headers"]["Referer"] = f"{base_url}{referer_map[dogpile_categ]}"
    params["headers"]["Sec-Fetch-Mode"] = "cors"
    params["cookies"]["dp_api_token"] = "1"
    params["headers"]["x-dogpile-token"] = _obtain_token()
    params["impersonate"] = _IMPERSONATE

    params["method"] = "POST"
    params["json"] = {"q": query, "qadf": safe_search_map[params["safesearch"]], "page": params["pageno"]}


def _as_number(value: t.Any) -> float | None:
    """Return *value* as a number, or ``None`` if it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _as_datetime(value: t.Any, from_timestamp: bool = False) -> datetime | None:
    """Convert an API date field into a :py:obj:`datetime`, ``None`` if unknown."""
    if from_timestamp and (number := _as_number(value)) is not None:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def response(resp: "SXNG_Response"):
    res = EngineResults()

    json_resp = resp.json()
    if not isinstance(json_resp, dict):
        raise SearxEngineAPIException("unexpected dogpile response")

    for result in json_resp.get("results") or []:
        url = result.get("clickUrl") or ""
        if not url:
            continue

        if dogpile_categ == "search":
            res.add(
                res.types.MainResult(
                    url=url,
                    title=html_to_text(result.get("title") or ""),
                    content=html_to_text(result.get("description") or ""),
                )
            )
        elif dogpile_categ == "news":
            # news headlines arrive HTML escaped (``&lt;b&gt;``), the other
            # categories carry the markup itself; unescape before stripping it
            res.add(
                res.types.MainResult(
                    url=url,
                    title=html_to_text(html.unescape(result.get("title") or "")),
                    content=html_to_text(html.unescape(result.get("description") or "")),
                    thumbnail=result.get("thumbnailUrl") or "",
                    publishedDate=_as_datetime(result.get("date"), from_timestamp=True),
                )
            )
        elif dogpile_categ == "videos":
            duration = _as_number(result.get("duration"))
            views = _as_number(result.get("viewCount"))
            res.add(
                res.types.Video(
                    url=url,
                    title=html_to_text(result.get("title") or ""),
                    content=html_to_text(result.get("description") or ""),
                    thumbnail=result.get("thumbnailUrl") or "",
                    publishedDate=_as_datetime(result.get("publishDate")),
                    length=timedelta(seconds=duration) if duration is not None else None,
                    views=humanize_number(views) if views is not None else "",
                )
            )
        elif dogpile_categ == "images":
            width = _as_number(result.get("width"))
            height = _as_number(result.get("height"))
            res.add(
                res.types.Image(
                    url=result.get("altClickUrl") or url,
                    title=html_to_text(result.get("title") or ""),
                    content=html_to_text(result.get("description") or ""),
                    img_src=url,
                    thumbnail_src=result.get("thumbnailUrl") or "",
                    resolution=f"{width:g}x{height:g}" if width and height else "",
                    img_format=result.get("format") or "",
                )
            )

    return res
