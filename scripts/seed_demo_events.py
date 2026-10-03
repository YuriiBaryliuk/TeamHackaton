"""Generate 30 days of DEMO events and Urgent searches (all is_demo=1).

    python -m scripts.seed_demo_events

Run seed_points first. Safe to run many times: it deletes the old demo rows
(is_demo=1) and writes new ones. Real rows (is_demo=0) are never touched.
Fixed random seed, so the story is the same every time; the timeline ends
"now", so the demo always looks current.

The simulation per box:
  refilled -> people take one item at a time (only while the place is open,
  07:00-22:00) -> stock runs out -> someone taps "empty" -> a gap -> refilled.
  Not every take is reported (REPORT_TAKE_PROB).
Some boxes stop getting reports on purpose, so the map shows faded / unknown.

Urgent searches are generated in clusters. Two clusters mostly find nothing
(the railway station and Nowa Huta): these are the "white spots" story.
"""
import hashlib
import random
import sys
from datetime import datetime, timedelta

from app.db import connect, init_db, to_iso, utc_now
from app.urgent import TZ, is_open

SEED = 42
DAYS = 30
REPORT_TAKE_PROB = 0.7
ACTIVE_FROM, ACTIVE_TO = 7, 22     # local hours when people use the boxes
DEMO_DEVICES = 300                 # pretend anonymous devices

# Demand profile per demo box:
#   per_day   = items taken per day on average
#   capacity  = items after a refill
#   gap       = hours from "empty" to the next refill (min, max)
#   stale     = no reports in the last N hours (24-72 -> faded, >72 -> unknown)
PROFILES = {
    "krk-0004": dict(per_day=14, capacity=20, gap=(30, 60)),            # station: high demand, slow refill
    "krk-0003": dict(per_day=8, capacity=25, gap=(4, 16)),
    "krk-0013": dict(per_day=9, capacity=25, gap=(4, 16)),
    "krk-0014": dict(per_day=7, capacity=20, gap=(6, 20)),
    "krk-0015": dict(per_day=6, capacity=20, gap=(8, 24)),
    "krk-0016": dict(per_day=5, capacity=20, gap=(8, 24), stale=50),    # faded
    "krk-0017": dict(per_day=6, capacity=20, gap=(6, 20)),
    "krk-0001": dict(per_day=6, capacity=20, gap=(3, 12)),
    "krk-0002": dict(per_day=3, capacity=15, gap=(12, 36)),
    "krk-0007": dict(per_day=5, capacity=20, gap=(3, 12)),
    "krk-0008": dict(per_day=3, capacity=15, gap=(12, 36)),
    "krk-0010": dict(per_day=3, capacity=15, gap=(12, 48)),
    "krk-0011": dict(per_day=4, capacity=15, gap=(6, 24)),
    "krk-0018": dict(per_day=2, capacity=15, gap=(48, 96), stale=100),  # Nowa Huta: unknown
    "krk-0019": dict(per_day=2, capacity=15, gap=(24, 72)),
    "krk-0022": dict(per_day=2, capacity=15, gap=(12, 48), stale=40),   # faded
    "krk-0023": dict(per_day=2, capacity=12, gap=(12, 48), stale=120),  # unknown
}

# (centre lat, centre lon, number of searches, probability that something was found)
SEARCH_CLUSTERS = [
    (50.0677, 19.9476, 140, 0.15),   # railway station: white spot
    (50.0740, 20.0350, 90, 0.10),    # Nowa Huta: white spot
    (50.0820, 19.8900, 30, 0.20),    # Bronowice
    (50.0280, 19.9040, 40, 0.40),    # Ruczaj
    (50.0617, 19.9373, 120, 0.90),   # Old Town
    (50.0515, 19.9446, 70, 0.85),    # Kazimierz
    (50.0660, 19.9150, 80, 0.85),    # AGH
]
CLUSTER_SPREAD_DEG = 0.002

# Boxes that get a refill in the last hour or two if they ended up empty, so that
# "Urgent" in the Old Town, Kazimierz and at AGH finds something during the demo.
# The station box (krk-0004) is deliberately NOT here: it is the white-spot story.
REFILL_RECENTLY = ["krk-0001", "krk-0007", "krk-0014"]


def device(rng: random.Random) -> str:
    return hashlib.sha256(f"demo-device-{rng.randrange(DEMO_DEVICES)}".encode()).hexdigest()


def next_active(t: datetime, opening_hours: str | dict) -> datetime:
    """Move t forward in 30-minute steps until the place is open and it is daytime."""
    for _ in range(24 * 2 * 8):  # at most 8 days ahead
        local_hour = t.astimezone(TZ).hour
        if ACTIVE_FROM <= local_hour < ACTIVE_TO and is_open(opening_hours, t):
            return t
        t += timedelta(minutes=30)
    return t


