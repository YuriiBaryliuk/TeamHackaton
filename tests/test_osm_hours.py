from scripts.osm_hours import parse_osm_hours

WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def test_always():
    assert parse_osm_hours("24/7") == {"always": True}
    assert parse_osm_hours("Mo-Su 00:00-24:00") == {"always": True}


def test_weekdays_and_saturday():
    h = parse_osm_hours("Mo-Fr 08:00-20:00; Sa 08:00-15:00")
    assert h["mon"] == h["fri"] == ["08:00", "20:00"]
    assert h["sat"] == ["08:00", "15:00"]
    assert "sun" not in h


def test_comma_between_rules():
    h = parse_osm_hours("Mo-Fr 08:00-20:00, Sa 08:00-16:00")
    assert h["fri"] == ["08:00", "20:00"] and h["sat"] == ["08:00", "16:00"]


def test_no_days_means_every_day():
    assert parse_osm_hours("06:00-22:00") == {d: ["06:00", "22:00"] for d in WEEK}


def test_off_and_holidays():
    h = parse_osm_hours("Mo-Sa 09:00-21:00; Su off; PH off")
    assert "sun" not in h and h["sat"] == ["09:00", "21:00"]


def test_day_lists_and_split_intervals():
    h = parse_osm_hours("Mo,We,Fr 9:00-12:00,13:00-17:00")
    assert set(h) == {"mon", "wed", "fri"}
    assert h["mon"] == ["09:00", "17:00"]


def test_later_rule_overrides():
    h = parse_osm_hours("Mo-Su 08:00-20:00; Su 10:00-14:00")
    assert h["sat"] == ["08:00", "20:00"] and h["sun"] == ["10:00", "14:00"]


def test_unsupported_returns_none():
    assert parse_osm_hours("Mar-Dec: Mo-Fr 10:00-18:00") is None
    assert parse_osm_hours("sunrise-sunset") is None
    assert parse_osm_hours("Mo-Fr 08:00+") is None
    assert parse_osm_hours("") is None
    assert parse_osm_hours(None) is None
