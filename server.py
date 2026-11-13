"""Seattle Transit + Weather MCP server.

Personal portfolio project, independent of any employer.
Live data only, from public APIs — nothing is invented:
- Weather: Open-Meteo (https://api.open-meteo.com), free, no API key.
  Non-commercial use, CC BY 4.0 attribution.
- Transit: OneBusAway Puget Sound
  (https://api.pugetsound.onebusaway.org), covering King County Metro,
  Sound Transit Link light rail, Pierce Transit, Community Transit,
  Kitsap Transit, Washington State Ferries and others.
  API key from env OBA_API_KEY; defaults to "TEST", which OneBusAway
  documents as working on the Puget Sound instance for development.
  For regular use, get a free key at developers.onebusaway.org and
  set OBA_API_KEY — do not rely on TEST in production.

Honest limits, stated in every tool that needs them:
- Live arrivals are predicted times when a vehicle is GPS-tracked,
  otherwise scheduled times. A predicted time is not a guarantee.
- This server does no trip routing / trip planning. OneBusAway
  defers routing to OpenTripPlanner; this server returns stops,
  routes, and next arrivals only.
- Weather is a forecast, not an observation at your exact street.
  Times are in the requested timezone (America/Los_Angeles default).
"""
import os
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("seattle-transit-weather")

OBA_BASE = os.environ.get(
    "ONEBUSAWAY_BASE_URL", "https://api.pugetsound.onebusaway.org/api/where"
)
OBA_KEY = os.environ.get("OBA_API_KEY", "TEST")
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

# Seattle defaults: downtown Seattle.
SEATTLE_LAT = 47.6062
SEATTLE_LON = -122.3321
DEFAULT_TZ = "America/Los_Angeles"

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


# This VM's egress proxy does TLS interception with a CA that lives in the
# system bundle but not in certifi's. Use the system bundle, and pass the
# proxy explicitly: httpx chokes parsing this shell's no_proxy list.
# (Same pattern as the Seattle Restaurants server.)
_SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"


def _client() -> httpx.Client:
    return httpx.Client(
        proxy=os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"),
        trust_env=False,
        verify=_SYSTEM_CA if os.path.exists(_SYSTEM_CA) else True,
        headers={"User-Agent": "SeattleTransitWeatherMCP/1.0 (portfolio project)"},
        timeout=20,
    )


def _get(url, params=None):
    try:
        with _client() as client:
            r = client.get(url, params=params)
    except Exception as e:  # network failure, not a data answer
        return {"error": f"Upstream request failed: {e}"}
    if r.status_code == 429:
        return {"error": "Upstream rate limit (HTTP 429). Wait a minute and retry; do not hammer the API."}
    if r.status_code != 200:
        return {"error": f"Upstream returned HTTP {r.status_code} for {url}"}
    try:
        return r.json()
    except Exception:
        return {"error": "Upstream returned a response that was not JSON."}


def _c_to_f(c):
    return round(c * 9 / 5 + 32, 1) if c is not None else None


def _mins_from_now(ms):
    if not ms:
        return None
    return round((ms / 1000 - datetime.now(timezone.utc).timestamp()) / 60, 1)


