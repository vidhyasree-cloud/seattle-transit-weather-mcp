# Seattle Transit + Weather MCP Server

Personal portfolio project, independent of any employer.

A Python + FastMCP server that gives Claude Desktop live Seattle-area
transit and weather, from public APIs only (stdio transport).

## Tools

| Tool | What it does |
| --- | --- |
| `search_place` | Geocode a place name to lat/lon (Open-Meteo geocoding) |
| `get_seattle_weather` | Current weather, default downtown Seattle (Open-Meteo, live) |
| `get_weather_forecast` | Daily forecast, 1–16 days, default 7 (Open-Meteo, live) |
| `find_transit_stops` | Stops near a location (OneBusAway Puget Sound, live) |
| `get_next_arrivals` | Live next arrivals at a stop id, predicted vs scheduled |
| `get_route_info` | Route details for a OneBusAway route id |
| `transit_and_weather` | Weather + nearby stops in one call, plus arrivals if a stop id is given |

## Data sources (live only — nothing invented)

- **Weather: Open-Meteo** — free, no API key, non-commercial use,
  CC BY 4.0 attribution. Forecast-model values, not street-level
  observations.
- **Transit: OneBusAway Puget Sound** — King County Metro, Sound Transit
  Link light rail, Pierce Transit, Community Transit, Kitsap Transit,
  Washington State Ferries and others.
  - API key: env `OBA_API_KEY`, defaults to `TEST`, which OneBusAway
    documents as working on the Puget Sound instance for development.
  - For regular use, get a free key at developers.onebusaway.org and
    set `OBA_API_KEY`. Do not rely on `TEST` in production.
  - Rate limits apply (~20 req/min on the Puget Sound instance);
    the server surfaces HTTP 429 instead of retrying silently.

## Honest limits

- Live arrivals are predicted times when a vehicle is GPS-tracked,
  otherwise scheduled times. A predicted time is not a guarantee.
- **No trip routing / trip planning.** OneBusAway defers routing to
  OpenTripPlanner. This server returns stops, routes, and next
  arrivals only — it will not plan a route from A to B.
- Weather is a forecast for the coordinates given, not an observation
  at your exact street. Times are America/Los_Angeles by default.
- If an upstream API is down or rate-limited, the tool returns an
  error saying so — it does not fall back to invented times.

## Run

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

A stdio MCP server prints nothing and waits for a client — that is normal.
Connect it in Claude Desktop via `mcpServers` in `claude_desktop_config.json`.
On Vidya's PC, edit the **Local** config file, not the Roaming one:
`C:\Users\Vidhya_Devaraju\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude_desktop_config.json`
(quit Claude fully via Task Manager first).

```json
"seattle-transit-weather": {
  "command": "C:\\Users\\Vidhya_Devaraju\\seattle-transit-weather-mcp\\.venv\\Scripts\\python.exe",
  "args": ["C:\\Users\\Vidhya_Devaraju\\seattle-transit-weather-mcp\\server.py"],
  "env": { "OBA_API_KEY": "TEST" }
}
```

Replace `TEST` with your own OneBusAway key when you get one.
Never paste an API key in chat — paste it only into the config file.
