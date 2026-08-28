"""Airport/location lookups and metro-area handling.

No framework dependency — safe to import from Streamlit, a future API
service, or tests.
"""

import functools

import airportsdata

# IATA multi-airport metropolitan area codes — passing one of these straight
# through as from_airport/to_airport (same field an individual airport code
# goes in) makes Google Flights search every airport in the city at once and
# tag each result with its real originating/arriving airport, e.g. "NYC"
# transparently covers JFK, LGA, and EWR. Not derivable from airportsdata
# (which only groups by an airport's own city field, missing cases like
# Newark, whose city field is "Newark" rather than "New York") — this list
# is hand-curated and each code was confirmed live against Google Flights
# before being added, since a wrong/nonexistent code fails silently as "no
# flights". Only cities where that check actually returned multiple distinct
# airports are included; single-airport "metro" codes (e.g. Berlin's "BER",
# which collides with Berlin Brandenburg's own airport code) are left out
# since they'd just duplicate the airport entry.
METRO_AREAS = {
    "NYC": ("New York", "US"),
    "WAS": ("Washington", "US"),
    "CHI": ("Chicago", "US"),
    "LON": ("London", "GB"),
    "PAR": ("Paris", "FR"),
    "ROM": ("Rome", "IT"),
    "MIL": ("Milan", "IT"),
    "STO": ("Stockholm", "SE"),
    "MOW": ("Moscow", "RU"),
    "TYO": ("Tokyo", "JP"),
    "SEL": ("Seoul", "KR"),
    "YTO": ("Toronto", "CA"),
    "YMQ": ("Montreal", "CA"),
    "BUE": ("Buenos Aires", "AR"),
    "RIO": ("Rio de Janeiro", "BR"),
    "SAO": ("Sao Paulo", "BR"),
}

# Member airports per metro code, for the "narrow to a specific airport"
# picker that appears once a metro is chosen — display/browsing only, not
# used for the actual search (Google expands the metro code itself server
# side; see METRO_AREAS). airportsdata's own city field is too unreliable
# for this: grouping by it drops real majors (YYZ, YUL, EZE, GIG, SDU, BWI,
# CIA all have a city field that doesn't match their metro's name) and pulls
# in irrelevant general-aviation/military fields that happen to share it
# (e.g. Washington's grouping that way includes a handful of small private
# airstrips). Ordered by prominence, most-flown first, not alphabetically.
METRO_MEMBERS = {
    "NYC": ["JFK", "LGA", "EWR"],
    "WAS": ["IAD", "DCA", "BWI"],
    "CHI": ["ORD", "MDW"],
    "LON": ["LHR", "LGW", "STN", "LTN", "LCY"],
    "PAR": ["CDG", "ORY"],
    "ROM": ["FCO", "CIA"],
    "MIL": ["MXP", "LIN", "BGY"],
    "STO": ["ARN", "BMA"],
    "MOW": ["SVO", "DME", "VKO"],
    "TYO": ["HND", "NRT"],
    "SEL": ["ICN", "GMP"],
    "YTO": ["YYZ", "YTZ"],
    "YMQ": ["YUL"],
    "BUE": ["EZE", "AEP"],
    "RIO": ["GIG", "SDU"],
    "SAO": ["GRU", "CGH", "VCP"],
}


@functools.cache
def load_airports() -> dict:
    return airportsdata.load("IATA")


def location_codes(airports: dict) -> list[str]:
    return sorted(set(airports) | set(METRO_AREAS))


def format_location(code: str, airports: dict) -> str:
    if code in METRO_AREAS:
        city, country = METRO_AREAS[code]
        return f"{code} — {city}, {country} · All airports"
    info = airports.get(code)
    if not info:
        return code
    return f"{code} — {info['city']}, {info['country']} · {info['name']}"


def all_airport_codes(airports: dict) -> list[str]:
    """Stable ordering shared between the all-airports map trace and the
    click handler that maps a clicked point index back to an airport code
    (see core.charts.build_route_map / app.render_route_map)."""
    return sorted(airports)