@mcp.tool()
def search_place(name: str, count: int = 5) -> dict:
    """Geocode a place name to latitude/longitude via Open-Meteo.

    Use this first when you only have a place name (e.g. "Bellevue",
    "SeaTac Airport", "University District"). Returns matches with
    lat/lon, admin area, country, population and timezone.
    """
    if not name.strip():
        return {"error": "name must not be empty"}
    data = _get(OPEN_METEO_GEOCODE, {"name": name, "count": max(1, min(count, 10)), "format": "json"})
    if "error" in data:
        return data
    results = data.get("results") or []
    if not results:
        return {"query": name, "results": [], "note": "No place matched that name. Try a broader name, e.g. a city instead of a street."}
    return {
        "query": name,
        "results": [
            {
                "name": r.get("name"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "admin1": r.get("admin1"),
                "country": r.get("country"),
                "population": r.get("population"),
                "timezone": r.get("timezone"),
            }
            for r in results
        ],
        "source": "Open-Meteo Geocoding API, live.",
    }


@mcp.tool()
def get_seattle_weather(latitude: float = SEATTLE_LAT, longitude: float = SEATTLE_LON,
                        temperature_unit: str = "fahrenheit") -> dict:
    """Current weather at a location (default: downtown Seattle).

    Live from Open-Meteo. temperature_unit: "fahrenheit" or "celsius".
    Returns temperature, feels-like, humidity, precipitation, wind
    and a plain-language sky description. This is a forecast-model
    current value, not a street-level observation.
    """
    unit = temperature_unit.lower()
    if unit not in ("fahrenheit", "celsius"):
        return {"error": 'temperature_unit must be "fahrenheit" or "celsius"'}
    data = _get(OPEN_METEO_FORECAST, {
        "latitude": latitude, "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
        "temperature_unit": unit, "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
        "timezone": DEFAULT_TZ,
    })
    if "error" in data:
        return data
    cur = data.get("current") or {}
    code = cur.get("weather_code")
    return {
        "latitude": data.get("latitude"), "longitude": data.get("longitude"),
        "timezone": data.get("timezone"), "time": cur.get("time"),
        "temperature": cur.get("temperature_2m"),
        "temperature_unit": "F" if unit == "fahrenheit" else "C",
        "feels_like": cur.get("apparent_temperature"),
        "relative_humidity_pct": cur.get("relative_humidity_2m"),
        "precipitation": cur.get("precipitation"),
        "weather_code": code,
        "condition": WMO_CODES.get(code, "Unknown"),
        "wind_speed": cur.get("wind_speed_10m"),
        "wind_direction_deg": cur.get("wind_direction_10m"),
        "source": "Open-Meteo, live. CC BY 4.0.",
        "note": "Forecast-model current value for these coordinates, not a street-level observation.",
    }


@mcp.tool()
def get_weather_forecast(latitude: float = SEATTLE_LAT, longitude: float = SEATTLE_LON,
                         days: int = 7, temperature_unit: str = "fahrenheit") -> dict:
    """Daily weather forecast for up to 16 days (default 7, Seattle).

    Live from Open-Meteo. Each day: high/low, condition, precipitation
    chance, max wind. Use search_place first if you only have a name.
    """
    if not (1 <= days <= 16):
        return {"error": "days must be between 1 and 16"}
    unit = temperature_unit.lower()
    if unit not in ("fahrenheit", "celsius"):
        return {"error": 'temperature_unit must be "fahrenheit" or "celsius"'}
    data = _get(OPEN_METEO_FORECAST, {
        "latitude": latitude, "longitude": longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "temperature_unit": unit, "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
        "timezone": DEFAULT_TZ, "forecast_days": days,
    })
    if "error" in data:
        return data
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    forecast = []
    for i, d in enumerate(dates):
        code = (daily.get("weather_code") or [None] * len(dates))[i]
        forecast.append({
            "date": d,
            "condition": WMO_CODES.get(code, "Unknown"),
            "high": (daily.get("temperature_2m_max") or [None] * len(dates))[i],
            "low": (daily.get("temperature_2m_min") or [None] * len(dates))[i],
            "precipitation_probability_max_pct": (daily.get("precipitation_probability_max") or [None] * len(dates))[i],
            "wind_speed_max": (daily.get("wind_speed_10m_max") or [None] * len(dates))[i],
        })
    return {
        "latitude": data.get("latitude"), "longitude": data.get("longitude"),
        "timezone": data.get("timezone"), "temperature_unit": "F" if unit == "fahrenheit" else "C",
        "forecast": forecast,
        "source": "Open-Meteo, live. CC BY 4.0.",
    }


@mcp.tool()
def find_transit_stops(latitude: float = SEATTLE_LAT, longitude: float = SEATTLE_LON,
                       radius_meters: int = 500) -> dict:
    """Find transit stops near a location, live from OneBusAway Puget Sound.

    Covers King County Metro, Sound Transit Link, Pierce/Community/
    Kitsap Transit and others in the region. Returns stop id, name,
    direction, coordinates and the route ids serving it.
    Use the stop id with get_next_arrivals.
    """
    if not (100 <= radius_meters <= 5000):
        return {"error": "radius_meters must be between 100 and 5000"}
    data = _get(f"{OBA_BASE}/stops-for-location.json",
                {"key": OBA_KEY, "lat": latitude, "lon": longitude, "radius": radius_meters})
    if "error" in data:
        return data
    stops = (data.get("data") or {}).get("list") or []
    return {
        "latitude": latitude, "longitude": longitude, "radius_meters": radius_meters,
        "limit_exceeded": (data.get("data") or {}).get("limitExceeded"),
        "stops": [
            {
                "stop_id": s.get("id"), "stop_code": s.get("code"),
                "name": s.get("name"), "direction": s.get("direction"),
                "latitude": s.get("lat"), "longitude": s.get("lon"),
                "route_ids": s.get("routeIds") or [],
                "wheelchair_boarding": s.get("wheelchairBoarding"),
            }
            for s in stops
        ],
        "source": "OneBusAway Puget Sound, live.",
        "note": "Stop ids look like 1_75403. Pass one to get_next_arrivals for live times.",
    }


@mcp.tool()
def get_next_arrivals(stop_id: str, minutes_after: int = 35) -> dict:
    """Live next arrivals/departures at a OneBusAway stop id (e.g. 1_75403).

    Returns route, headsign, scheduled vs predicted time, minutes away,
    and how late/early the vehicle is when a prediction exists.
    Predicted = GPS-tracked vehicle; otherwise the scheduled time is
    shown and labelled as scheduled, not predicted. A predicted time
    is not a guarantee the bus will arrive then.
    """
    if not stop_id.strip():
        return {"error": "stop_id must not be empty, e.g. 1_75403"}
    if not (5 <= minutes_after <= 240):
        return {"error": "minutes_after must be between 5 and 240"}
    data = _get(f"{OBA_BASE}/arrivals-and-departures-for-stop/{stop_id}.json",
                {"key": OBA_KEY, "minutesAfter": minutes_after})
    if "error" in data:
        return data
    entry = (data.get("data") or {}).get("entry") or {}
    refs = (data.get("data") or {}).get("references") or {}
    routes = {r.get("id"): r for r in refs.get("routes") or []}
    arrivals = []
    for a in entry.get("arrivalsAndDepartures") or []:
        route = routes.get(a.get("routeId")) or {}
        pred_ms = a.get("predictedArrivalTime") or a.get("predictedDepartureTime")
        sched_ms = a.get("scheduledArrivalTime") or a.get("scheduledDepartureTime")
        delay_s = None
        if pred_ms and sched_ms:
            delay_s = round((pred_ms - sched_ms) / 1000)
        arrivals.append({
            "route": a.get("routeShortName") or route.get("shortName"),
            "route_long_name": route.get("longName"),
            "headsign": a.get("tripHeadsign"),
            "stop_id": a.get("stopId"),
            "predicted": bool(a.get("predicted")),
            "minutes_away": _mins_from_now(pred_ms) if pred_ms else _mins_from_now(sched_ms),
            "scheduled_time": datetime.fromtimestamp(sched_ms / 1000, tz=timezone.utc).astimezone().isoformat() if sched_ms else None,
            "predicted_time": datetime.fromtimestamp(pred_ms / 1000, tz=timezone.utc).astimezone().isoformat() if pred_ms else None,
            "delay_seconds": delay_s,
            "status": a.get("status"),
            "service_alerts": a.get("situationIds") or [],
        })
    return {
        "stop_id": stop_id,
        "stop_name": (entry.get("stop") or {}).get("name"),
        "arrivals": arrivals,
        "source": "OneBusAway Puget Sound, live.",
        "note": "Predicted times are GPS-based estimates, not guarantees. No prediction means the scheduled time is shown.",
    }


@mcp.tool()
def get_route_info(route_id: str) -> dict:
    """Live route details from OneBusAway (e.g. 1_102768 for route 72).

    Returns short/long name, agency, type and description when the
    upstream API provides them. Get route ids from find_transit_stops.
    """
    if not route_id.strip():
        return {"error": "route_id must not be empty, e.g. 1_102768"}
    data = _get(f"{OBA_BASE}/route/{route_id}.json", {"key": OBA_KEY})
    if "error" in data:
        return data
    entry = (data.get("data") or {}).get("entry") or {}
    refs = (data.get("data") or {}).get("references") or {}
    agencies = {a.get("id"): a for a in refs.get("agencies") or []}
    agency = agencies.get(entry.get("agencyId")) or {}
    return {
        "route_id": entry.get("id"),
        "short_name": entry.get("shortName"),
        "long_name": entry.get("longName"),
        "description": entry.get("description"),
        "type": entry.get("type"),
        "agency": agency.get("name"),
        "agency_id": entry.get("agencyId"),
        "url": entry.get("url"),
        "source": "OneBusAway Puget Sound, live.",
    }


@mcp.tool()
def transit_and_weather(latitude: float = SEATTLE_LAT, longitude: float = SEATTLE_LON,
                        stop_id: str = "") -> dict:
    """One call: current Seattle-area weather + nearby stops (+ arrivals).

    Weather is live from Open-Meteo; stops are live from OneBusAway.
    If stop_id is given, next arrivals for that stop are included;
    otherwise only the nearest stops are listed — arrivals are not
    guessed for a stop you did not name. No trip routing is done.
    """
    weather = get_seattle_weather(latitude, longitude)
    stops = find_transit_stops(latitude, longitude)
    result = {
        "weather": weather,
        "nearby_stops": stops,
        "note": "Weather + stops are live. Arrivals need a stop_id; this tool does not invent a route or a departure time.",
    }
    if stop_id.strip():
        result["arrivals"] = get_next_arrivals(stop_id)
    return result


if __name__ == "__main__":
    mcp.run()
