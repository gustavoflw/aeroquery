from core.airports import (
    METRO_AREAS,
    METRO_MEMBERS,
    all_airport_codes,
    format_location,
    load_airports,
)


def test_load_airports_is_cached_across_calls():
    assert load_airports() is load_airports()


def test_load_airports_returns_real_airport_data():
    airports = load_airports()
    assert len(airports) > 1000
    assert airports["CDG"]["city"] == "Paris"


def test_metro_areas_and_members_are_consistent():
    # Every metro code with a members list should also be a known metro area,
    # and vice versa — these two dicts are meant to be kept in lockstep.
    assert set(METRO_AREAS) == set(METRO_MEMBERS)


def test_format_location_for_real_airport():
    airports = load_airports()
    label = format_location("CDG", airports)
    assert label.startswith("CDG — Paris, FR")


def test_format_location_for_metro_code():
    airports = load_airports()
    label = format_location("STO", airports)
    assert label == "STO — Stockholm, SE · All airports"


def test_format_location_for_unknown_code_falls_back_to_bare_code():
    assert format_location("ZZZ", {}) == "ZZZ"


def test_all_airport_codes_matches_sorted_dict_keys():
    airports = {"CDG": {}, "AAA": {}, "ZZZ": {}}
    assert all_airport_codes(airports) == ["AAA", "CDG", "ZZZ"]
