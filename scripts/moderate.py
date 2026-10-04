"""Review points suggested by visitors (approved = 0).

    python -m scripts.moderate list
    python -m scripts.moderate approve krk-2001
    python -m scripts.moderate reject krk-2001     # deletes the point and its marks

No admin login exists on purpose (no accounts at all): whoever has access to the
server runs this script. On Render: Shell tab of the service.
"""
import argparse
import sys

from app.db import connect, init_db


def list_pending(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, kind, lat, lon, address, created_at FROM points WHERE approved = 0 ORDER BY created_at")
    return [dict(r) for r in rows]


def approve(conn, point_id: str) -> bool:
    cur = conn.execute("UPDATE points SET approved = 1 WHERE id = ? AND approved = 0", (point_id,))
    conn.commit()
    return cur.rowcount == 1


def reject(conn, point_id: str) -> bool:
    if not conn.execute("SELECT 1 FROM points WHERE id = ? AND approved = 0", (point_id,)).fetchone():
        return False
    conn.execute("DELETE FROM events WHERE point_id = ?", (point_id,))
    conn.execute("DELETE FROM points WHERE id = ?", (point_id,))
    conn.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review suggested points.")
    parser.add_argument("action", choices=["list", "approve", "reject"])
    parser.add_argument("point_id", nargs="?")
    args = parser.parse_args(argv)
    conn = connect()
    init_db(conn)

    if args.action == "list":
        pending = list_pending(conn)
        for p in pending:
            print(f"{p['id']}  {p['name']}  ({p['kind']})  {p['lat']:.5f},{p['lon']:.5f}  "
                  f"{p['address'] or ''}  added {p['created_at']}")
            print(f"    https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}#map=18/{p['lat']}/{p['lon']}")
        print(f"{len(pending)} point(s) waiting for review.")
        return 0

    if not args.point_id:
        parser.error("point_id is required")
    done = approve(conn, args.point_id) if args.action == "approve" else reject(conn, args.point_id)
    print(f"{args.action}d {args.point_id}" if done else f"{args.point_id} is not a point waiting for review.")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
