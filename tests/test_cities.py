from app.cities import CITIES, city_for, inside_city


def test_city_for_each_centre():
    for code, city in CITIES.items():
        assert city_for(*city["center"]) == code


def test_city_for_outside_all_cities():
    assert city_for(51.76, 19.46) is None  # Łódź


def test_inside_city():
    assert inside_city("krakow", 50.0617, 19.9373)
    assert not inside_city("krakow", 52.2297, 21.0122)
    assert not inside_city("atlantis", 50.0, 20.0)
