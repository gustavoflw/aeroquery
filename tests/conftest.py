from fast_flights.model import Airport, Flights, SimpleDatetime, SingleFlight


def make_leg(
    from_code="OPO",
    to_code="MLA",
    dep=(2026, 9, 18, 8, 0),
    arr=(2026, 9, 18, 11, 0),
    duration=180,
    plane_type="A320",
):
    return SingleFlight(
        from_airport=Airport(name=from_code, code=from_code),
        to_airport=Airport(name=to_code, code=to_code),
        departure=SimpleDatetime(date=dep[:3], time=dep[3:]),
        arrival=SimpleDatetime(date=arr[:3], time=arr[3:]),
        duration=duration,
        plane_type=plane_type,
    )


def make_flight(price=100, airlines=("Test Air",), legs=None):
    """A single-leg (nonstop) flight by default; pass `legs` for a
    multi-leg (connecting) itinerary."""
    return Flights(
        type="nonstop" if legs is None else "multi",
        price=price,
        airlines=list(airlines),
        flights=legs or [make_leg()],
        carbon=None,
    )
