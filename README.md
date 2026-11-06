# Air Traffic — operational performance dashboard

A redesigned Streamlit dashboard for the processed 2025 OPDI flight-list data.

## What's included

- Compact **Air Traffic** title and TU Delft-inspired wordmark
- Global / regional route map
- Interactive filters for date, airline/operator, airport, aircraft type and free-text search
- Overview: monthly traffic, airline leaders, airport movements
- Airline performance: flight counts, aircraft, route breadth and observation-span proxy
- Airport activity: departures, arrivals, total movements and country/location metadata
- Fleet: aircraft types, models, classes and unique aircraft
- Directional route rankings and route diversity
- Record-level flight explorer with CSV export
- Data-quality and preprocessing validation page
- DuckDB queries directly against Parquet: the app does not load all 16m flight records into pandas memory