def simulate_box(point: dict, profile: dict, now: datetime, rng: random.Random) -> list[tuple]:
    """Return (point_id, type, source, device_hash, created_at) rows for one box."""
    rows = []
    hours = point["opening_hours"]
    rate_per_hour = profile["per_day"] / (ACTIVE_TO - ACTIVE_FROM)
    end = now - timedelta(hours=profile.get("stale", 0))
    t = next_active(now - timedelta(days=DAYS, hours=rng.uniform(0, 24)), hours)

    def emit(kind: str, source: str, at: datetime):
        rows.append((point["id"], kind, source, device(rng), to_iso(at)))

    while t < end:
        emit("refilled", rng.choice(["steward", "partner", "qr"]), t)
        stock = profile["capacity"]
        while stock > 0:
            t = next_active(t + timedelta(hours=rng.expovariate(rate_per_hour)), hours)
            if t >= end:
                return rows
            stock -= 1
            if rng.random() < REPORT_TAKE_PROB:
                emit("took", "qr", t)
        t = next_active(t + timedelta(hours=rng.uniform(0.3, 4)), hours)  # someone notices it is empty
        if t >= end:
            return rows
        emit("empty", "qr", t)
        t = next_active(t + timedelta(hours=rng.uniform(*profile["gap"])), hours)
    return rows


def refill_recently(rows: list[tuple], point_id: str, now: datetime, rng: random.Random) -> None:
    """If the box's last state event is 'empty', add a 'refilled' shortly before now."""
    own = [r for r in rows if r[0] == point_id]
    states = [r for r in own if r[1] in ("refilled", "empty")]
    if states and states[-1][1] == "empty":
        last = datetime.fromisoformat(own[-1][4])
        at = min(now, max(last + timedelta(minutes=5), now - timedelta(hours=rng.uniform(0.5, 2))))
        rows.append((point_id, "refilled", "steward", device(rng), to_iso(at)))


def stage_box_events(now: datetime, rng: random.Random) -> list[tuple]:
    """krk-demo: freshly refilled, so tapping "Empty" on stage gives a visible change."""
    return [
        ("krk-demo", "refilled", "steward", device(rng), to_iso(now - timedelta(hours=3))),
        ("krk-demo", "took", "qr", device(rng), to_iso(now - timedelta(hours=2))),
        ("krk-demo", "took", "qr", device(rng), to_iso(now - timedelta(minutes=50))),
    ]


def urgent_rows(now: datetime, rng: random.Random) -> list[tuple]:
    rows = []
    for lat, lon, n, p_found in SEARCH_CLUSTERS:
        for _ in range(n):
            t = next_active(now - timedelta(days=rng.uniform(0, DAYS)), {"always": True})
            if t > now:
                t = now - timedelta(minutes=rng.uniform(5, 600))
            found = rng.random() < p_found
            nearest = round(rng.uniform(1.5, 9.5), 1) if found else (
                round(rng.uniform(11, 30), 1) if rng.random() < 0.8 else None)
            rows.append((
                round(rng.gauss(lat, CLUSTER_SPREAD_DEG), 3),
                round(rng.gauss(lon, CLUSTER_SPREAD_DEG), 3),
                int(found), nearest, to_iso(t),
            ))
    return rows


def main() -> int:
    rng = random.Random(SEED)
    now = utc_now().replace(microsecond=0)
    conn = connect()
    init_db(conn)

    points = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM points WHERE is_demo = 1")}
    missing = [pid for pid in [*PROFILES, "krk-demo"] if pid not in points]
    if missing:
        print(f"Missing demo points {missing}. Run `python -m scripts.seed_points` first.")
        return 1

    events = []
    for pid, profile in PROFILES.items():
        events += simulate_box(points[pid], profile, now, rng)
    for pid in REFILL_RECENTLY:
        refill_recently(events, pid, now, rng)
    events += stage_box_events(now, rng)
    searches = urgent_rows(now, rng)

    with conn:  # one transaction: all or nothing
        conn.execute("DELETE FROM events WHERE is_demo = 1")
        conn.execute("DELETE FROM urgent_searches WHERE is_demo = 1")
        conn.executemany(
            "INSERT INTO events (point_id, type, source, device_hash, created_at, is_demo) VALUES (?, ?, ?, ?, ?, 1)",
            events)
        conn.executemany(
            "INSERT INTO urgent_searches (lat_r, lon_r, found, nearest_min, created_at, is_demo) VALUES (?, ?, ?, ?, ?, 1)",
            searches)

    white = sum(1 for s in searches if s[2] == 0)
    print(f"Demo events: {len(events)} for {len(PROFILES) + 1} boxes over {DAYS} days.")
    print(f"Demo Urgent searches: {len(searches)} ({white} found nothing nearby = white spots).")
    print("All rows are marked is_demo=1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
