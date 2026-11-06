# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,invalid-name,too-few-public-methods

"""wttr.in engine: a body that is not JSON, and a weather code the table lacks."""

import flask
from flask_babel import Babel

from searx.engines import wttr

from tests import SearxTestCase


class _Response:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.search_params = {"query": "Jakarta"}

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


# wttr.in reports 152 (smog); the WWO table has no entry for it.
_CURRENT = {
    "temp_C": "30",
    "weatherCode": "152",
    "FeelsLikeC": "33",
    "winddirDegree": "90",
    "windspeedKmph": "10",
    "pressure": "1008",
    "humidity": "80",
    "cloudcover": "40",
}


class TestWttrEngine(SearxTestCase):
    def test_non_json_body_returns_no_results(self):
        """#6883: a rate limited answer is an HTML page, not a crash."""
        assert not list(wttr.response(_Response()))

    def test_unknown_weather_code_does_not_raise(self):
        """#6883: an unknown code must not take the whole answer down."""
        app = flask.Flask(__name__)
        Babel(app)  # the answer is built through gettext
        with app.test_request_context("/search?q=Jakarta&language=en"):
            results = list(wttr.response(_Response({"current_condition": [_CURRENT], "weather": []})))
        assert results
        assert results[0].current.condition == "fog"
