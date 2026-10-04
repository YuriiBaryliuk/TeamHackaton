"""Real public toilets and pharmacies for Warszawa, Wrocław and Gdańsk from OpenStreetMap.

    python -m scripts.seed_osm              # import from the saved snapshots (no network)
    python -m scripts.seed_osm --download   # refresh the snapshots from the Overpass API first

Kraków is not here: it uses the city's own open dataset (seed_points.py).

What is imported (is_demo = 0, has_products = 0: nothing is known about free products there):
- amenity=toilets, except access=private/customers/no/permit -> kind 'city_toilet'
- amenity=pharmacy -> kind 'pharmacy' (the fallback when no box is near)
Ids are built from the OSM ids, e.g. waw-osm-n1234567, so they stay stable.
Opening hours: scripts/osm_hours.py; anything it cannot read is stored as "unknown".
Fee: fee=no -> 0; fee=yes -> the number in `charge` if there is one; otherwise unknown.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from app.cities import CITIES
from app.db import BASE_DIR, connect, init_db, to_iso, utc_now
from scripts.osm_hours import parse_osm_hours

OSM_CITIES = ["warszawa", "wroclaw", "gdansk"]
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
QUERY = """[out:json][timeout:90];
area["boundary"="administrative"]["admin_level"="8"]["name"="{name}"]->.c;
( nwr["amenity"="toilets"](area.c); nwr["amenity"="pharmacy"](area.c); );
out center tags;"""
KEEP_TAGS = ["amenity", "name", "brand", "access", "fee", "charge", "opening_hours", "wheelchair",
             "addr:street", "addr:housenumber", "addr:place"]
EXCLUDED_ACCESS = {"private", "customers", "no", "permit"}


def snapshot_path(city: str):
    return BASE_DIR / "data" / f"osm_{city}.json"


def download(city: str) -> list[dict]:
    """Ask the Overpass API; try a second server and a few retries (they are often busy)."""
    data = urllib.parse.urlencode({"data": QUERY.format(name=CITIES[city]["name"])}).encode()
    last = None
    for attempt in range(3):
        for url in OVERPASS_URLS:
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "Kropka-HackYeah/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)["elements"]
            except Exception as e:  # 429/504 from a busy server: try the next one
                last = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass failed for {city}: {last}")


def normalize(elements: list[dict]) -> list[dict]:
    """Keep only what we use, in a stable order, so snapshots diff nicely."""
    out = []
    for e in elements:
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        tags = {k: v for k, v in e.get("tags", {}).items() if k in KEEP_TAGS}
        out.append({"type": e["type"], "id": e["id"], "lat": round(lat, 6), "lon": round(lon, 6), "tags": tags})
    return sorted(out, key=lambda e: (e["type"], e["id"]))


def fee_pln(tags: dict) -> float | None:
    if tags.get("fee") == "no":
        return 0.0
    if tags.get("fee") == "yes":
        m = re.search(r"(\d+(?:[.,]\d+)?)", tags.get("charge", ""))
        return float(m.group(1).replace(",", ".")) if m else None
    return None


def address(tags: dict) -> str | None:
    street = tags.get("addr:street") or tags.get("addr:place")
    if not street:
        return None
    return f"{street} {tags.get('addr:housenumber', '')}".strip()


def rows_for(city: str, elements: list[dict], now_iso: str) -> list[dict]:
    prefix = CITIES[city]["prefix"]
    rows = []
    for e in elements:
        tags = e["tags"]
        amenity = tags.get("amenity")
        if amenity == "toilets":
            if tags.get("access") in EXCLUDED_ACCESS:
                continue
            kind = "city_toilet"
            name = f"Toaleta publiczna: {tags['name']}" if tags.get("name") else "Toaleta publiczna"
            fee = fee_pln(tags)
        elif amenity == "pharmacy":
            kind = "pharmacy"
            name = tags.get("name") or tags.get("brand") or "Apteka"
            fee = 0.0
        else:
            continue
        hours = parse_osm_hours(tags.get("opening_hours")) or {"unknown": True}
        rows.append({
            "id": f"{prefix}-osm-{e['type'][0]}{e['id']}",
            "name": name[:80],
            "kind": kind,
            "lat": e["lat"],
            "lon": e["lon"],
            "address": address(tags),
            "access": "open",
            "entry_fee_pln": fee,
            "opening_hours": json.dumps(hours),
            "wheelchair": int(tags.get("wheelchair") == "yes"),
            "has_products": 0,
            "has_qr": 0,
            "city": city,
            "is_demo": 0,
            "created_at": now_iso,
        })
    return rows


UPSERT = """
INSERT INTO points (id, name, kind, lat, lon, address, access, entry_fee_pln, opening_hours,
                    wheelchair, has_products, has_qr, city, is_demo, created_at)
VALUES (:id, :name, :kind, :lat, :lon, :address, :access, :entry_fee_pln, :opening_hours,
        :wheelchair, :has_products, :has_qr, :city, :is_demo, :created_at)
ON CONFLICT(id) DO UPDATE SET
  name=excluded.name, kind=excluded.kind, lat=excluded.lat, lon=excluded.lon, address=excluded.address,
  entry_fee_pln=excluded.entry_fee_pln, opening_hours=excluded.opening_hours, wheelchair=excluded.wheelchair
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import OSM toilets and pharmacies for other cities.")
    parser.add_argument("--download", action="store_true", help="refresh the snapshots from Overpass first")
    parser.add_argument("cities", nargs="*", choices=OSM_CITIES, help="default: all of them")
    args = parser.parse_args(argv)
    cities = args.cities or OSM_CITIES

    now_iso = to_iso(utc_now())
    conn = connect()
    init_db(conn)
    for city in cities:
        path = snapshot_path(city)
        if args.download:
            try:
                elements = normalize(download(city))
                path.write_text(json.dumps(elements, ensure_ascii=False, indent=0), encoding="utf-8")
                print(f"{city}: downloaded {len(elements)} OSM objects, snapshot saved.")
            except RuntimeError as e:
                print(f"{city}: {e}. Keeping the old snapshot.")
        if not path.exists():
            print(f"{city}: no snapshot ({path.name}); run with --download.")
            continue
        rows = rows_for(city, json.loads(path.read_text(encoding="utf-8")), now_iso)
        conn.executemany(UPSERT, rows)
        conn.commit()
        kinds = {k: sum(1 for r in rows if r["kind"] == k) for k in ("city_toilet", "pharmacy")}
        unknown = sum(1 for r in rows if '"unknown"' in r["opening_hours"])
        print(f"{city}: {kinds['city_toilet']} toilets, {kinds['pharmacy']} pharmacies "
              f"({unknown} with unknown opening hours).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
