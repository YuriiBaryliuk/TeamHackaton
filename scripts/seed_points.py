"""Seed Kraków points. Safe to run many times (upsert by id).

    python -m scripts.seed_points

1. REAL data: public toilets from the city's open dataset
   "ZIW Toalety miejskie" (https://msip.krakow.pl/dataset/3121), read from the
   city's ArcGIS server, which returns WGS84 coordinates directly (outSR=4326),
   so no coordinate conversion is needed. A snapshot is saved to
   data/krakow_toilets.geojson and used when the server cannot be reached.
   Imported as kind='city_toilet', entry_fee_pln=2, has_products=0, is_demo=0.
   Ids: krk-1000 + the dataset's own object id, so they stay stable.

2. DEMO data: about 25 hand-made points (cafés, libraries, universities,
   pharmacies, shops). Names and exact positions are ILLUSTRATIVE.
   All have is_demo=1. Ids: krk-0001 ... plus krk-demo for the stage sticker.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date

from app.db import BASE_DIR, connect, init_db, to_iso, utc_now
from scripts import demo_cities

TOILETS_URL = "https://msip.um.krakow.pl/arcgis/rest/services/Obserwatorium/WT_WC_2023/MapServer/0/query"
TOILETS_FIELDS = "ESRI_OID,miejsce,dzielnica,godziny,dni,status,nplnsprw,rodz_ob,sezon,uwagi"
TOILETS_CACHE = BASE_DIR / "data" / "krakow_toilets.geojson"
TOILET_FEE_PLN = 2.0
TOILET_ID_OFFSET = 1000

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_GROUPS = {
    "codziennie": ALL_DAYS,
    "pn-pt": ALL_DAYS[:5],
    "pn-sb": ALL_DAYS[:6],
    "sb-nd": ALL_DAYS[5:],
}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}

# One segment of the "godziny" text, e.g. "pn-pt 9.00-18.00" or "8.00-20.00 (IV-X)".
SEGMENT_RE = re.compile(
    r"^(?:(?P<days>pn-pt|sb-nd|pn-sb)\s+)?"
    r"(?P<h1>\d{1,2})\.(?P<m1>\d{2})\s*-\s*(?P<h2>\d{1,2})\.(?P<m2>\d{2})"
    r"(?:\s*\((?P<s1>[IVX]+)\s*-\s*(?P<s2>[IVX]+)\))?$",
    re.IGNORECASE,
)


# ---------- real data: city toilets ----------

def download_toilets() -> dict | None:
    params = urllib.parse.urlencode({"where": "1=1", "outFields": TOILETS_FIELDS, "outSR": 4326, "f": "geojson"})
    try:
        with urllib.request.urlopen(f"{TOILETS_URL}?{params}", timeout=20) as r:
            data = json.load(r)
        if not data.get("features"):
            raise ValueError("no features in response")
        TOILETS_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Downloaded {len(data['features'])} toilets from the city server, snapshot saved.")
        return data
    except Exception as e:  # network down, server changed, ...: do not block
        print(f"Could not download toilets ({e}).")
        if TOILETS_CACHE.exists():
            print(f"Using the saved snapshot {TOILETS_CACHE.name}.")
            return json.loads(TOILETS_CACHE.read_text(encoding="utf-8"))
        print("No snapshot either: skipping city toilets.")
        return None


def in_season(start: str, end: str, month: int) -> bool:
    a, b = ROMAN[start], ROMAN[end]
    return a <= month <= b if a <= b else (month >= a or month <= b)  # XI-III wraps over new year


def parse_toilet_hours(godziny: str, dni: str, month: int) -> dict:
    """Turn the dataset's free text into our opening_hours JSON.

    Examples: 'całodobowo' + 'Codziennie' -> {"always": true}
              '9.00-17.00' + 'pn-pt'      -> mon..fri 09:00-17:00
              '8.00-20.00 (IV-X), 9.00-18.00 (XI-III)' -> the segment for the current month
    """
    default_days = DAY_GROUPS.get(dni.strip().lower(), ALL_DAYS)
    if godziny.strip().lower() == "całodobowo":
        if default_days == ALL_DAYS:
            return {"always": True}
        return {d: ["00:00", "24:00"] for d in default_days}

    hours: dict = {}
    for segment in godziny.split(","):
        m = SEGMENT_RE.match(segment.strip())
        if not m:
            raise ValueError(f"cannot parse opening hours segment: {segment!r}")
        if m["s1"] and not in_season(m["s1"].upper(), m["s2"].upper(), month):
            continue
        days = DAY_GROUPS[m["days"].lower()] if m["days"] else default_days
        span = [f"{int(m['h1']):02d}:{m['m1']}", f"{int(m['h2']):02d}:{m['m2']}"]
        for d in days:
            hours[d] = span
    if not hours:
        raise ValueError(f"no opening hours for this month in {godziny!r}")
    return hours


def toilet_rows(geojson: dict, now_iso: str, month: int) -> list[dict]:
    rows, skipped = [], 0
    for f in geojson["features"]:
        p = f["properties"]
        if (p.get("status") or "").strip().lower() != "czynne":
            skipped += 1  # marked as not working in the dataset
            continue
        lon, lat = f["geometry"]["coordinates"]
        place = re.sub(r"\s*N$", "", p["miejsce"].strip())  # drop the dataset's trailing " N" marker
        rows.append({
            "id": f"krk-{TOILET_ID_OFFSET + int(p['ESRI_OID'])}",
            "name": f"Toaleta miejska: {place}",
            "kind": "city_toilet",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "address": f"{place}, {p['dzielnica'].split('. ', 1)[-1]}",
            "access": "open",
            "entry_fee_pln": TOILET_FEE_PLN,
            "opening_hours": json.dumps(parse_toilet_hours(p["godziny"], p["dni"], month)),
            "wheelchair": int((p.get("nplnsprw") or "").strip().lower().startswith("tak")),
            "has_products": 0,
            "has_qr": 0,
            "is_demo": 0,
            "created_at": now_iso,
            "city": "krakow",
        })
    print(f"City toilets: {len(rows)} working, {skipped} skipped as not working.")
    return rows


# ---------- demo data: hand-made points (ILLUSTRATIVE) ----------

def every_day(open_: str, close: str) -> dict:
    return {d: [open_, close] for d in ALL_DAYS}


def weekdays(open_: str, close: str, sat: list | None = None) -> dict:
    h = {d: [open_, close] for d in ALL_DAYS[:5]}
    if sat:
        h["sat"] = sat
    return h


ALWAYS = {"always": True}

# (id, name, kind, lat, lon, address, access, opening_hours, wheelchair, has_products, has_qr)
DEMO_POINTS = [
    # Old Town
    ("krk-0001", "Kawiarnia przy Rynku", "partner", 50.06215, 19.93860, "okolice Rynku Głównego", "ask_staff", every_day("08:00", "22:00"), 0, 1, 1),
    ("krk-0002", "Biblioteka miejska: Stare Miasto", "partner", 50.06370, 19.92980, "okolice ul. Rajskiej", "open", weekdays("09:00", "20:00", ["10:00", "15:00"]), 1, 1, 1),
    ("krk-0003", "Uniwersytet: Collegium (budynek dydaktyczny)", "university", 50.06100, 19.93320, "okolice ul. Gołębiej", "open", weekdays("07:30", "21:00", ["08:00", "16:00"]), 1, 1, 1),
    # Railway station (Kraków Główny)
    ("krk-0004", "Dworzec Kraków Główny: toaleta w hali", "partner", 50.06770, 19.94760, "Dworzec Kraków Główny", "open", ALWAYS, 1, 1, 1),
    ("krk-0005", "Apteka całodobowa przy dworcu", "pharmacy", 50.06600, 19.94350, "okolice ul. Pawiej", "open", ALWAYS, 1, 0, 0),
    ("krk-0006", "Sklep całodobowy przy dworcu", "shop", 50.06650, 19.94600, "okolice Dworca Głównego", "open", ALWAYS, 1, 0, 0),
    # Kazimierz
    ("krk-0007", "Kawiarnia na Kazimierzu", "partner", 50.05150, 19.94460, "okolice Placu Nowego", "ask_staff", every_day("09:00", "23:00"), 0, 1, 1),
    ("krk-0008", "Dom kultury: Kazimierz", "pink_box", 50.05250, 19.94880, "okolice ul. Szerokiej", "open", weekdays("10:00", "20:00", ["10:00", "18:00"]), 1, 1, 1),
    ("krk-0009", "Apteka na Kazimierzu", "pharmacy", 50.05300, 19.94300, "okolice ul. Krakowskiej", "open", weekdays("08:00", "21:00", ["09:00", "15:00"]), 1, 0, 0),
    # Podgórze
    ("krk-0010", "Różowa skrzyneczka: Podgórze", "pink_box", 50.04370, 19.95000, "okolice Rynku Podgórskiego", "open", weekdays("08:00", "18:00"), 1, 1, 1),
    ("krk-0011", "Kawiarnia przy Placu Bohaterów Getta", "partner", 50.04660, 19.95470, "okolice Placu Bohaterów Getta", "ask_staff", every_day("08:00", "20:00"), 1, 1, 1),
    ("krk-0012", "Apteka w Podgórzu", "pharmacy", 50.04500, 19.95200, "okolice ul. Kalwaryjskiej", "open", weekdays("08:00", "20:00", ["09:00", "14:00"]), 1, 0, 0),
    # Universities
    ("krk-0013", "AGH: budynek główny", "university", 50.06560, 19.91880, "okolice al. Mickiewicza", "open", weekdays("07:00", "21:00", ["08:00", "16:00"]), 1, 1, 1),
    ("krk-0014", "AGH: miasteczko studenckie", "university", 50.06810, 19.90500, "okolice ul. Reymonta", "students_only", every_day("07:00", "23:00"), 1, 1, 1),
    ("krk-0015", "Politechnika: kampus Warszawska", "university", 50.07100, 19.94300, "okolice ul. Warszawskiej", "open", weekdays("07:30", "20:00"), 1, 1, 1),
    ("krk-0016", "Uniwersytet: kampus Ruczaj", "university", 50.02750, 19.90300, "okolice ul. Łojasiewicza", "open", weekdays("07:30", "21:00", ["08:00", "15:00"]), 1, 1, 1),
    ("krk-0017", "Uczelnia ekonomiczna: Rakowicka", "university", 50.06850, 19.95450, "okolice ul. Rakowickiej", "open", weekdays("07:30", "20:00"), 1, 1, 1),
    # Nowa Huta
    ("krk-0018", "Biblioteka: Nowa Huta", "partner", 50.07450, 20.03300, "okolice os. Teatralnego", "open", weekdays("10:00", "19:00"), 1, 1, 1),
    ("krk-0019", "Liceum w Nowej Hucie", "school", 50.07800, 20.03900, "okolice os. Szkolnego", "students_only", weekdays("07:30", "16:00"), 1, 1, 1),
    ("krk-0020", "Apteka przy Placu Centralnym", "pharmacy", 50.07100, 20.04000, "okolice Placu Centralnego", "open", every_day("08:00", "22:00"), 1, 0, 0),
    ("krk-0021", "Sklep spożywczy: Nowa Huta", "shop", 50.07800, 20.03000, "okolice al. Róż", "open", every_day("06:00", "23:00"), 1, 0, 0),
    # Other districts
    ("krk-0022", "Szkoła podstawowa: Krowodrza", "school", 50.07600, 19.91500, "okolice ul. Królewskiej", "students_only", weekdays("07:30", "16:00"), 1, 1, 1),
    ("krk-0023", "Kawiarnia w Bronowicach", "partner", 50.08200, 19.89000, "okolice ul. Rydla", "ask_staff", every_day("08:00", "20:00"), 0, 1, 1),
    ("krk-0024", "Stacja paliw całodobowa", "shop", 50.08500, 19.95500, "okolice al. 29 Listopada", "open", ALWAYS, 1, 0, 0),
    ("krk-0025", "Sklep spożywczy: Ruczaj", "shop", 50.02900, 19.90500, "okolice ul. Kobierzyńskiej", "open", every_day("06:00", "23:00"), 1, 0, 0),
    ("krk-0026", "Apteka: Krowodrza", "pharmacy", 50.07500, 19.92300, "okolice ul. Królewskiej", "open", weekdays("08:00", "20:00", ["09:00", "14:00"]), 1, 0, 0),
    # The box we scan live on stage at HackYeah (TAURON Arena Kraków)
    ("krk-demo", "Kropka: stoisko HackYeah", "partner", 50.06760, 19.99150, "TAURON Arena Kraków", "open", ALWAYS, 1, 1, 1),
]


def demo_rows(now_iso: str) -> list[dict]:
    """Kraków demo points (above) plus the demo boxes of the other cities (demo_cities.py)."""
    keys = ["id", "name", "kind", "lat", "lon", "address", "access", "opening_hours", "wheelchair", "has_products", "has_qr"]
    per_city = [("krakow", values) for values in DEMO_POINTS]
    per_city += [(city, values[:-1]) for city, pts in demo_cities.DEMO_POINTS.items() for values in pts]  # drop profile
    rows = []
    for city, values in per_city:
        row = dict(zip(keys, values))
        row.update(opening_hours=json.dumps(row["opening_hours"]), entry_fee_pln=0, is_demo=1,
                   created_at=now_iso, city=city)
        rows.append(row)
    return rows


# ---------- write ----------

UPSERT = """
INSERT INTO points (id, name, kind, lat, lon, address, access, entry_fee_pln, opening_hours,
                    wheelchair, has_products, has_qr, city, is_demo, created_at)
