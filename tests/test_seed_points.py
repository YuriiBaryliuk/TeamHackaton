from scripts.seed_points import in_season, parse_toilet_hours

WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def test_round_the_clock_every_day():
    assert parse_toilet_hours("całodobowo", "Codziennie", 10) == {"always": True}


def test_round_the_clock_weekdays_only():
    h = parse_toilet_hours("całodobowo", "pn-pt", 10)
    assert set(h) == set(WEEK[:5]) and h["mon"] == ["00:00", "24:00"]


def test_simple_hours_with_day_group():
    h = parse_toilet_hours("8.00-16.00", "pn-pt", 10)
    assert h == {d: ["08:00", "16:00"] for d in WEEK[:5]}


def test_weekday_and_weekend_segments():
    h = parse_toilet_hours("pn-pt 9.00-18.00, sb-nd 10.00-16.00", "Codziennie", 10)
    assert h["fri"] == ["09:00", "18:00"] and h["sun"] == ["10:00", "16:00"]


def test_seasonal_hours_pick_current_season():
    text = "8.00-20.00 (IV-X), 9.00-18.00 (XI- III)"  # note the stray space, as in the real data
    assert parse_toilet_hours(text, "Codziennie", 10)["mon"] == ["08:00", "20:00"]  # October
    assert parse_toilet_hours(text, "Codziennie", 1)["mon"] == ["09:00", "18:00"]   # January


def test_in_season_wraps_over_new_year():
    assert in_season("XI", "III", 12) and in_season("XI", "III", 2)
    assert not in_season("XI", "III", 6)
