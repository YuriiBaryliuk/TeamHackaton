"""DEMO boxes, demand profiles and Urgent-search clusters for Warszawa, Wrocław and Gdańsk.

Everything here is ILLUSTRATIVE (is_demo = 1): plausible places (main station, old town,
universities, residential districts), not real partner venues. The real data for these
cities (public toilets and pharmacies) comes from OpenStreetMap, see seed_osm.py.
"""
WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ALWAYS = {"always": True}


def every_day(a: str, b: str) -> dict:
    return {d: [a, b] for d in WEEK}


def weekdays(a: str, b: str, sat: list | None = None) -> dict:
    h = {d: [a, b] for d in WEEK[:5]}
    if sat:
        h["sat"] = sat
    return h


# Demand profiles (same meaning as PROFILES in seed_demo_events.py):
#   per_day items taken per day, capacity after a refill, gap hours empty -> refill,
#   stale = no reports in the last N hours (faded / unknown on the map).
PROFILE_TYPES = {
    "station": dict(per_day=12, capacity=20, gap=(30, 60)),   # busy, slow refills: white spot story
    "busy":    dict(per_day=8, capacity=25, gap=(4, 16)),
    "cafe":    dict(per_day=5, capacity=20, gap=(3, 12)),
    "quiet":   dict(per_day=3, capacity=15, gap=(12, 36)),
    "faded":   dict(per_day=3, capacity=15, gap=(12, 36), stale=45),
    "stale":   dict(per_day=2, capacity=15, gap=(24, 72), stale=100),
}

# city -> [(id, name, kind, lat, lon, address, access, opening_hours, wheelchair, has_products, has_qr, profile)]
DEMO_POINTS = {
    "warszawa": [
        ("waw-0001", "Kawiarnia na Starym Mieście", "partner", 52.24930, 21.01270, "okolice Rynku Starego Miasta", "ask_staff", every_day("08:00", "22:00"), 0, 1, 1, "cafe"),
        ("waw-0002", "Dworzec Warszawa Centralna: toaleta w hali", "partner", 52.22870, 21.00350, "Dworzec Warszawa Centralna", "open", ALWAYS, 1, 1, 1, "station"),
        ("waw-0003", "Uniwersytet: kampus główny", "university", 52.23980, 21.01930, "okolice Krakowskiego Przedmieścia", "open", weekdays("07:30", "21:00", ["08:00", "16:00"]), 1, 1, 1, "busy"),
        ("waw-0004", "Politechnika: Gmach Główny", "university", 52.22060, 21.01030, "okolice placu Politechniki", "open", weekdays("07:30", "20:00"), 1, 1, 1, "busy"),
        ("waw-0005", "Biblioteka: Praga", "partner", 52.25250, 21.04000, "okolice ul. Ząbkowskiej", "open", weekdays("10:00", "19:00"), 1, 1, 1, "faded"),
        ("waw-0006", "Dom kultury: Mokotów", "pink_box", 52.19350, 21.02300, "okolice ul. Puławskiej", "open", weekdays("10:00", "20:00", ["10:00", "16:00"]), 1, 1, 1, "quiet"),
        ("waw-0007", "Liceum na Ursynowie", "school", 52.15000, 21.04500, "okolice al. KEN", "students_only", weekdays("07:30", "16:00"), 1, 1, 1, "stale"),
    ],
    "wroclaw": [
        ("wro-0001", "Kawiarnia przy Rynku", "partner", 51.11020, 17.03100, "okolice Rynku", "ask_staff", every_day("08:00", "22:00"), 0, 1, 1, "cafe"),
        ("wro-0002", "Dworzec Wrocław Główny: toaleta w hali", "partner", 51.09810, 17.03640, "Dworzec Wrocław Główny", "open", ALWAYS, 1, 1, 1, "station"),
        ("wro-0003", "Uniwersytet: Gmach Główny", "university", 51.11410, 17.03440, "okolice placu Uniwersyteckiego", "open", weekdays("07:30", "21:00", ["08:00", "15:00"]), 1, 1, 1, "busy"),
        ("wro-0004", "Politechnika: plac Grunwaldzki", "university", 51.10730, 17.06100, "okolice placu Grunwaldzkiego", "open", weekdays("07:30", "20:00"), 1, 1, 1, "busy"),
        ("wro-0005", "Biblioteka: Nadodrze", "partner", 51.12050, 17.03000, "okolice ul. Jedności Narodowej", "open", weekdays("10:00", "19:00"), 1, 1, 1, "faded"),
        ("wro-0006", "Dom kultury: Krzyki", "pink_box", 51.07500, 17.01300, "okolice ul. Powstańców Śląskich", "open", weekdays("10:00", "20:00", ["10:00", "16:00"]), 1, 1, 1, "quiet"),
        ("wro-0007", "Szkoła: Psie Pole", "school", 51.14500, 17.11000, "okolice ul. Bierutowskiej", "students_only", weekdays("07:30", "16:00"), 1, 1, 1, "stale"),
    ],
    "gdansk": [
        ("gda-0001", "Kawiarnia przy Długim Targu", "partner", 54.34860, 18.65250, "okolice Długiego Targu", "ask_staff", every_day("08:00", "22:00"), 0, 1, 1, "cafe"),
        ("gda-0002", "Dworzec Gdańsk Główny: toaleta w hali", "partner", 54.35560, 18.64470, "Dworzec Gdańsk Główny", "open", ALWAYS, 1, 1, 1, "station"),
        ("gda-0003", "Uniwersytet: kampus Oliwa", "university", 54.39600, 18.57350, "okolice ul. Bażyńskiego", "open", weekdays("07:30", "21:00", ["08:00", "15:00"]), 1, 1, 1, "busy"),
        ("gda-0004", "Politechnika: Gmach Główny", "university", 54.37120, 18.61950, "okolice ul. Narutowicza", "open", weekdays("07:30", "20:00"), 1, 1, 1, "busy"),
        ("gda-0005", "Biblioteka: Wrzeszcz", "partner", 54.38100, 18.60500, "okolice ul. Grunwaldzkiej", "open", weekdays("10:00", "19:00"), 1, 1, 1, "faded"),
        ("gda-0006", "Centrum kultury: Przymorze", "pink_box", 54.40900, 18.59000, "okolice ul. Obrońców Wybrzeża", "open", weekdays("10:00", "20:00", ["10:00", "16:00"]), 1, 1, 1, "quiet"),
        ("gda-0007", "Szkoła: Chełm", "school", 54.33400, 18.61700, "okolice ul. Cieszyńskiego", "students_only", weekdays("07:30", "16:00"), 1, 1, 1, "stale"),
    ],
}

