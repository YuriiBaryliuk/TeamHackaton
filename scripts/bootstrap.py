"""Run on every server start, before Uvicorn.

    python -m scripts.bootstrap

If the database has no points yet, seed it from the saved snapshots (no network needed):
Kraków city toilets (data/krakow_toilets.geojson), OpenStreetMap toilets and pharmacies for
the other cities (data/osm_*.json), the demo points, and 30 days of demo events ending "now".
If points already exist, do nothing.

On Render's free plan the disk is wiped on every restart, so each boot gets a fresh,
deterministic demo database. With a persistent disk it seeds only once.
"""
import sys

from app.db import DB_PATH, connect, init_db
from scripts import seed_demo_events, seed_osm, seed_points


def main() -> int:
    conn = connect()
    init_db(conn)
    count = conn.execute("SELECT COUNT(*) FROM points").fetchone()[0]
    conn.close()
    if count:
        print(f"Bootstrap: {DB_PATH} already has {count} points, not seeding.")
        return 0
    print(f"Bootstrap: empty database at {DB_PATH}, seeding.")
    if seed_points.main(["--offline"]) != 0 or seed_osm.main([]) != 0:
        return 1
    return seed_demo_events.main()


if __name__ == "__main__":
    sys.exit(main())
