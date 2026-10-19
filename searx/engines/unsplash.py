# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unsplash"""

from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from json import loads

# Anubis lets link-preview fetchers through while challenging browsers and the
# SearXNG agent, so this engine identifies as one.
UNSPLASH_USER_AGENT = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"

# about
about = {
    "website": 'https://unsplash.com',
    "wikidata_id": 'Q28233552',
    "official_api_documentation": 'https://unsplash.com/developers',
    "use_official_api": False,
    "require_api_key": False,
    "results": 'JSON',
}

base_url = 'https://unsplash.com/'
search_url = base_url + 'napi/search/photos?'
categories = ["stock images"]
page_size = 20
paging = True


def clean_url(url):
    parsed = urlparse(url)
    query = [(k, v) for (k, v) in parse_qsl(parsed.query) if k != 'ixid']

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def request(query, params):
    params['url'] = search_url + urlencode({'query': query, 'page': params['pageno'], 'per_page': page_size})
    logger.debug("query_url --> %s", params['url'])

    # Unsplash protects its API with Anubis (https://anubis.techaro.lol/).
    # Common browser user agents and the SearXNG agent now both get a 401
    # challenge, but agents that only ever fetch link previews are still let
    # through, so we present one of those.
    params["headers"]["User-Agent"] = UNSPLASH_USER_AGENT

    return params


def response(resp):
    results = []
    json_data = loads(resp.text)

    if 'results' in json_data:
        for result in json_data['results']:
            results.append(
                {
                    'template': 'images.html',
                    'url': clean_url(result['links']['html']),
                    'thumbnail_src': clean_url(result['urls']['thumb']),
                    'img_src': clean_url(result['urls']['regular']),
                    'title': result.get('alt_description') or 'unknown',
                    'content': result.get('description') or '',
                }
            )

    return results
