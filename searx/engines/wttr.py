# SPDX-License-Identifier: AGPL-3.0-or-later
"""wttr.in (weather forecast service)"""

import logging
import typing as t

from urllib.parse import quote
from datetime import datetime

from searx.result_types import EngineResults, WeatherAnswer
from searx import weather

logger = logging.getLogger(__name__)

about = {
    "website": "https://wttr.in",
    "wikidata_id": "Q107586666",
    "official_api_documentation": "https://github.com/chubin/wttr.in#json-output",
    "use_official_api": True,
    "require_api_key": False,
    "results": "JSON",
}

categories = ["weather"]

url = "https://wttr.in/{query}?format=j1&lang={lang}"

# WWO (World Weather Online) condition codes as reported by wttr.in.  The
# meaning of each code follows wttr.in's own condition table:
#   https://github.com/chubin/wttr.in/blob/master/share/translations/en/conditions.txt
# Each code is mapped to the closest searx.weather.WeatherConditionType.
WWO_TO_CONDITION: dict[str, weather.WeatherConditionType] = {
    "113": "clear sky",                 # Clear / Sunny
    "116": "partly cloudy",             # Partly cloudy
    "119": "cloudy",                    # Cloudy
    "122": "cloudy",                    # Overcast
    "143": "fog",                       # Mist
    "152": "fog",                       # smog: wttr.in reports it, not in the WWO table
    "176": "light rain showers",        # Patchy rain possible
    "179": "light snow showers",        # Patchy snow possible
    "182": "light sleet showers",       # Patchy sleet possible
    "185": "light sleet",               # Patchy freezing drizzle possible
    "200": "rain and thunder",          # Thundery outbreaks possible
    "227": "snow",                      # Blowing snow
    "230": "heavy snow",                # Blizzard
    "248": "fog",                       # Fog
    "260": "fog",                       # Freezing fog
    "263": "light rain",                # Patchy light drizzle
    "266": "light rain",                # Light drizzle
    "281": "light sleet",               # Freezing drizzle
    "284": "sleet",                     # Heavy freezing drizzle
    "293": "light rain",                # Patchy light rain
    "296": "light rain",                # Light rain
    "299": "rain",                      # Moderate rain at times
    "302": "rain",                      # Moderate rain
    "305": "heavy rain",                # Heavy rain at times
    "308": "heavy rain",                # Heavy rain
    "311": "light sleet",               # Light freezing rain
    "314": "sleet",                     # Moderate or heavy freezing rain
    "317": "light sleet",               # Light sleet
    "320": "heavy sleet",               # Moderate or heavy sleet
    "323": "light snow",                # Patchy light snow
    "326": "light snow",                # Light snow
    "329": "snow",                      # Patchy moderate snow
    "332": "snow",                      # Moderate snow
    "335": "heavy snow",                # Patchy heavy snow
    "338": "heavy snow",                # Heavy snow
    "350": "sleet",                     # Ice pellets
    "353": "light rain showers",        # Light rain shower
    "356": "heavy rain showers",        # Moderate or heavy rain shower
    "359": "heavy rain showers",        # Torrential rain shower
    "362": "light sleet showers",       # Light sleet showers
    "365": "heavy sleet showers",       # Moderate or heavy sleet showers
    "368": "light snow showers",        # Light snow showers
    "371": "heavy snow showers",        # Moderate or heavy snow showers
    "374": "light sleet showers",       # Light showers of ice pellets
    "377": "heavy sleet showers",       # Moderate or heavy showers of ice pellets
    "386": "light rain and thunder",    # Patchy light rain with thunder
    "389": "heavy rain and thunder",    # Moderate or heavy rain with thunder
    "392": "light snow and thunder",    # Patchy light snow with thunder
    "395": "heavy snow and thunder",    # Moderate or heavy snow with thunder
}


def request(query, params):
    params["url"] = url.format(query=quote(query), lang=params["language"])
    params["raise_for_httperror"] = False

    return params


def _weather_data(location: weather.GeoLocation, data: dict[str, t.Any]):
    # the naming between different data objects is inconsitent, thus temp_C and
    # tempC are possible
    tempC: float = data.get("temp_C") or data.get("tempC")  # type: ignore

    return WeatherAnswer.Item(
        location=location,
        temperature=weather.Temperature(val=tempC, unit="°C"),
        condition=WWO_TO_CONDITION.get(data["weatherCode"], "fog"),
        feels_like=weather.Temperature(val=data["FeelsLikeC"], unit="°C"),
        wind_from=weather.Compass(int(data["winddirDegree"])),
        wind_speed=weather.WindSpeed(val=data["windspeedKmph"], unit="km/h"),
        pressure=weather.Pressure(val=data["pressure"], unit="hPa"),
        humidity=weather.RelativeHumidity(data["humidity"]),
        cloud_cover=data["cloudcover"],
    )


def response(resp):
    res = EngineResults()

    if resp.status_code == 404:
        return res

    try:
        json_data = resp.json()
    except ValueError:
        # wttr.in answers with an HTML error page or an empty body when it is
        # rate limited; that is not a reason to raise (#6883).
        logger.warning("wttr.in returned a non-JSON body, status %s", resp.status_code)
        return res
    geoloc = weather.GeoLocation.by_query(resp.search_params["query"])

    weather_answer = WeatherAnswer(
        current=_weather_data(geoloc, json_data["current_condition"][0]),
        service="wttr.in",
    )

    for day in json_data["weather"]:
        date = datetime.fromisoformat(day["date"])
        time_slot_len = 24 // len(day["hourly"])
        for index, forecast in enumerate(day["hourly"]):
            forecast_data = _weather_data(geoloc, forecast)
            forecast_data.datetime = weather.DateTime(date.replace(hour=index * time_slot_len + 1))
            weather_answer.forecasts.append(forecast_data)

    res.add(weather_answer)
    return res