VALUES (:id, :name, :kind, :lat, :lon, :address, :access, :entry_fee_pln, :opening_hours,
        :wheelchair, :has_products, :has_qr, :city, :is_demo, :created_at)
ON CONFLICT(id) DO UPDATE SET
  name=excluded.name, kind=excluded.kind, lat=excluded.lat, lon=excluded.lon, address=excluded.address,
  access=excluded.access, entry_fee_pln=excluded.entry_fee_pln, opening_hours=excluded.opening_hours,
  wheelchair=excluded.wheelchair, has_products=excluded.has_products, has_qr=excluded.has_qr,
  is_demo=excluded.is_demo
"""  # created_at is kept from the first insert


def load_snapshot() -> dict | None:
    if TOILETS_CACHE.exists():
        print(f"Using the saved snapshot {TOILETS_CACHE.name} (offline mode).")
        return json.loads(TOILETS_CACHE.read_text(encoding="utf-8"))
    print("No toilets snapshot found: skipping city toilets.")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Kraków points.")
    parser.add_argument("--offline", action="store_true",
                        help="use data/krakow_toilets.geojson instead of downloading (used on server start)")
    args = parser.parse_args(argv)

    now_iso = to_iso(utc_now())
    rows = []
    toilets = load_snapshot() if args.offline else download_toilets()
    if toilets:
        rows += toilet_rows(toilets, now_iso, date.today().month)
    rows += demo_rows(now_iso)

    conn = connect()
    init_db(conn)
    conn.executemany(UPSERT, rows)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM points WHERE city='krakow'").fetchone()[0]
    demo = sum(1 for r in rows if r["is_demo"])
    print(f"Upserted {len(rows)} points ({demo} demo, all cities). Kraków points in DB: {total}.")
    print("NOTE: demo points (is_demo=1) have illustrative names and positions, not real partners.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
