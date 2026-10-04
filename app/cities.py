"""Supported cities: one place for names, map centres and id prefixes.

A city "contains" every location within CITY_RADIUS_M of its centre. Urgent searches
and new points are assigned to the city they are in, whatever city the map shows.
"""
from app.urgent import haversine_m

CITY_RADIUS_M = 30_000

CITIES = {
    "krakow":   {"name": "Kraków",   "center": (50.0614, 19.9383), "prefix": "krk"},
    "warszawa": {"name": "Warszawa", "center": (52.2297, 21.0122), "prefix": "waw"},
    "wroclaw":  {"name": "Wrocław",  "center": (51.1100, 17.0325), "prefix": "wro"},
    "gdansk":   {"name": "Gdańsk",   "center": (54.3520, 18.6466), "prefix": "gda"},
}
DEFAULT_CITY = "krakow"


def city_for(lat: float, lon: float) -> str | None:
    """The city this location belongs to, or None if it is outside all of them."""
    best, best_d = None, CITY_RADIUS_M
    for code, city in CITIES.items():
        d = haversine_m(lat, lon, *city["center"])
        if d <= best_d:
            best, best_d = code, d
    return best


def inside_city(code: str, lat: float, lon: float) -> bool:
    city = CITIES.get(code)
    return bool(city) and haversine_m(lat, lon, *city["center"]) <= CITY_RADIUS_M
