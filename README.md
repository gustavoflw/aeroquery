# AeroQuery

A Streamlit app for searching one-way flights and visualizing the results on
an interactive route map. Enter an origin, destination, and date; it scrapes
Google Flights and shows every itinerary as both a sortable list and bowed
flight paths on a world map, so you can compare price, stops, and layovers
at a glance.

![AeroQuery screenshot](.github/screenshot.png)

## Features

- **Route map** — each itinerary is drawn as a curved path between airports,
  color-coded by result, with hover details (airline, price, stops, layover
  durations).
- **Linked selection** — click a swatch next to an itinerary or a route on
  the map to highlight it in both places.
- **Itinerary cards** — per-leg times, aircraft type, and layover duration
  for every result, sorted by price.
- **Light/dark aware** — the map palette follows Streamlit's active theme.
- Filter by max stops (nonstop, 1 stop, 2 stops, or any).

## Getting started

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run streamlit run app.py
```

Then open the app in your browser, enter an origin/destination airport
(IATA codes) and a departure date, and search.

## How it works

Flight data comes from [`fast-flights`](https://github.com/AWeirdDev/flights),
which queries Google Flights directly — no API key required. A custom fetch
integration attaches an EU cookie-consent cookie so requests from the EU/EEA
skip Google's consent wall. Airport coordinates for the map come from
[`airportsdata`](https://github.com/mborsetti/airportsdata), and the map
itself is rendered with Plotly.

## License

Apache 2.0 — see [LICENSE](LICENSE).
