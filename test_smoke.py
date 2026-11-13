"""Smoke tests — call the tool functions directly (no MCP client needed).

All tests hit the live public APIs, so they need internet.
They assert shape, not exact values: weather/arrivals change.
Run: .venv/bin/python test_smoke.py
"""
import server


def main():
    w = server.get_seattle_weather()
    assert "error" not in w, w
    assert w["temperature"] is not None, w
    assert w["condition"], w
    print("get_seattle_weather OK:", w["temperature"], w["temperature_unit"], w["condition"], w["time"])

    f = server.get_weather_forecast(days=3)
    assert "error" not in f, f
    assert len(f["forecast"]) == 3, f
    print("get_weather_forecast OK:", [(d["date"], d["condition"], d["high"], d["low"]) for d in f["forecast"]])

    p = server.search_place("Bellevue")
    assert "error" not in p and p["results"], p
    print("search_place OK:", p["results"][0])

    stops = server.find_transit_stops()
    assert "error" not in stops, stops
    assert stops["stops"], stops
    first = stops["stops"][0]
    print("find_transit_stops OK:", first["stop_id"], first["name"], "routes:", first["route_ids"][:3])

    arr = server.get_next_arrivals(first["stop_id"])
    assert "error" not in arr, arr
    print("get_next_arrivals OK:", first["stop_id"], "arrivals:", len(arr["arrivals"]),
          arr["arrivals"][0] if arr["arrivals"] else "none in window")

    # get_route_info needs a route id; use one from the stops list
    route_ids = first["route_ids"]
    if route_ids:
        r = server.get_route_info(route_ids[0])
        assert "error" not in r, r
        print("get_route_info OK:", r["route_id"], r["short_name"], r["long_name"], r["agency"])

    combo = server.transit_and_weather(stop_id=first["stop_id"])
    assert "weather" in combo and "nearby_stops" in combo and "arrivals" in combo, combo
    print("transit_and_weather OK")

    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