# Boxes refilled shortly before "now" so Urgent in the centre finds something during a demo.
REFILL_RECENTLY = ["waw-0001", "wro-0001", "gda-0001"]

# (centre lat, centre lon, number of searches, probability something was found)
SEARCH_CLUSTERS = {
    "warszawa": [
        (52.2289, 21.0032, 110, 0.15),   # Centralna station: white spot
        (52.1450, 21.0480, 70, 0.10),    # Ursynów: white spot
        (52.2390, 20.9130, 30, 0.20),    # Bemowo
        (52.2490, 21.0120, 90, 0.90),    # Old Town
        (52.2400, 21.0190, 60, 0.85),    # University
    ],
    "wroclaw": [
        (51.0983, 17.0367, 90, 0.15),    # main station: white spot
        (51.1470, 17.1130, 60, 0.10),    # Psie Pole: white spot
        (51.1250, 16.9500, 30, 0.20),    # Nowy Dwór
        (51.1100, 17.0320, 80, 0.90),    # Rynek
        (51.1073, 17.0610, 50, 0.85),    # plac Grunwaldzki
    ],
    "gdansk": [
        (54.3557, 18.6440, 80, 0.15),    # main station: white spot
        (54.3330, 18.6150, 60, 0.10),    # Chełm: white spot
        (54.3940, 18.6020, 30, 0.20),    # Zaspa
        (54.3486, 18.6525, 70, 0.90),    # Długi Targ
        (54.3960, 18.5735, 50, 0.85),    # Oliwa campus
    ],
}


def profiles() -> dict:
    """point id -> demand profile, for seed_demo_events."""
    return {p[0]: PROFILE_TYPES[p[-1]] for pts in DEMO_POINTS.values() for p in pts}
